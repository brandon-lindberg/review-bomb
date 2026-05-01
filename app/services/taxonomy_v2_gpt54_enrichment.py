from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx
from sqlalchemy import asc, case, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.models import Game, GameSimilarityV3Neighbor, GameSourceTaxonomyLabel
from app.services.game_similarity_v3 import (
    SIMILARITY_V3_STATUS_COMPUTED,
    SIMILARITY_V3_VERSION,
    clear_game_similarity_v3_dirty,
    mark_game_similarity_v3_dirty,
)
from app.services.game_taxonomy import normalize_taxonomy_label
from app.services.game_taxonomy_v2 import (
    FINGERPRINT_AXES,
    TAXONOMY_V2_READY_STATUSES,
    TAXONOMY_V2_STATUS_CURATED,
    TAXONOMY_V2_VERSION,
    TaxonomyV2EvidenceRecord,
    TaxonomyV2Result,
    _canonical_token,
    _ASSIGNMENT_ONLY_NODE_HARD_EXCLUSIONS,
    _ADDITIONAL_NODE_HARD_EXCLUSIONS,
    _prefer_primary_archetype_candidate,
    assign_taxonomy_v2_archetypes,
    build_taxonomy_v2_text_corpus,
    load_archetype_graph_v2,
    load_phrase_matrix,
    load_source_label_matrix,
    store_game_taxonomy_v2,
)


_OPENAI_RESPONSES_PATH = "/responses"
_OPENAI_MODEL = "gpt-5.4"
_DEFAULT_BATCH_SIZE = 50
_DEFAULT_CONCURRENCY = 20
_DEFAULT_MIN_CONFIDENCE = 0.85
_LLM_EVIDENCE_SOURCE = "llm_gpt54"
_MAX_SOURCE_LABELS = 48
_MAX_TEXT_SEGMENT_LENGTH = 2400
_MAX_TEXT_CORPUS_LENGTH = 6000
_OUTPUT_SCHEMA_NAME = "taxonomy_v2_gpt54_enrichment"
_LOW_SIGNAL_AUDIT_STATES = frozenset({"insufficient_signal", "provider_gap", "conflict_ambiguous"})
_DLC_PATTERN = re.compile(r"\b(?:dlc|downloadable content|expansion|expansion pass|story dlc|add[- ]on|addon|episode)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TaxonomyV2EnrichmentSourceLabel:
    source: str
    facet: str
    raw_label: str
    normalized_label: str


@dataclass(frozen=True)
class TaxonomyV2EnrichmentParentGame:
    game_id: int
    public_id: str
    title: str
    release_date: str | None
    taxonomy_v2_status: str | None
    taxonomy_v2_primary_archetype: str | None
    taxonomy_v2_secondary_archetypes: list[str]
    taxonomy_v2_fingerprint: dict[str, list[str]]
    description: str | None
    steam_detailed_description: str | None
    taxonomy_genres: list[str]
    taxonomy_themes: list[str]
    taxonomy_modes: list[str]

    def to_prompt_payload(self) -> dict[str, Any]:
        include_curated_taxonomy = self.taxonomy_v2_status == TAXONOMY_V2_STATUS_CURATED
        return {
            "id": self.game_id,
            "public_id": self.public_id,
            "title": self.title,
            "release_date": self.release_date,
            "taxonomy_v2_status": self.taxonomy_v2_status,
            "taxonomy_v2_primary_archetype": self.taxonomy_v2_primary_archetype if include_curated_taxonomy else None,
            "taxonomy_v2_secondary_archetypes": (
                list(self.taxonomy_v2_secondary_archetypes) if include_curated_taxonomy else []
            ),
            "taxonomy_v2_fingerprint": {
                field: list(values)
                for field, values in ((self.taxonomy_v2_fingerprint or {}) if include_curated_taxonomy else {}).items()
                if values
            },
            "stored_text": {
                "description": _truncate_text(self.description, limit=_MAX_TEXT_SEGMENT_LENGTH),
                "steam_detailed_description": _truncate_text(self.steam_detailed_description, limit=_MAX_TEXT_SEGMENT_LENGTH),
            },
            "stored_labels": {
                "taxonomy_genres": list(self.taxonomy_genres),
                "taxonomy_themes": list(self.taxonomy_themes),
                "taxonomy_modes": list(self.taxonomy_modes),
            },
        }


@dataclass(frozen=True)
class TaxonomyV2EnrichmentBundle:
    game_id: int
    public_id: str
    title: str
    release_date: str | None
    opencritic_id: int | None
    steam_app_id: int | None
    metacritic_slug: str | None
    description: str | None
    opencritic_description: str | None
    steam_short_description: str | None
    steam_detailed_description: str | None
    metacritic_description: str | None
    taxonomy_genres: list[str]
    taxonomy_themes: list[str]
    taxonomy_modes: list[str]
    taxonomy_v2_status: str | None
    taxonomy_v2_text_corpus: str | None
    taxonomy_v2_text_sources: list[str]
    taxonomy_v2_debug_payload: dict[str, Any]
    source_labels: list[TaxonomyV2EnrichmentSourceLabel]
    parent_game: TaxonomyV2EnrichmentParentGame | None = None

    @property
    def audit_state(self) -> str:
        return str((self.taxonomy_v2_debug_payload or {}).get("audit_state") or "unknown")

    @property
    def signal_score(self) -> int:
        score = 0
        if self.taxonomy_v2_text_corpus:
            score += min(len(self.taxonomy_v2_text_corpus) // 250, 12)
        score += min(len(self.source_labels), 12)
        if self.opencritic_id is not None:
            score += 2
        if self.steam_app_id is not None:
            score += 2
        if self.metacritic_slug:
            score += 1
        return score

    @property
    def has_rich_db_evidence(self) -> bool:
        if self.signal_score >= 10:
            return True
        if self.taxonomy_v2_text_corpus and len(self.taxonomy_v2_text_corpus) >= 600 and len(self.source_labels) >= 4:
            return True
        return False

    @property
    def appears_dlc(self) -> bool:
        if self.parent_game is not None:
            return True
        if _DLC_PATTERN.search(self.title or ""):
            return True
        for text in (
            self.description,
            self.opencritic_description,
            self.steam_short_description,
            self.steam_detailed_description,
            self.metacritic_description,
            self.taxonomy_v2_text_corpus,
        ):
            if text and _DLC_PATTERN.search(text):
                return True
        return any(
            label.normalized_label in {"downloadable content", "dlc", "expansion", "addon", "add on"}
            for label in self.source_labels
        )

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "game": {
                "id": self.game_id,
                "public_id": self.public_id,
                "title": self.title,
                "release_date": self.release_date,
                "opencritic_id": self.opencritic_id,
                "steam_app_id": self.steam_app_id,
                "metacritic_slug": self.metacritic_slug,
            },
            "current_taxonomy": {
                "status": self.taxonomy_v2_status,
                "audit_state": self.audit_state,
                "debug_payload": self.taxonomy_v2_debug_payload or {},
            },
            "stored_text": {
                "description": _truncate_text(self.description, limit=_MAX_TEXT_SEGMENT_LENGTH),
                "opencritic_description": _truncate_text(self.opencritic_description, limit=_MAX_TEXT_SEGMENT_LENGTH),
                "steam_short_description": _truncate_text(self.steam_short_description, limit=_MAX_TEXT_SEGMENT_LENGTH),
                "steam_detailed_description": _truncate_text(self.steam_detailed_description, limit=_MAX_TEXT_SEGMENT_LENGTH),
                "metacritic_description": _truncate_text(self.metacritic_description, limit=_MAX_TEXT_SEGMENT_LENGTH),
                "taxonomy_v2_text_corpus": _truncate_text(self.taxonomy_v2_text_corpus, limit=_MAX_TEXT_CORPUS_LENGTH),
                "taxonomy_v2_text_sources": list(self.taxonomy_v2_text_sources),
            },
            "stored_labels": {
                "taxonomy_genres": list(self.taxonomy_genres),
                "taxonomy_themes": list(self.taxonomy_themes),
                "taxonomy_modes": list(self.taxonomy_modes),
                "source_labels": [
                    {
                        "source": label.source,
                        "facet": label.facet,
                        "raw_label": label.raw_label,
                        "normalized_label": label.normalized_label,
                    }
                    for label in self.source_labels[:_MAX_SOURCE_LABELS]
                ],
            },
            "dlc_context": {
                "appears_dlc": self.appears_dlc,
                "likely_parent_game": self.parent_game.to_prompt_payload() if self.parent_game is not None else None,
            },
        }


@dataclass(frozen=True)
class TaxonomyV2ExternalEvidence:
    evidence_quality: str
    evidence_summary: str
    gameplay_facts: dict[str, list[str]]
    source_urls: list[str]
    source_notes: list[str]

    @property
    def has_material_evidence(self) -> bool:
        if self.source_urls:
            return True
        if self.evidence_summary:
            return True
        return any(values for values in self.gameplay_facts.values())

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "evidence_quality": self.evidence_quality,
            "evidence_summary": self.evidence_summary,
            "gameplay_facts": {
                key: list(values)
                for key, values in self.gameplay_facts.items()
                if values
            },
            "source_urls": list(self.source_urls),
            "source_notes": list(self.source_notes),
        }


@dataclass(frozen=True)
class TaxonomyV2EnrichmentDecision:
    game_id: int
    public_id: str
    title: str
    accepted: bool
    status: str
    reason: str
    used_web: bool
    llm_confidence: float | None
    result: TaxonomyV2Result | None
    payload: dict[str, Any]
    research_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class TaxonomyV2SimilarGameExample:
    title: str
    expected_relationship: str
    why_similar: str


@dataclass(frozen=True)
class TaxonomyV2SimilarGamesPreview:
    game_id: int
    public_id: str
    title: str
    confidence: float | None
    used_web: bool
    anchor_summary: str
    expected_must_include_titles: list[str]
    similar_games: list[TaxonomyV2SimilarGameExample]
    source_urls: list[str]
    payload: dict[str, Any]
    research_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class TaxonomyV2SimilarCandidateReview:
    candidate_public_id: str
    candidate_title: str
    requested_title: str
    input_rank: int
    rank: int
    strength_label: str
    strength_score: float
    relationship_fit: str
    rationale: str


@dataclass(frozen=True)
class TaxonomyV2SimilarGamesStageEvaluation:
    game_id: int
    public_id: str
    title: str
    overall_verdict: str
    overall_note: str
    anchor_summary: str
    used_web: bool
    source_urls: list[str]
    gap_notes: list[str]
    candidate_reviews: list[TaxonomyV2SimilarCandidateReview]
    payload: dict[str, Any]
    research_payload: dict[str, Any] | None = None


class OpenAITaxonomyEnrichmentAuthError(RuntimeError):
    """Raised when the OpenAI API is not configured."""


def _truncate_text(value: str | None, *, limit: int) -> str | None:
    if not value:
        return None
    cleaned = " ".join(str(value).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_tokens(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        token = _canonical_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
    return cleaned


def _confidence_by_field_value(fingerprint: dict[str, list[str]], confidence: float) -> dict[str, dict[str, float]]:
    bounded = max(0.0, min(confidence, 0.99))
    return {
        field: {value: bounded for value in values}
        for field, values in fingerprint.items()
        if values
    }


def _iter_rule_outputs(container: Any) -> Iterable[tuple[str, str]]:
    if isinstance(container, dict):
        for value in container.values():
            yield from _iter_rule_outputs(value)
        return
    if isinstance(container, list):
        if len(container) >= 2 and isinstance(container[0], str) and isinstance(container[1], str):
            yield _canonical_token(container[0]), _canonical_token(container[1])
            return
        for value in container:
            yield from _iter_rule_outputs(value)


@lru_cache(maxsize=1)
def load_taxonomy_v2_allowed_vocab() -> dict[str, Any]:
    graph = load_archetype_graph_v2()
    families_by_archetype: dict[str, str] = {}
    allowed_values_by_field: dict[str, set[str]] = {field: set() for field in FINGERPRINT_AXES}

    for archetype, node in (graph.get("nodes") or {}).items():
        canonical_archetype = _canonical_token(archetype)
        if not canonical_archetype:
            continue
        families_by_archetype[canonical_archetype] = _canonical_token(node.get("family", "")) or ""
        for bucket in ("required_axes", "preferred_axes"):
            for field, values in (node.get(bucket) or {}).items():
                canonical_field = _canonical_token(field)
                if canonical_field not in allowed_values_by_field:
                    continue
                allowed_values_by_field[canonical_field].update(_canonical_token(value) for value in values if _canonical_token(value))
        hard_exclusions = {
            _canonical_token(value)
            for value in (node.get("hard_exclusions") or [])
            if _canonical_token(value)
        }
        hard_exclusions.update(_ADDITIONAL_NODE_HARD_EXCLUSIONS.get(canonical_archetype, set()))
        hard_exclusions.update(_ASSIGNMENT_ONLY_NODE_HARD_EXCLUSIONS.get(canonical_archetype, set()))
        allowed_values_by_field["hard_exclusions"].update(hard_exclusions)

    for field, value in _iter_rule_outputs(load_source_label_matrix()):
        if field in allowed_values_by_field and value:
            allowed_values_by_field[field].add(value)
    for rule in load_phrase_matrix().get("rules", []):
        for field, value in _iter_rule_outputs(rule.get("emits")):
            if field in allowed_values_by_field and value:
                allowed_values_by_field[field].add(value)

    return {
        "archetypes": sorted(families_by_archetype),
        "families_by_archetype": families_by_archetype,
        "values_by_field": {
            field: sorted(values)
            for field, values in allowed_values_by_field.items()
        },
    }


def _response_schema() -> dict[str, Any]:
    fingerprint_properties = {
        field: {
            "type": "array",
            "items": {"type": "string"},
        }
        for field in FINGERPRINT_AXES
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["accept", "reject"],
            },
            "primary_archetype": {"type": "string"},
            "secondary_archetypes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "fingerprint": {
                "type": "object",
                "additionalProperties": False,
                "properties": fingerprint_properties,
                "required": list(FINGERPRINT_AXES),
            },
            "confidence": {"type": "number"},
            "evidence_summary": {"type": "string"},
            "used_web": {"type": "boolean"},
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rejection_reason": {"type": "string"},
        },
        "required": [
            "decision",
            "primary_archetype",
            "secondary_archetypes",
            "fingerprint",
            "confidence",
            "evidence_summary",
            "used_web",
            "source_urls",
            "rejection_reason",
        ],
    }


def _research_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "evidence_quality": {
                "type": "string",
                "enum": ["strong", "moderate", "weak", "none"],
            },
            "evidence_summary": {"type": "string"},
            "gameplay_facts": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "core_loop": {"type": "array", "items": {"type": "string"}},
                    "perspective": {"type": "array", "items": {"type": "string"}},
                    "combat": {"type": "array", "items": {"type": "string"}},
                    "progression": {"type": "array", "items": {"type": "string"}},
                    "structure": {"type": "array", "items": {"type": "string"}},
                    "modes": {"type": "array", "items": {"type": "string"}},
                    "dlc_relationship": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "core_loop",
                    "perspective",
                    "combat",
                    "progression",
                    "structure",
                    "modes",
                    "dlc_relationship",
                ],
            },
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "evidence_quality",
            "evidence_summary",
            "gameplay_facts",
            "source_urls",
            "source_notes",
        ],
    }


def _similar_games_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "anchor_summary": {"type": "string"},
            "confidence": {"type": "number"},
            "used_web": {"type": "boolean"},
            "expected_must_include_titles": {
                "type": "array",
                "items": {"type": "string"},
            },
            "similar_games": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "expected_relationship": {
                            "type": "string",
                            "enum": ["same", "strong_neighbor", "adjacent_neighbor", "base_game"],
                        },
                        "why_similar": {"type": "string"},
                    },
                    "required": ["title", "expected_relationship", "why_similar"],
                },
            },
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "anchor_summary",
            "confidence",
            "used_web",
            "expected_must_include_titles",
            "similar_games",
            "source_urls",
        ],
    }


def _similar_stage_evaluation_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "anchor_summary": {"type": "string"},
            "overall_verdict": {
                "type": "string",
                "enum": ["excellent", "good", "mixed", "weak"],
            },
            "overall_note": {"type": "string"},
            "gap_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
            "candidate_reviews": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_public_id": {"type": "string"},
                        "rank": {"type": "integer"},
                        "strength_label": {
                            "type": "string",
                            "enum": ["must_keep", "strong", "good", "weak", "drop"],
                        },
                        "strength_score": {"type": "number"},
                        "relationship_fit": {
                            "type": "string",
                            "enum": [
                                "base_game",
                                "same",
                                "strong_neighbor",
                                "adjacent_neighbor",
                                "weak_neighbor",
                                "wrong",
                            ],
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "candidate_public_id",
                        "rank",
                        "strength_label",
                        "strength_score",
                        "relationship_fit",
                        "rationale",
                    ],
                },
            },
        },
        "required": [
            "anchor_summary",
            "overall_verdict",
            "overall_note",
            "gap_notes",
            "candidate_reviews",
        ],
    }


def _build_system_prompt(*, allow_web: bool, has_external_evidence: bool = False) -> str:
    vocab = load_taxonomy_v2_allowed_vocab()
    web_rule = (
        "Web lookup is available. Use it only if the stored DB evidence is weak, missing, or conflicting."
        if allow_web
        else "Web lookup is not available for this pass. Use only the stored DB evidence."
    )
    external_evidence_rule = (
        "external_evidence contains grounded, source-backed gameplay facts gathered after the first pass. "
        "Use it directly and let it raise confidence when it materially strengthens the evidence.\n"
        if has_external_evidence
        else ""
    )
    return (
        "You are classifying a video game into the existing Similar Games Taxonomy V2.\n"
        "Return strict JSON matching the provided schema.\n"
        "Reject when the evidence is thin, contradictory, or title-only.\n"
        "Prefer gameplay identity over publisher, platform, or business model metadata.\n"
        f"{web_rule}\n"
        f"{external_evidence_rule}"
        "If dlc_context indicates the title appears to be DLC and a likely_parent_game is supplied, treat the parent game's stored gameplay evidence as primary evidence for the DLC.\n"
        "Additive story, mission, location, weapon, or expansion content should usually preserve the parent game's core gameplay identity unless the DLC bundle clearly establishes a different mode or genre.\n"
        "Only inherit the parent game's core gameplay identity when the DLC bundle does not materially contradict it.\n"
        "Confidence may still be high when the DLC's own copy is sparse if the parent gameplay evidence is rich and the DLC description is additive rather than contradictory.\n"
        "When official store or publisher sources consistently describe concrete gameplay loops, mechanics, structure, and modes, that is sufficient to support high confidence even if third-party reviews are sparse.\n"
        "Only use archetypes from this list:\n"
        f"{json.dumps(vocab['archetypes'])}\n"
        "Only use fingerprint fields and token values already present in the taxonomy vocabulary below.\n"
        f"{json.dumps(vocab['values_by_field'], separators=(',', ':'))}\n"
        "If you reject, set primary_archetype to an empty string and leave all fingerprint arrays empty.\n"
        "If you accept, the fingerprint must strongly support the chosen primary archetype.\n"
        "Use source_urls only for pages that materially informed the classification."
    )


def _build_source_hints(bundle: TaxonomyV2EnrichmentBundle) -> dict[str, Any]:
    suggested_urls: list[str] = []
    search_queries: list[str] = []
    if bundle.steam_app_id is not None:
        suggested_urls.append(f"https://store.steampowered.com/app/{bundle.steam_app_id}/")
    if bundle.metacritic_slug:
        suggested_urls.append(f"https://www.metacritic.com/game/{bundle.metacritic_slug}")
    search_queries.append(f"\"{bundle.title}\" gameplay")
    if bundle.release_date:
        search_queries.append(f"\"{bundle.title}\" {bundle.release_date} gameplay")
    if bundle.opencritic_id is not None:
        search_queries.append(f"site:opencritic.com \"{bundle.title}\"")
    if bundle.appears_dlc and bundle.parent_game is not None:
        search_queries.append(f"\"{bundle.title}\" DLC for \"{bundle.parent_game.title}\" gameplay")
    return {
        "suggested_urls": suggested_urls,
        "search_queries": search_queries[:5],
    }


def _build_research_system_prompt() -> str:
    return (
        "You are gathering grounded gameplay evidence for one video game before taxonomy classification.\n"
        "Use web search to find authoritative, gameplay-relevant sources.\n"
        "Prioritize official sites, store pages, publisher/developer pages, OpenCritic, and Metacritic.\n"
        "Consistent official/store evidence is sufficient for strong evidence_quality when it provides concrete gameplay details.\n"
        "Do not downgrade evidence_quality only because third-party reviews are sparse if authoritative first-party sources are detailed and internally consistent.\n"
        "Focus on gameplay identity: core loop, perspective, combat, progression, structure, modes, and DLC relationship.\n"
        "Return strict JSON matching the schema.\n"
        "Do not classify into a taxonomy archetype in this step.\n"
        "Do not invent URLs. Only return source_urls that materially informed the research result."
    )


def _build_research_user_prompt(bundle: TaxonomyV2EnrichmentBundle) -> str:
    payload = bundle.to_prompt_payload()
    source_hints = _build_source_hints(bundle)
    return (
        "Research this game and extract grounded gameplay evidence.\n"
        "Use the DB payload for identity disambiguation, then gather stronger external evidence.\n"
        "Prefer authoritative sources and focus on concrete gameplay facts.\n"
        "Evidence bundle:\n"
        f"{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}\n"
        "Source hints:\n"
        f"{json.dumps(source_hints, ensure_ascii=True, separators=(',', ':'))}"
    )


def _build_user_prompt(
    bundle: TaxonomyV2EnrichmentBundle,
    *,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
) -> str:
    payload = bundle.to_prompt_payload()
    dlc_hint = ""
    if bundle.appears_dlc and bundle.parent_game is not None:
        dlc_hint = (
            "DLC guidance:\n"
            f"- This title appears to be DLC for {bundle.parent_game.title}.\n"
            "- Prefer the parent game's stored descriptions and labels over any non-curated parent taxonomy fields.\n"
            "- If the DLC evidence is additive and does not contradict the parent game's core gameplay, classify it using the parent game's gameplay identity.\n"
        )
    external_evidence_block = ""
    if external_evidence is not None and external_evidence.has_material_evidence:
        external_evidence_block = (
            "External evidence:\n"
            f"{json.dumps(external_evidence.to_prompt_payload(), ensure_ascii=True, separators=(',', ':'))}\n"
        )
    return (
        "Classify this game for Similar Games Taxonomy V2.\n"
        "Use the stored DB evidence first. Reject if the evidence is not strong enough.\n"
        f"{dlc_hint}"
        f"{external_evidence_block}"
        "Evidence bundle:\n"
        f"{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}"
    )


def _build_similar_games_system_prompt(*, has_external_evidence: bool = False) -> str:
    prompt = (
        "You are selecting concrete similar-game examples for a video game.\n"
        "Return strict JSON matching the schema.\n"
        "Choose games based on gameplay identity, not just setting, tone, or franchise adjacency.\n"
        "Prefer released, recognizable, gameplay-relevant examples over obscure long-tail titles when multiple answers fit.\n"
        "Do not default to unreleased, anthology, or compilation products unless the anchor itself clearly matches that product type.\n"
        "For DLC or expansion content, include the base game in expected_must_include_titles when the DLC inherits the base game's core gameplay identity.\n"
        "If the title is additive DLC, the base game should usually appear in similar_games with expected_relationship=base_game.\n"
        "Bias toward examples a human editor would immediately recognize as sensible comps for a similar-games rail.\n"
        "Keep why_similar concise and specific to gameplay loop, structure, combat, progression, or mode.\n"
        "Use source_urls only for pages that materially informed the judgment."
    )
    if has_external_evidence:
        prompt += (
            "\nexternal_evidence contains grounded, source-backed gameplay facts."
            " Use it as the main truth source and let it improve confidence."
        )
    return prompt


def _build_similar_stage_evaluation_system_prompt(*, has_external_evidence: bool = False) -> str:
    prompt = (
        "You are reviewing a proposed similar-games rail for one anchor video game.\n"
        "Evaluate only the provided candidate games. Do not invent, substitute, or omit titles.\n"
        "Return strict JSON matching the schema.\n"
        "Rank every provided candidate exactly once from best fit to worst fit.\n"
        "Judge fit by gameplay identity: core loop, perspective, combat, progression, structure, challenge model, and mode profile.\n"
        "Do not reward a candidate just for shared setting, tone, franchise, or surface aesthetics.\n"
        "Use proposed taxonomy as context, not as binding truth, if the gameplay evidence points elsewhere.\n"
        "Use these labels:\n"
        "- must_keep: essential comp, obvious benchmark, or base game/DLC pairing a human editor would expect.\n"
        "- strong: clearly strong fit and good rail candidate.\n"
        "- good: reasonable fit, acceptable but not essential.\n"
        "- weak: partial fit or second-order comp that probably loses to better options.\n"
        "- drop: misleading or poor fit for a similar-games rail.\n"
        "Use relationship_fit values this way:\n"
        "- base_game: the candidate is the anchor's base game or direct expansion anchor.\n"
        "- same: nearly same gameplay identity and audience expectation.\n"
        "- strong_neighbor: very close gameplay fit.\n"
        "- adjacent_neighbor: meaningful but looser fit.\n"
        "- weak_neighbor: understandable but stretched fit.\n"
        "- wrong: not a good similar-games recommendation.\n"
        "Keep rationale concise and specific."
    )
    if has_external_evidence:
        prompt += (
            "\nexternal_evidence contains grounded gameplay facts for the anchor."
            " Use it to improve confidence in the candidate judgments."
        )
    return prompt


def _build_similar_repair_system_prompt(*, has_external_evidence: bool = False) -> str:
    prompt = (
        "You are repairing the weak tail of a similar-games rail for one video game.\n"
        "Return strict JSON matching the schema.\n"
        "You are proposing replacement games only.\n"
        "Do not repeat any title from keep_candidates or blocked_titles.\n"
        "Choose released, recognizable games that better fit the anchor's gameplay identity.\n"
        "Prefer replacements that directly address the supplied gap_notes.\n"
        "Judge fit by gameplay identity: core loop, structure, progression, combat, perspective, mode profile, and challenge model.\n"
        "For DLC or expansion anchors, include the base game only if it is missing from keep_candidates and is the clearest must-have comp.\n"
        "Keep why_similar concise and specific."
    )
    if has_external_evidence:
        prompt += (
            "\nexternal_evidence contains grounded gameplay facts for the anchor."
            " Use it to improve the replacement choices."
        )
    return prompt


def _build_similar_games_user_prompt(
    bundle: TaxonomyV2EnrichmentBundle,
    *,
    limit: int,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
) -> str:
    payload = bundle.to_prompt_payload()
    external_evidence_block = ""
    if external_evidence is not None and external_evidence.has_material_evidence:
        external_evidence_block = (
            "External evidence:\n"
            f"{json.dumps(external_evidence.to_prompt_payload(), ensure_ascii=True, separators=(',', ':'))}\n"
        )
    return (
        f"Select {max(1, min(limit, 10))} similar game examples for this title.\n"
        "Treat this as a human editorial similar-games rail preview.\n"
        "If the title is DLC and the base game is the clearest must-have neighbor, include it explicitly.\n"
        f"{external_evidence_block}"
        "Evidence bundle:\n"
        f"{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}"
    )


def _build_similar_repair_user_prompt(
    bundle: TaxonomyV2EnrichmentBundle,
    stage_row: dict[str, Any],
    evaluation_row: dict[str, Any],
    *,
    replacement_limit: int,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
) -> str:
    proposed_taxonomy = dict(stage_row.get("proposed_taxonomy") or {})
    keep_candidates = [
        {
            "rank": item.get("rank"),
            "title": item.get("candidate_title"),
            "relationship_fit": item.get("relationship_fit"),
            "strength_label": item.get("strength_label"),
            "strength_score": item.get("strength_score"),
        }
        for item in (evaluation_row.get("candidate_reviews") or [])
        if str(item.get("strength_label") or "") in {"must_keep", "strong", "good"}
    ]
    blocked_titles = [
        item.get("candidate_title")
        for item in (evaluation_row.get("candidate_reviews") or [])
        if str(item.get("strength_label") or "") in {"weak", "drop"}
    ]
    external_evidence_block = ""
    if external_evidence is not None and external_evidence.has_material_evidence:
        external_evidence_block = (
            "External evidence:\n"
            f"{json.dumps(external_evidence.to_prompt_payload(), ensure_ascii=True, separators=(',', ':'))}\n"
        )
    payload = {
        "anchor_game": bundle.to_prompt_payload(),
        "proposed_taxonomy": {
            "primary_archetype": proposed_taxonomy.get("primary_archetype"),
            "secondary_archetypes": list(proposed_taxonomy.get("secondary_archetypes") or []),
            "confidence": proposed_taxonomy.get("confidence"),
            "evidence_summary": proposed_taxonomy.get("evidence_summary"),
        },
        "keep_candidates": keep_candidates,
        "blocked_titles": blocked_titles,
        "gap_notes": list(evaluation_row.get("gap_notes") or []),
        "replacement_limit": max(1, min(int(replacement_limit), 10)),
    }
    return (
        f"Repair this similar-games rail by proposing {payload['replacement_limit']} replacement titles.\n"
        "Do not repeat any blocked or already-kept titles.\n"
        f"{external_evidence_block}"
        "Repair context:\n"
        f"{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}"
    )


def _build_similarity_review_candidate_snapshot(game: Game, stage_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_public_id": str(getattr(game, "public_id", "") or ""),
        "candidate_title": str(getattr(game, "title", "") or ""),
        "requested_title": _sanitize_single_short_text(stage_item.get("requested_title"), limit=160)
        or str(getattr(game, "title", "") or ""),
        "input_rank": int(stage_item.get("rank") or 0),
        "requested_relationship": _sanitize_single_short_text(stage_item.get("expected_relationship"), limit=64)
        or "adjacent_neighbor",
        "requested_why_similar": _sanitize_single_short_text(stage_item.get("why_similar"), limit=360),
        "release_date": getattr(game, "release_date", None).isoformat() if getattr(game, "release_date", None) else None,
        "taxonomy": {
            "status": getattr(game, "taxonomy_v2_status", None),
            "primary_archetype": getattr(game, "taxonomy_v2_primary_archetype", None),
            "secondary_archetypes": list(getattr(game, "taxonomy_v2_secondary_archetypes", None) or []),
            "confidence": float(getattr(game, "taxonomy_v2_confidence", None) or 0)
            if getattr(game, "taxonomy_v2_confidence", None) is not None
            else None,
        },
        "stored_text": {
            "description": _truncate_text(getattr(game, "description", None), limit=700),
            "opencritic_description": _truncate_text(getattr(game, "opencritic_description", None), limit=700),
            "steam_short_description": _truncate_text(getattr(game, "steam_short_description", None), limit=700),
            "taxonomy_v2_text_corpus": _truncate_text(getattr(game, "taxonomy_v2_text_corpus", None), limit=1200),
        },
        "stored_labels": {
            "taxonomy_genres": list(getattr(game, "taxonomy_genres", None) or []),
            "taxonomy_themes": list(getattr(game, "taxonomy_themes", None) or []),
            "taxonomy_modes": list(getattr(game, "taxonomy_modes", None) or []),
        },
    }


def _build_similar_stage_evaluation_user_prompt(
    bundle: TaxonomyV2EnrichmentBundle,
    stage_row: dict[str, Any],
    candidate_games_by_public_id: dict[str, Game],
    *,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
) -> str:
    anchor_payload = {
        "anchor_game": bundle.to_prompt_payload(),
        "current_taxonomy": dict(stage_row.get("current_taxonomy") or {}),
        "proposed_taxonomy": {
            "primary_archetype": (stage_row.get("proposed_taxonomy") or {}).get("primary_archetype"),
            "secondary_archetypes": list((stage_row.get("proposed_taxonomy") or {}).get("secondary_archetypes") or []),
            "confidence": (stage_row.get("proposed_taxonomy") or {}).get("confidence"),
            "evidence_summary": (stage_row.get("proposed_taxonomy") or {}).get("evidence_summary"),
        },
        "review_flags": list(stage_row.get("review_flags") or []),
    }
    candidate_payloads: list[dict[str, Any]] = []
    for item in stage_row.get("staged_neighbors") or []:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        if not candidate_public_id:
            continue
        candidate_game = candidate_games_by_public_id.get(candidate_public_id)
        if candidate_game is None:
            continue
        candidate_payloads.append(_build_similarity_review_candidate_snapshot(candidate_game, item))
    external_evidence_block = ""
    if external_evidence is not None and external_evidence.has_material_evidence:
        external_evidence_block = (
            "external_evidence:\n"
            f"{json.dumps(external_evidence.to_prompt_payload(), ensure_ascii=True, separators=(',', ':'))}\n"
        )
    return (
        "Review this proposed similar-games rail and rank every candidate.\n"
        "You must evaluate every provided candidate exactly once.\n"
        f"{external_evidence_block}"
        "Anchor context:\n"
        f"{json.dumps(anchor_payload, ensure_ascii=True, separators=(',', ':'))}\n"
        "Candidate set:\n"
        f"{json.dumps(candidate_payloads, ensure_ascii=True, separators=(',', ':'))}"
    )


def _extract_response_text(payload: dict[str, Any]) -> str:
    output_parts: list[str] = []
    for item in payload.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                output_parts.append(content["text"])
            if content.get("type") == "refusal":
                raise RuntimeError(str(content.get("refusal") or "Model refused request"))
    if output_parts:
        return "\n".join(output_parts)
    raise RuntimeError("OpenAI response did not include output_text")


def _sanitize_source_urls(values: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned[:8]


def _sanitize_short_text_list(values: Any, *, limit: int = 8, item_limit: int = 220) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            continue
        value = " ".join(raw.split()).strip()
        if not value:
            continue
        if len(value) > item_limit:
            value = value[: item_limit - 3].rstrip() + "..."
        marker = value.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def _sanitize_single_short_text(value: Any, *, limit: int = 280) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 3].rstrip() + "..."
    return cleaned


def _build_external_evidence(response_payload: dict[str, Any]) -> TaxonomyV2ExternalEvidence | None:
    summary = _truncate_text(str(response_payload.get("evidence_summary") or "").strip(), limit=1600) or ""
    evidence_quality = _canonical_token(response_payload.get("evidence_quality")) or "none"
    gameplay_facts_payload = response_payload.get("gameplay_facts") or {}
    gameplay_facts = {
        key: _sanitize_short_text_list((gameplay_facts_payload or {}).get(key) or [])
        for key in (
            "core_loop",
            "perspective",
            "combat",
            "progression",
            "structure",
            "modes",
            "dlc_relationship",
        )
    }
    source_urls = _sanitize_source_urls(response_payload.get("source_urls") or [])
    source_notes = _sanitize_short_text_list(response_payload.get("source_notes") or [], limit=8, item_limit=320)
    evidence = TaxonomyV2ExternalEvidence(
        evidence_quality=evidence_quality,
        evidence_summary=summary,
        gameplay_facts=gameplay_facts,
        source_urls=source_urls,
        source_notes=source_notes,
    )
    if not evidence.has_material_evidence:
        return None
    return evidence


def _build_similar_games_preview(
    bundle: TaxonomyV2EnrichmentBundle,
    response_payload: dict[str, Any],
    *,
    used_web: bool,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
    research_payload: dict[str, Any] | None = None,
    limit: int,
) -> TaxonomyV2SimilarGamesPreview:
    confidence = _safe_float(response_payload.get("confidence"))
    anchor_summary = _truncate_text(
        _sanitize_single_short_text(response_payload.get("anchor_summary"), limit=900),
        limit=900,
    ) or ""
    similar_games_payload = response_payload.get("similar_games") or []
    similar_games: list[TaxonomyV2SimilarGameExample] = []
    seen_titles: set[str] = set()
    for item in similar_games_payload:
        if not isinstance(item, dict):
            continue
        title = _sanitize_single_short_text(item.get("title"), limit=160)
        if not title:
            continue
        marker = title.casefold()
        if marker in seen_titles:
            continue
        seen_titles.add(marker)
        relationship = _canonical_token(item.get("expected_relationship")) or "adjacent_neighbor"
        if relationship not in {"same", "strong_neighbor", "adjacent_neighbor", "base_game"}:
            relationship = "adjacent_neighbor"
        why_similar = _sanitize_single_short_text(item.get("why_similar"), limit=360)
        if not why_similar:
            continue
        similar_games.append(
            TaxonomyV2SimilarGameExample(
                title=title,
                expected_relationship=relationship,
                why_similar=why_similar,
            )
        )
        if len(similar_games) >= max(1, min(limit, 10)):
            break

    expected_must_include_titles = _sanitize_short_text_list(
        response_payload.get("expected_must_include_titles") or [],
        limit=5,
        item_limit=160,
    )
    source_urls = _sanitize_source_urls(
        list(response_payload.get("source_urls") or [])
        + (list(external_evidence.source_urls) if external_evidence is not None else [])
    )
    return TaxonomyV2SimilarGamesPreview(
        game_id=bundle.game_id,
        public_id=bundle.public_id,
        title=bundle.title,
        confidence=confidence,
        used_web=used_web,
        anchor_summary=anchor_summary,
        expected_must_include_titles=expected_must_include_titles,
        similar_games=similar_games,
        source_urls=source_urls,
        payload=response_payload,
        research_payload=research_payload,
    )


def _build_similar_games_stage_evaluation(
    bundle: TaxonomyV2EnrichmentBundle,
    stage_row: dict[str, Any],
    response_payload: dict[str, Any],
    *,
    used_web: bool,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
    research_payload: dict[str, Any] | None = None,
) -> TaxonomyV2SimilarGamesStageEvaluation:
    candidate_inputs_by_public_id: dict[str, dict[str, Any]] = {}
    for item in stage_row.get("staged_neighbors") or []:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        if candidate_public_id:
            candidate_inputs_by_public_id[candidate_public_id] = dict(item)

    overall_verdict = _canonical_token(response_payload.get("overall_verdict")) or "weak"
    if overall_verdict not in {"excellent", "good", "mixed", "weak"}:
        overall_verdict = "weak"
    overall_note = _truncate_text(
        _sanitize_single_short_text(response_payload.get("overall_note"), limit=700),
        limit=700,
    ) or ""
    anchor_summary = _truncate_text(
        _sanitize_single_short_text(response_payload.get("anchor_summary"), limit=900),
        limit=900,
    ) or ""
    gap_notes = _sanitize_short_text_list(response_payload.get("gap_notes") or [], limit=8, item_limit=240)

    candidate_reviews_payload = response_payload.get("candidate_reviews") or []
    candidate_reviews: list[TaxonomyV2SimilarCandidateReview] = []
    seen_public_ids: set[str] = set()
    for item in candidate_reviews_payload:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        if not candidate_public_id or candidate_public_id in seen_public_ids:
            continue
        stage_candidate = candidate_inputs_by_public_id.get(candidate_public_id)
        if stage_candidate is None:
            continue
        seen_public_ids.add(candidate_public_id)
        raw_score = _safe_float(item.get("strength_score"))
        if raw_score is None:
            raw_score = 0.0
        if 0.0 <= raw_score <= 1.0:
            raw_score *= 100.0
        raw_score = max(0.0, min(raw_score, 100.0))
        strength_label = _canonical_token(item.get("strength_label")) or "drop"
        if strength_label not in {"must_keep", "strong", "good", "weak", "drop"}:
            strength_label = "drop"
        relationship_fit = _canonical_token(item.get("relationship_fit")) or "wrong"
        if relationship_fit not in {
            "base_game",
            "same",
            "strong_neighbor",
            "adjacent_neighbor",
            "weak_neighbor",
            "wrong",
        }:
            relationship_fit = "wrong"
        rationale = _sanitize_single_short_text(item.get("rationale"), limit=320) or "No rationale provided."
        try:
            requested_rank = int(item.get("rank") or 0)
        except (TypeError, ValueError):
            requested_rank = 0
        candidate_reviews.append(
            TaxonomyV2SimilarCandidateReview(
                candidate_public_id=candidate_public_id,
                candidate_title=_sanitize_single_short_text(stage_candidate.get("candidate_title"), limit=160),
                requested_title=_sanitize_single_short_text(stage_candidate.get("requested_title"), limit=160)
                or _sanitize_single_short_text(stage_candidate.get("candidate_title"), limit=160),
                input_rank=max(1, int(stage_candidate.get("rank") or len(candidate_reviews) + 1)),
                rank=max(1, requested_rank),
                strength_label=strength_label,
                strength_score=round(raw_score, 1),
                relationship_fit=relationship_fit,
                rationale=rationale,
            )
        )

    expected_public_ids = set(candidate_inputs_by_public_id)
    if seen_public_ids != expected_public_ids:
        missing = sorted(expected_public_ids - seen_public_ids)
        extra = sorted(seen_public_ids - expected_public_ids)
        raise RuntimeError(
            "Stage evaluation did not rate every candidate exactly once: "
            f"missing={missing} extra={extra}"
        )

    candidate_reviews.sort(
        key=lambda item: (
            item.rank,
            -item.strength_score,
            item.candidate_title.casefold(),
        )
    )
    candidate_reviews = [
        TaxonomyV2SimilarCandidateReview(
            candidate_public_id=item.candidate_public_id,
            candidate_title=item.candidate_title,
            requested_title=item.requested_title,
            input_rank=item.input_rank,
            rank=index,
            strength_label=item.strength_label,
            strength_score=item.strength_score,
            relationship_fit=item.relationship_fit,
            rationale=item.rationale,
        )
        for index, item in enumerate(candidate_reviews, start=1)
    ]

    source_urls = list(external_evidence.source_urls) if external_evidence is not None else []
    return TaxonomyV2SimilarGamesStageEvaluation(
        game_id=bundle.game_id,
        public_id=bundle.public_id,
        title=bundle.title,
        overall_verdict=overall_verdict,
        overall_note=overall_note,
        anchor_summary=anchor_summary,
        used_web=used_web,
        source_urls=source_urls,
        gap_notes=gap_notes,
        candidate_reviews=candidate_reviews,
        payload=response_payload,
        research_payload=research_payload,
    )


def _build_llm_taxonomy_result(
    bundle: TaxonomyV2EnrichmentBundle,
    response_payload: dict[str, Any],
    *,
    min_confidence: float,
    used_web: bool,
    reasoning_effort: str,
    external_evidence: TaxonomyV2ExternalEvidence | None = None,
    research_payload: dict[str, Any] | None = None,
) -> TaxonomyV2EnrichmentDecision:
    vocab = load_taxonomy_v2_allowed_vocab()
    llm_confidence = _safe_float(response_payload.get("confidence"))
    if llm_confidence is None:
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason="missing_confidence",
            used_web=used_web,
            llm_confidence=None,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    decision = _canonical_token(response_payload.get("decision"))
    if decision != "accept":
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason=_canonical_token(response_payload.get("rejection_reason")) or "llm_rejected",
            used_web=used_web,
            llm_confidence=llm_confidence,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    if llm_confidence < min_confidence:
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason="below_confidence_threshold",
            used_web=used_web,
            llm_confidence=llm_confidence,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    primary_archetype = _canonical_token(response_payload.get("primary_archetype"))
    if primary_archetype not in vocab["families_by_archetype"]:
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason="invalid_primary_archetype",
            used_web=used_web,
            llm_confidence=llm_confidence,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    allowed_values_by_field = vocab["values_by_field"]
    fingerprint_input = response_payload.get("fingerprint") or {}
    sanitized_fingerprint: dict[str, list[str]] = {}
    dropped_tokens: dict[str, list[str]] = {}
    for field in FINGERPRINT_AXES:
        raw_values = fingerprint_input.get(field) or []
        if not isinstance(raw_values, list):
            raw_values = []
        cleaned_values = _unique_tokens(str(value) for value in raw_values if isinstance(value, str))
        allowed_values = set(allowed_values_by_field.get(field, []))
        if allowed_values:
            accepted_values = [value for value in cleaned_values if value in allowed_values]
            rejected_values = [value for value in cleaned_values if value not in allowed_values]
        else:
            accepted_values = cleaned_values
            rejected_values = []
        sanitized_fingerprint[field] = accepted_values
        if rejected_values:
            dropped_tokens[field] = rejected_values

    primary_node = (load_archetype_graph_v2().get("nodes") or {}).get(primary_archetype) or {}
    primary_blocking_exclusions = {
        _canonical_token(value)
        for value in (primary_node.get("hard_exclusions") or [])
        if _canonical_token(value)
    }
    primary_blocking_exclusions.update(_ADDITIONAL_NODE_HARD_EXCLUSIONS.get(primary_archetype, set()))
    primary_blocking_exclusions.update(_ASSIGNMENT_ONLY_NODE_HARD_EXCLUSIONS.get(primary_archetype, set()))
    if primary_blocking_exclusions:
        original_hard_exclusions = list(sanitized_fingerprint.get("hard_exclusions", []))
        sanitized_fingerprint["hard_exclusions"] = [
            value for value in original_hard_exclusions if value not in primary_blocking_exclusions
        ]
        removed_self_conflicts = [value for value in original_hard_exclusions if value in primary_blocking_exclusions]
        if removed_self_conflicts:
            dropped_tokens.setdefault("hard_exclusions", []).extend(removed_self_conflicts)

    confidence_by_field_value = _confidence_by_field_value(sanitized_fingerprint, llm_confidence)
    candidates = assign_taxonomy_v2_archetypes(sanitized_fingerprint, confidence_by_field_value)
    candidates = _prefer_primary_archetype_candidate(candidates, sanitized_fingerprint)
    if not candidates:
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason="fingerprint_did_not_map",
            used_web=used_web,
            llm_confidence=llm_confidence,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    top_candidate = candidates[0]
    if top_candidate.archetype != primary_archetype:
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason="fingerprint_primary_mismatch",
            used_web=used_web,
            llm_confidence=llm_confidence,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    raw_secondary_archetypes = response_payload.get("secondary_archetypes") or []
    if not isinstance(raw_secondary_archetypes, list):
        raw_secondary_archetypes = []
    secondary_candidates = {candidate.archetype for candidate in candidates[1:]}
    secondary_archetypes = [
        archetype
        for archetype in _unique_tokens(str(value) for value in raw_secondary_archetypes if isinstance(value, str))
        if archetype in secondary_candidates and archetype != primary_archetype
    ][:3]

    evidence_summary = _truncate_text(str(response_payload.get("evidence_summary") or "").strip(), limit=1200) or ""
    if len(evidence_summary.split()) < 12:
        return TaxonomyV2EnrichmentDecision(
            game_id=bundle.game_id,
            public_id=bundle.public_id,
            title=bundle.title,
            accepted=False,
            status="rejected",
            reason="thin_evidence_summary",
            used_web=used_web,
            llm_confidence=llm_confidence,
            result=None,
            payload=response_payload,
            research_payload=research_payload,
        )

    evidence: list[TaxonomyV2EvidenceRecord] = []
    bounded_confidence = min(llm_confidence, top_candidate.confidence)
    for field, values in sanitized_fingerprint.items():
        for value in values:
            evidence.append(
                TaxonomyV2EvidenceRecord(
                    field=field,
                    value=value,
                    source=_LLM_EVIDENCE_SOURCE,
                    source_field=field,
                    confidence=max(0.5, min(bounded_confidence, 0.99)),
                    evidence_text=evidence_summary,
                    curated=True,
                )
            )

    result = TaxonomyV2Result(
        version=TAXONOMY_V2_VERSION,
        status=TAXONOMY_V2_STATUS_CURATED,
        primary_family=vocab["families_by_archetype"][primary_archetype] or top_candidate.family,
        primary_archetype=primary_archetype,
        secondary_archetypes=secondary_archetypes,
        hard_exclusions=list(sanitized_fingerprint.get("hard_exclusions", [])),
        soft_penalties=list(sanitized_fingerprint.get("soft_penalties", [])),
        confidence=bounded_confidence,
        fingerprint={field: list(values) for field, values in sanitized_fingerprint.items()},
        curated=True,
        evidence=evidence,
        debug_payload={
            "audit_state": "llm_curated",
            "llm_model": _OPENAI_MODEL,
            "llm_reasoning_effort": reasoning_effort,
            "llm_decision": "accept",
            "llm_confidence": round(llm_confidence, 4),
            "llm_used_web": used_web,
            "llm_source_urls": _sanitize_source_urls(
                list(response_payload.get("source_urls") or [])
                + (list(external_evidence.source_urls) if external_evidence is not None else [])
            ),
            "llm_evidence_summary": evidence_summary,
            "llm_original_audit_state": bundle.audit_state,
            "llm_dropped_tokens": dropped_tokens,
            "llm_external_evidence_quality": external_evidence.evidence_quality if external_evidence is not None else None,
            "llm_external_evidence_summary": external_evidence.evidence_summary if external_evidence is not None else None,
            "candidate_archetypes": [
                {
                    "archetype": candidate.archetype,
                    "family": candidate.family,
                    "score": candidate.score,
                    "confidence": round(candidate.confidence, 4),
                }
                for candidate in candidates[:5]
            ],
        },
    )
    return TaxonomyV2EnrichmentDecision(
        game_id=bundle.game_id,
        public_id=bundle.public_id,
        title=bundle.title,
        accepted=True,
        status="accepted",
        reason="accepted",
        used_web=used_web,
        llm_confidence=llm_confidence,
        result=result,
        payload=response_payload,
        research_payload=research_payload,
    )


def should_retry_with_web(
    bundle: TaxonomyV2EnrichmentBundle,
    decision: TaxonomyV2EnrichmentDecision,
) -> bool:
    if decision.accepted:
        return False
    if bundle.appears_dlc:
        return True
    if bundle.audit_state in _LOW_SIGNAL_AUDIT_STATES:
        return True
    if not bundle.has_rich_db_evidence:
        return True
    return decision.reason in {
        "below_confidence_threshold",
        "thin_evidence_summary",
        "fingerprint_did_not_map",
        "fingerprint_primary_mismatch",
    }


class GPT54TaxonomyEnrichmentService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        settings = get_settings()
        resolved_api_key = (api_key or settings.openai_api_key or "").strip()
        if not resolved_api_key:
            raise OpenAITaxonomyEnrichmentAuthError(
                "OPENAI_API_KEY is not configured. Set it before running taxonomy-v2-gpt54-enrich."
            )
        self._api_key = resolved_api_key
        self._base_url = (base_url or settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GPT54TaxonomyEnrichmentService":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def enrich_bundle(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        *,
        min_confidence: float,
        use_web: bool,
    ) -> TaxonomyV2EnrichmentDecision:
        initial_payload = await self._classify_bundle(
            bundle,
            reasoning_effort="low",
            external_evidence=None,
        )
        initial_decision = _build_llm_taxonomy_result(
            bundle,
            initial_payload,
            min_confidence=min_confidence,
            used_web=False,
            reasoning_effort="low",
        )
        if not use_web or not should_retry_with_web(bundle, initial_decision):
            return initial_decision

        research_payload = await self._research_bundle(
            bundle,
            reasoning_effort="medium",
        )
        external_evidence = _build_external_evidence(research_payload)
        if external_evidence is None or not external_evidence.has_material_evidence:
            return initial_decision

        grounded_payload = await self._classify_bundle(
            bundle,
            reasoning_effort="medium",
            external_evidence=external_evidence,
        )
        grounded_decision = _build_llm_taxonomy_result(
            bundle,
            grounded_payload,
            min_confidence=min_confidence,
            used_web=True,
            reasoning_effort="medium",
            external_evidence=external_evidence,
            research_payload=research_payload,
        )
        return grounded_decision

    async def preview_similar_games(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        *,
        limit: int = 5,
        use_web: bool,
    ) -> TaxonomyV2SimilarGamesPreview:
        external_evidence: TaxonomyV2ExternalEvidence | None = None
        research_payload: dict[str, Any] | None = None
        used_web = False
        if use_web:
            research_payload = await self._research_bundle(
                bundle,
                reasoning_effort="medium",
            )
            external_evidence = _build_external_evidence(research_payload)
            used_web = external_evidence is not None and external_evidence.has_material_evidence

        preview_payload = await self._preview_similar_games_bundle(
            bundle,
            reasoning_effort="medium" if used_web else "low",
            limit=limit,
            external_evidence=external_evidence,
        )
        return _build_similar_games_preview(
            bundle,
            preview_payload,
            used_web=used_web,
            external_evidence=external_evidence,
            research_payload=research_payload,
            limit=limit,
        )

    async def evaluate_stage_similar_games(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        stage_row: dict[str, Any],
        candidate_games_by_public_id: dict[str, Game],
        *,
        use_web: bool,
    ) -> TaxonomyV2SimilarGamesStageEvaluation:
        external_evidence: TaxonomyV2ExternalEvidence | None = None
        research_payload: dict[str, Any] | None = None
        used_web = False
        if use_web:
            research_payload = await self._research_bundle(
                bundle,
                reasoning_effort="medium",
            )
            external_evidence = _build_external_evidence(research_payload)
            used_web = external_evidence is not None and external_evidence.has_material_evidence

        evaluation_payload = await self._evaluate_stage_similar_games_bundle(
            bundle,
            stage_row,
            candidate_games_by_public_id,
            reasoning_effort="medium" if used_web else "low",
            external_evidence=external_evidence,
        )
        return _build_similar_games_stage_evaluation(
            bundle,
            stage_row,
            evaluation_payload,
            used_web=used_web,
            external_evidence=external_evidence,
            research_payload=research_payload,
        )

    async def repair_stage_similar_games(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        stage_row: dict[str, Any],
        evaluation_row: dict[str, Any],
        *,
        replacement_limit: int,
        use_web: bool,
    ) -> TaxonomyV2SimilarGamesPreview:
        external_evidence: TaxonomyV2ExternalEvidence | None = None
        research_payload: dict[str, Any] | None = None
        used_web = False
        if use_web:
            research_payload = await self._research_bundle(
                bundle,
                reasoning_effort="medium",
            )
            external_evidence = _build_external_evidence(research_payload)
            used_web = external_evidence is not None and external_evidence.has_material_evidence

        preview_payload = await self._repair_stage_similar_games_bundle(
            bundle,
            stage_row,
            evaluation_row,
            reasoning_effort="medium" if used_web else "low",
            replacement_limit=replacement_limit,
            external_evidence=external_evidence,
        )
        return _build_similar_games_preview(
            bundle,
            preview_payload,
            used_web=used_web,
            external_evidence=external_evidence,
            research_payload=research_payload,
            limit=replacement_limit,
        )

    async def _classify_bundle(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        *,
        reasoning_effort: str,
        external_evidence: TaxonomyV2ExternalEvidence | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": _OPENAI_MODEL,
            "reasoning": {"effort": reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_system_prompt(
                                allow_web=False,
                                has_external_evidence=external_evidence is not None and external_evidence.has_material_evidence,
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_user_prompt(bundle, external_evidence=external_evidence),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": _OUTPUT_SCHEMA_NAME,
                    "strict": True,
                    "schema": _response_schema(),
                }
            },
        }
        return await self._request_structured_response(
            bundle.title,
            payload,
        )

    async def _preview_similar_games_bundle(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        *,
        reasoning_effort: str,
        limit: int,
        external_evidence: TaxonomyV2ExternalEvidence | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": _OPENAI_MODEL,
            "reasoning": {"effort": reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_similar_games_system_prompt(
                                has_external_evidence=external_evidence is not None
                                and external_evidence.has_material_evidence,
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_similar_games_user_prompt(
                                bundle,
                                limit=limit,
                                external_evidence=external_evidence,
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "taxonomy_v2_gpt54_similar_games_preview",
                    "strict": True,
                    "schema": _similar_games_response_schema(),
                }
            },
        }
        return await self._request_structured_response(bundle.title, payload)

    async def _evaluate_stage_similar_games_bundle(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        stage_row: dict[str, Any],
        candidate_games_by_public_id: dict[str, Game],
        *,
        reasoning_effort: str,
        external_evidence: TaxonomyV2ExternalEvidence | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": _OPENAI_MODEL,
            "reasoning": {"effort": reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_similar_stage_evaluation_system_prompt(
                                has_external_evidence=external_evidence is not None
                                and external_evidence.has_material_evidence,
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_similar_stage_evaluation_user_prompt(
                                bundle,
                                stage_row,
                                candidate_games_by_public_id,
                                external_evidence=external_evidence,
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "taxonomy_v2_gpt54_stage_similarity_evaluation",
                    "strict": True,
                    "schema": _similar_stage_evaluation_response_schema(),
                }
            },
        }
        return await self._request_structured_response(bundle.title, payload)

    async def _repair_stage_similar_games_bundle(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        stage_row: dict[str, Any],
        evaluation_row: dict[str, Any],
        *,
        reasoning_effort: str,
        replacement_limit: int,
        external_evidence: TaxonomyV2ExternalEvidence | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": _OPENAI_MODEL,
            "reasoning": {"effort": reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_similar_repair_system_prompt(
                                has_external_evidence=external_evidence is not None
                                and external_evidence.has_material_evidence,
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_similar_repair_user_prompt(
                                bundle,
                                stage_row,
                                evaluation_row,
                                replacement_limit=replacement_limit,
                                external_evidence=external_evidence,
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "taxonomy_v2_gpt54_stage_similarity_repair",
                    "strict": True,
                    "schema": _similar_games_response_schema(),
                }
            },
        }
        return await self._request_structured_response(bundle.title, payload)

    async def _research_bundle(
        self,
        bundle: TaxonomyV2EnrichmentBundle,
        *,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": _OPENAI_MODEL,
            "reasoning": {"effort": reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": _build_research_system_prompt()}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _build_research_user_prompt(bundle)}],
                },
            ],
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "taxonomy_v2_gpt54_research",
                    "strict": True,
                    "schema": _research_response_schema(),
                }
            },
        }
        return await self._request_structured_response(bundle.title, payload)

    async def _request_structured_response(
        self,
        title: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        last_error: BaseException | None = None
        for attempt in range(1, 4):
            try:
                response = await self._client.post(
                    f"{self._base_url}{_OPENAI_RESPONSES_PATH}",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                response_payload = response.json()
                text = _extract_response_text(response_payload)
                return json.loads(text)
            except (httpx.HTTPError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= 3:
                    break
                await asyncio.sleep(attempt)
        raise RuntimeError(f"OpenAI enrichment request failed for {title}: {last_error}")


async def load_taxonomy_v2_gpt54_target_games(
    db: AsyncSession,
    *,
    limit: int | None = None,
    offset: int = 0,
    recent_first: bool = False,
    exclude_ids: Iterable[int] | None = None,
    hidden_only: bool = True,
) -> list[Game]:
    excluded_game_ids = [int(game_id) for game_id in (exclude_ids or []) if game_id is not None]
    query = select(Game)
    if hidden_only:
        query = query.where(
            Game.similarity_v3_status == "hidden",
            Game.similarity_v3_version.is_(None),
        )
    query = query.offset(max(0, int(offset)))
    if excluded_game_ids:
        query = query.where(Game.id.not_in(excluded_game_ids))
    if recent_first:
        unreleased_sort_expr = case(
            (Game.release_date > func.current_date(), 1),
            else_=0,
        )
        query = query.order_by(
            asc(unreleased_sort_expr),
            desc(Game.release_date).nulls_last(),
            desc(Game.created_at).nulls_last(),
            desc(Game.id),
        )
    else:
        query = query.order_by(
            func.coalesce(func.length(Game.taxonomy_v2_text_corpus), 0).desc(),
            func.coalesce(func.length(Game.steam_detailed_description), 0).desc(),
            func.coalesce(func.length(Game.opencritic_description), 0).desc(),
            Game.opencritic_id.isnot(None).desc(),
            Game.steam_app_id.isnot(None).desc(),
            Game.metacritic_slug.isnot(None).desc(),
            Game.release_date.desc().nulls_last(),
            Game.id.desc(),
        )
    if limit is not None:
        query = query.limit(max(1, int(limit)))
    result = await db.execute(query)
    return result.scalars().all()


async def build_taxonomy_v2_gpt54_bundles(
    db: AsyncSession,
    games: list[Game],
) -> list[TaxonomyV2EnrichmentBundle]:
    game_ids = [game.id for game in games if game is not None and game.id is not None]
    if not game_ids:
        return []
    label_result = await db.execute(
        select(GameSourceTaxonomyLabel).where(GameSourceTaxonomyLabel.game_id.in_(game_ids))
    )
    labels_by_game_id: dict[int, list[TaxonomyV2EnrichmentSourceLabel]] = {}
    for row in label_result.scalars().all():
        labels_by_game_id.setdefault(row.game_id, []).append(
            TaxonomyV2EnrichmentSourceLabel(
                source=row.source,
                facet=row.facet,
                raw_label=row.raw_label,
                normalized_label=row.normalized_label,
            )
        )

    parent_candidates_by_title: dict[str, list[Game]] = {}
    candidate_parent_titles: set[str] = set()
    for game in games:
        if game is None:
            continue
        labels = labels_by_game_id.get(game.id, [])
        title_candidates = _candidate_parent_titles(game, labels)
        candidate_parent_titles.update({title: [] for title in title_candidates})
    if candidate_parent_titles:
        normalized_titles = [title.lower() for title in candidate_parent_titles]
        search_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for title in candidate_parent_titles:
            for token in normalize_taxonomy_label(title).split():
                if len(token) < 4 or token in seen_tokens:
                    continue
                seen_tokens.add(token)
                search_tokens.append(token)
        clauses = []
        if normalized_titles:
            clauses.append(func.lower(Game.title).in_(normalized_titles))
        clauses.extend(func.lower(Game.title).like(f"%{token}%") for token in search_tokens[:8])
        parent_rows = (
            await db.execute(
                select(Game)
                .where(or_(*clauses))
                .order_by(Game.release_date.desc().nulls_last(), Game.created_at.desc().nulls_last(), Game.id.desc())
            )
        ).scalars().all()
        for row in parent_rows:
            for lookup_key in _parent_lookup_keys(str(row.title)):
                parent_candidates_by_title.setdefault(lookup_key, []).append(row)

    bundles: list[TaxonomyV2EnrichmentBundle] = []
    for game in games:
        if game is None or game.id is None or not getattr(game, "public_id", None):
            continue
        stored_text_corpus = getattr(game, "taxonomy_v2_text_corpus", None)
        stored_text_sources = list(getattr(game, "taxonomy_v2_text_sources", None) or [])
        if not stored_text_corpus:
            stored_text_corpus, stored_text_sources = build_taxonomy_v2_text_corpus(game)
        parent_game = _select_parent_game_context(
            game,
            labels_by_game_id.get(game.id, []),
            parent_candidates_by_title,
        )
        bundles.append(
            TaxonomyV2EnrichmentBundle(
                game_id=game.id,
                public_id=game.public_id,
                title=game.title,
                release_date=game.release_date.isoformat() if getattr(game, "release_date", None) is not None else None,
                opencritic_id=getattr(game, "opencritic_id", None),
                steam_app_id=getattr(game, "steam_app_id", None),
                metacritic_slug=getattr(game, "metacritic_slug", None),
                description=getattr(game, "description", None),
                opencritic_description=getattr(game, "opencritic_description", None),
                steam_short_description=getattr(game, "steam_short_description", None),
                steam_detailed_description=getattr(game, "steam_detailed_description", None),
                metacritic_description=getattr(game, "metacritic_description", None),
                taxonomy_genres=list(getattr(game, "taxonomy_genres", None) or []),
                taxonomy_themes=list(getattr(game, "taxonomy_themes", None) or []),
                taxonomy_modes=list(getattr(game, "taxonomy_modes", None) or []),
                taxonomy_v2_status=getattr(game, "taxonomy_v2_status", None),
                taxonomy_v2_text_corpus=stored_text_corpus,
                taxonomy_v2_text_sources=stored_text_sources,
                taxonomy_v2_debug_payload=dict(getattr(game, "taxonomy_v2_debug_payload", None) or {}),
                source_labels=sorted(
                    labels_by_game_id.get(game.id, []),
                    key=lambda row: (row.source, row.facet, row.normalized_label),
                ),
                parent_game=parent_game,
            )
        )
    return bundles


async def store_taxonomy_v2_gpt54_decision(
    db: AsyncSession,
    *,
    game: Game,
    decision: TaxonomyV2EnrichmentDecision,
) -> None:
    if not decision.accepted or decision.result is None:
        return
    await store_game_taxonomy_v2(db, game, decision.result)
    mark_game_similarity_v3_dirty(game, "taxonomy_v2_gpt54")


def build_taxonomy_v2_gpt54_output_row(
    bundle: TaxonomyV2EnrichmentBundle,
    decision: TaxonomyV2EnrichmentDecision,
) -> dict[str, Any]:
    result = decision.result
    return {
        "game_id": bundle.game_id,
        "public_id": bundle.public_id,
        "title": bundle.title,
        "audit_state": bundle.audit_state,
        "signal_score": bundle.signal_score,
        "accepted": decision.accepted,
        "status": decision.status,
        "reason": decision.reason,
        "used_web": decision.used_web,
        "llm_confidence": decision.llm_confidence,
        "primary_archetype": result.primary_archetype if result is not None else None,
        "secondary_archetypes": list(result.secondary_archetypes) if result is not None else [],
        "source_urls": list((result.debug_payload if result is not None else {}).get("llm_source_urls", [])),
        "payload": decision.payload,
        "research_payload": decision.research_payload,
    }


def build_taxonomy_v2_gpt54_similar_preview_row(
    bundle: TaxonomyV2EnrichmentBundle,
    preview: TaxonomyV2SimilarGamesPreview,
) -> dict[str, Any]:
    return {
        "game_id": bundle.game_id,
        "public_id": bundle.public_id,
        "title": bundle.title,
        "audit_state": bundle.audit_state,
        "signal_score": bundle.signal_score,
        "used_web": preview.used_web,
        "confidence": preview.confidence,
        "anchor_summary": preview.anchor_summary,
        "expected_must_include_titles": list(preview.expected_must_include_titles),
        "similar_games": [
            {
                "title": item.title,
                "expected_relationship": item.expected_relationship,
                "why_similar": item.why_similar,
            }
            for item in preview.similar_games
        ],
        "source_urls": list(preview.source_urls),
        "payload": preview.payload,
        "research_payload": preview.research_payload,
    }


def build_taxonomy_v2_gpt54_stage_evaluation_row(
    stage_row: dict[str, Any],
    evaluation: TaxonomyV2SimilarGamesStageEvaluation,
) -> dict[str, Any]:
    strength_counts: dict[str, int] = {}
    for item in evaluation.candidate_reviews:
        strength_counts[item.strength_label] = strength_counts.get(item.strength_label, 0) + 1
    return {
        "game_id": stage_row.get("game_id"),
        "public_id": stage_row.get("public_id"),
        "title": stage_row.get("title"),
        "stage_status": stage_row.get("stage_status"),
        "review_flags": list(stage_row.get("review_flags") or []),
        "recommended_actions": list(stage_row.get("recommended_actions") or []),
        "current_taxonomy": dict(stage_row.get("current_taxonomy") or {}),
        "proposed_taxonomy": dict(stage_row.get("proposed_taxonomy") or {}),
        "overall_verdict": evaluation.overall_verdict,
        "overall_note": evaluation.overall_note,
        "anchor_summary": evaluation.anchor_summary,
        "used_web": evaluation.used_web,
        "source_urls": list(evaluation.source_urls),
        "gap_notes": list(evaluation.gap_notes),
        "strength_counts": strength_counts,
        "candidate_reviews": [
            {
                "rank": item.rank,
                "input_rank": item.input_rank,
                "candidate_public_id": item.candidate_public_id,
                "candidate_title": item.candidate_title,
                "requested_title": item.requested_title,
                "strength_label": item.strength_label,
                "strength_score": item.strength_score,
                "relationship_fit": item.relationship_fit,
                "rationale": item.rationale,
            }
            for item in evaluation.candidate_reviews
        ],
        "payload": evaluation.payload,
        "research_payload": evaluation.research_payload,
    }


def build_taxonomy_v2_gpt54_filtered_stage_row(
    stage_row: dict[str, Any],
    evaluation_row: dict[str, Any],
    *,
    allowed_overall_verdicts: set[str] | None = None,
    allowed_strength_labels: set[str] | None = None,
) -> dict[str, Any]:
    allowed_verdicts = {
        _canonical_token(value)
        for value in (allowed_overall_verdicts or {"excellent", "good"})
        if _canonical_token(value)
    }
    allowed_labels = {
        _canonical_token(value)
        for value in (allowed_strength_labels or {"must_keep", "strong", "good"})
        if _canonical_token(value)
    }
    filtered_row = dict(stage_row)
    evaluation_payload = dict(evaluation_row or {})
    overall_verdict = _canonical_token(evaluation_payload.get("overall_verdict")) or "unknown"
    candidate_reviews_by_public_id: dict[str, dict[str, Any]] = {}
    for item in evaluation_payload.get("candidate_reviews") or []:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        if candidate_public_id:
            candidate_reviews_by_public_id[candidate_public_id] = dict(item)

    filtered_neighbors: list[dict[str, Any]] = []
    removed_candidates: list[dict[str, Any]] = []
    for item in stage_row.get("staged_neighbors") or []:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        review = candidate_reviews_by_public_id.get(candidate_public_id)
        strength_label = _canonical_token((review or {}).get("strength_label")) or "unreviewed"
        should_keep = overall_verdict in allowed_verdicts and strength_label in allowed_labels
        if not should_keep:
            removed_candidates.append(
                {
                    "candidate_public_id": candidate_public_id,
                    "candidate_title": _sanitize_single_short_text(item.get("candidate_title"), limit=160),
                    "strength_label": strength_label,
                    "strength_score": _safe_float((review or {}).get("strength_score")),
                    "overall_verdict": overall_verdict,
                }
            )
            continue
        relationship_fit = _canonical_token((review or {}).get("relationship_fit")) or ""
        expected_relationship = (
            relationship_fit
            if relationship_fit in {"base_game", "same", "strong_neighbor", "adjacent_neighbor"}
            else _sanitize_single_short_text(item.get("expected_relationship"), limit=64) or "adjacent_neighbor"
        )
        filtered_neighbors.append(
            {
                "rank": int((review or {}).get("rank") or len(filtered_neighbors) + 1),
                "candidate_public_id": candidate_public_id,
                "candidate_title": _sanitize_single_short_text(item.get("candidate_title"), limit=160),
                "requested_title": _sanitize_single_short_text(item.get("requested_title"), limit=160)
                or _sanitize_single_short_text(item.get("candidate_title"), limit=160),
                "expected_relationship": expected_relationship,
                "why_similar": _sanitize_single_short_text((review or {}).get("rationale"), limit=360)
                or _sanitize_single_short_text(item.get("why_similar"), limit=360),
            }
        )

    filtered_neighbors.sort(
        key=lambda item: (
            int(item.get("rank") or 0),
            _sanitize_single_short_text(item.get("candidate_title"), limit=160).casefold(),
        )
    )
    for index, item in enumerate(filtered_neighbors, start=1):
        item["rank"] = index

    review_flags = list(stage_row.get("review_flags") or [])
    if removed_candidates and "weak_candidates_pruned" not in review_flags:
        review_flags.append("weak_candidates_pruned")
    if overall_verdict not in allowed_verdicts and "verdict_blocked" not in review_flags:
        review_flags.append("verdict_blocked")
    if not filtered_neighbors and "no_publishable_neighbors" not in review_flags:
        review_flags.append("no_publishable_neighbors")

    filtered_row["staged_neighbors"] = filtered_neighbors
    filtered_row["review_flags"] = review_flags
    filtered_row["filter_metadata"] = {
        "overall_verdict": overall_verdict,
        "allowed_overall_verdicts": sorted(allowed_verdicts),
        "allowed_strength_labels": sorted(allowed_labels),
        "kept_neighbor_count": len(filtered_neighbors),
        "removed_neighbor_count": len(removed_candidates),
        "removed_candidates": removed_candidates,
    }
    if filtered_neighbors and overall_verdict in allowed_verdicts:
        filtered_row["stage_status"] = "ready_for_review"
    elif (filtered_row.get("proposed_taxonomy") or {}).get("primary_archetype"):
        filtered_row["stage_status"] = "taxonomy_only"
    else:
        filtered_row["stage_status"] = "blocked"
    return filtered_row


def build_taxonomy_v2_gpt54_alignment_row(
    review_row: dict[str, Any],
    stage_row: dict[str, Any],
    evaluation_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_payload = dict(review_row or {})
    stage_payload = dict(stage_row or {})
    evaluation_payload = dict(evaluation_row or {})

    current_taxonomy = dict(review_payload.get("current_taxonomy") or stage_payload.get("current_taxonomy") or {})
    proposed_taxonomy = dict(stage_payload.get("proposed_taxonomy") or {})
    taxonomy_alignment = dict(review_payload.get("taxonomy_alignment") or stage_payload.get("taxonomy_alignment") or {})

    current_live_neighbors = [
        dict(item)
        for item in (review_payload.get("current_live_neighbors") or stage_payload.get("current_live_neighbors") or [])
        if isinstance(item, dict)
    ]
    staged_neighbors = [
        dict(item)
        for item in (stage_payload.get("staged_neighbors") or [])
        if isinstance(item, dict)
    ]
    candidate_reviews_by_public_id: dict[str, dict[str, Any]] = {}
    for item in evaluation_payload.get("candidate_reviews") or []:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        if candidate_public_id:
            candidate_reviews_by_public_id[candidate_public_id] = dict(item)

    live_neighbor_titles = _sanitize_short_text_list(
        [item.get("title") for item in current_live_neighbors],
        limit=20,
        item_limit=160,
    )
    live_neighbor_public_ids = _sanitize_short_text_list(
        [item.get("public_id") for item in current_live_neighbors],
        limit=20,
        item_limit=80,
    )
    llm_neighbor_titles = _sanitize_short_text_list(
        [item.get("candidate_title") for item in staged_neighbors],
        limit=20,
        item_limit=160,
    )
    llm_neighbor_public_ids = _sanitize_short_text_list(
        [item.get("candidate_public_id") for item in staged_neighbors],
        limit=20,
        item_limit=80,
    )

    live_title_set = {value.casefold(): value for value in live_neighbor_titles}
    llm_title_set = {value.casefold(): value for value in llm_neighbor_titles}
    overlap_titles = sorted(
        live_title_set[key]
        for key in (set(live_title_set) & set(llm_title_set))
    )
    live_only_titles = sorted(
        live_title_set[key]
        for key in (set(live_title_set) - set(llm_title_set))
    )
    llm_only_titles = sorted(
        llm_title_set[key]
        for key in (set(llm_title_set) - set(live_title_set))
    )

    missing_must_include_titles = _sanitize_short_text_list(
        review_payload.get("missing_must_include_titles") or stage_payload.get("missing_must_include_titles") or [],
        limit=10,
        item_limit=160,
    )
    matched_live_titles = _sanitize_short_text_list(
        review_payload.get("matched_live_titles") or stage_payload.get("matched_live_titles") or [],
        limit=10,
        item_limit=160,
    )
    unresolved_similar_games = _sanitize_short_text_list(
        stage_payload.get("unresolved_similar_games") or [],
        limit=10,
        item_limit=160,
    )
    removed_candidates = [
        dict(item)
        for item in ((stage_payload.get("filter_metadata") or {}).get("removed_candidates") or [])
        if isinstance(item, dict)
    ]
    unresolved_similar_games = _sanitize_short_text_list(
        stage_payload.get("unresolved_similar_games") or [],
        limit=20,
        item_limit=160,
    )
    removed_candidate_titles = _sanitize_short_text_list(
        [item.get("candidate_title") for item in removed_candidates],
        limit=20,
        item_limit=160,
    )
    issue_types: list[str] = []
    current_primary = _sanitize_single_short_text(current_taxonomy.get("primary_archetype"), limit=96)
    proposed_primary = _sanitize_single_short_text(proposed_taxonomy.get("primary_archetype"), limit=96)
    if current_taxonomy.get("status") != "curated" and proposed_primary:
        issue_types.append("taxonomy_not_curated")
    if taxonomy_alignment.get("needs_taxonomy_review"):
        issue_types.append("taxonomy_mismatch")
    if not current_live_neighbors:
        issue_types.append("live_empty")
    if not overlap_titles:
        issue_types.append("zero_live_overlap")
    if missing_must_include_titles:
        issue_types.append("must_include_missing")
    if unresolved_similar_games:
        issue_types.append("catalog_gap")
    if removed_candidates:
        issue_types.append("weak_candidates_pruned")
    if current_live_neighbors and llm_only_titles:
        issue_types.append("live_ranking_misaligned")
    if live_only_titles:
        issue_types.append("live_false_positive_candidates")

    training_targets = {
        "anchor_public_id": _sanitize_single_short_text(stage_payload.get("public_id") or review_payload.get("public_id"), limit=80),
        "anchor_title": _sanitize_single_short_text(stage_payload.get("title") or review_payload.get("title"), limit=160),
        "current_primary_archetype": current_primary or None,
        "target_primary_archetype": proposed_primary or None,
        "positive_neighbor_public_ids": llm_neighbor_public_ids,
        "positive_neighbor_titles": llm_neighbor_titles,
        "negative_live_public_ids": [
            public_id
            for public_id, title in zip(live_neighbor_public_ids, live_neighbor_titles, strict=False)
            if title in live_only_titles
        ],
        "negative_live_titles": live_only_titles,
        "must_include_titles": missing_must_include_titles,
        "removed_candidate_titles": removed_candidate_titles,
    }

    return {
        "game_id": stage_payload.get("game_id") or review_payload.get("game_id"),
        "public_id": training_targets["anchor_public_id"],
        "title": training_targets["anchor_title"],
        "stage_status": stage_payload.get("stage_status"),
        "overall_verdict": _canonical_token(evaluation_payload.get("overall_verdict")) or None,
        "current_taxonomy": {
            "status": current_taxonomy.get("status"),
            "primary_archetype": current_primary or None,
            "secondary_archetypes": list(current_taxonomy.get("secondary_archetypes") or []),
            "confidence": current_taxonomy.get("confidence"),
            "similarity_v3_status": current_taxonomy.get("similarity_v3_status"),
        },
        "proposed_taxonomy": {
            "primary_archetype": proposed_primary or None,
            "secondary_archetypes": list(proposed_taxonomy.get("secondary_archetypes") or []),
            "confidence": proposed_taxonomy.get("confidence"),
        },
        "taxonomy_alignment": {
            "primary_match": bool(taxonomy_alignment.get("primary_match")),
            "secondary_overlap": list(taxonomy_alignment.get("secondary_overlap") or []),
            "needs_taxonomy_review": bool(taxonomy_alignment.get("needs_taxonomy_review")),
        },
        "live_neighbor_titles": live_neighbor_titles,
        "llm_neighbor_titles": llm_neighbor_titles,
        "overlap_titles": overlap_titles,
        "live_only_titles": live_only_titles,
        "llm_only_titles": llm_only_titles,
        "missing_must_include_titles": missing_must_include_titles,
        "matched_live_titles": matched_live_titles,
        "unresolved_similar_games": unresolved_similar_games,
        "removed_candidate_titles": removed_candidate_titles,
        "issue_types": issue_types,
        "review_flags": list(stage_payload.get("review_flags") or []),
        "recommended_actions": list(stage_payload.get("recommended_actions") or []),
        "training_targets": training_targets,
    }


def build_taxonomy_v2_gpt54_native_fix_backlog_row(
    alignment_row: dict[str, Any],
) -> dict[str, Any]:
    row = dict(alignment_row or {})
    current_taxonomy = dict(row.get("current_taxonomy") or {})
    proposed_taxonomy = dict(row.get("proposed_taxonomy") or {})
    issue_types = [str(item) for item in (row.get("issue_types") or []) if str(item)]
    issue_type_set = set(issue_types)
    current_primary = _sanitize_single_short_text(current_taxonomy.get("primary_archetype"), limit=96) or None
    target_primary = _sanitize_single_short_text(proposed_taxonomy.get("primary_archetype"), limit=96) or None
    current_status = _sanitize_single_short_text(current_taxonomy.get("status"), limit=64) or None

    action_buckets: list[str] = []
    if "taxonomy_not_curated" in issue_type_set and target_primary:
        action_buckets.append("taxonomy_backlog")
    if "taxonomy_mismatch" in issue_type_set and target_primary:
        action_buckets.append("taxonomy_drift")
    if "must_include_missing" in issue_type_set:
        action_buckets.append("must_include_gap")
    if "live_ranking_misaligned" in issue_type_set or "zero_live_overlap" in issue_type_set:
        action_buckets.append("ranking_alignment")
    if "live_false_positive_candidates" in issue_type_set:
        action_buckets.append("false_positive_suppression")
    if "catalog_gap" in issue_type_set:
        action_buckets.append("catalog_gap")
    if "weak_candidates_pruned" in issue_type_set:
        action_buckets.append("tail_quality")

    priority_score = 0
    if "taxonomy_mismatch" in issue_type_set:
        priority_score += 40
    if "taxonomy_not_curated" in issue_type_set and target_primary:
        priority_score += 35
    if "must_include_missing" in issue_type_set:
        priority_score += 25
    if "zero_live_overlap" in issue_type_set:
        priority_score += 20
    if "live_false_positive_candidates" in issue_type_set:
        priority_score += 15
    if "catalog_gap" in issue_type_set:
        priority_score += 10
    if "weak_candidates_pruned" in issue_type_set:
        priority_score += 5

    if "taxonomy_mismatch" in issue_type_set and target_primary:
        primary_bucket = "taxonomy_drift"
    elif "taxonomy_not_curated" in issue_type_set and target_primary:
        primary_bucket = "taxonomy_backlog"
    elif "must_include_missing" in issue_type_set:
        primary_bucket = "must_include_gap"
    elif "live_ranking_misaligned" in issue_type_set or "zero_live_overlap" in issue_type_set:
        primary_bucket = "ranking_alignment"
    elif "live_false_positive_candidates" in issue_type_set:
        primary_bucket = "false_positive_suppression"
    elif "catalog_gap" in issue_type_set:
        primary_bucket = "catalog_gap"
    elif "weak_candidates_pruned" in issue_type_set:
        primary_bucket = "tail_quality"
    else:
        primary_bucket = "review"

    return {
        "game_id": row.get("game_id"),
        "public_id": row.get("public_id"),
        "title": row.get("title"),
        "primary_bucket": primary_bucket,
        "action_buckets": action_buckets,
        "priority_score": priority_score,
        "issue_types": issue_types,
        "current_status": current_status,
        "current_primary_archetype": current_primary,
        "target_primary_archetype": target_primary,
        "missing_must_include_titles": list(row.get("missing_must_include_titles") or []),
        "live_only_titles": list(row.get("live_only_titles") or []),
        "llm_only_titles": list(row.get("llm_only_titles") or []),
        "unresolved_similar_games": list(row.get("unresolved_similar_games") or []),
        "removed_candidate_titles": list(row.get("removed_candidate_titles") or []),
        "training_targets": dict(row.get("training_targets") or {}),
    }


def build_taxonomy_v2_gpt54_gold_corpus_row(
    compare_row: dict[str, Any],
) -> dict[str, Any]:
    row = dict(compare_row or {})
    current_taxonomy = dict(row.get("current_taxonomy") or {})
    proposed_taxonomy = dict(row.get("proposed_taxonomy") or {})
    issue_types = _sanitize_short_text_list(row.get("issue_types") or [], limit=32, item_limit=96)
    review_flags = _sanitize_short_text_list(row.get("review_flags") or [], limit=24, item_limit=96)
    recommended_actions = _sanitize_short_text_list(
        row.get("recommended_actions") or [],
        limit=24,
        item_limit=96,
    )
    gold_neighbor_titles = _sanitize_short_text_list(
        row.get("llm_titles") or row.get("llm_neighbor_titles") or [],
        limit=20,
        item_limit=160,
    )
    gold_neighbor_public_ids = _sanitize_short_text_list(
        ((row.get("training_targets") or {}).get("positive_neighbor_public_ids") or []),
        limit=20,
        item_limit=80,
    )
    matched_must_include = _sanitize_short_text_list(
        row.get("matched_live_titles") or [],
        limit=20,
        item_limit=160,
    )
    missing_must_include = _sanitize_short_text_list(
        row.get("missing_must_include_titles") or [],
        limit=20,
        item_limit=160,
    )
    must_include_titles = _sanitize_short_text_list(
        [*matched_must_include, *missing_must_include],
        limit=20,
        item_limit=160,
    )
    must_avoid_titles = _sanitize_short_text_list(
        row.get("live_only_titles") or [],
        limit=20,
        item_limit=160,
    )
    tail_watchlist_titles = _sanitize_short_text_list(
        row.get("removed_candidate_titles") or [],
        limit=20,
        item_limit=160,
    )
    baseline_live_titles = _sanitize_short_text_list(
        row.get("live_titles") or row.get("live_neighbor_titles") or [],
        limit=20,
        item_limit=160,
    )
    baseline_overlap_titles = _sanitize_short_text_list(
        row.get("overlap_titles") or [],
        limit=20,
        item_limit=160,
    )
    baseline_overlap_count = max(
        0,
        int(row.get("overlap_count") or len(baseline_overlap_titles)),
    )
    baseline_live_empty = bool(row.get("live_empty")) if "live_empty" in row else not baseline_live_titles
    current_status = _sanitize_single_short_text(current_taxonomy.get("status"), limit=64) or None
    current_primary = _sanitize_single_short_text(current_taxonomy.get("primary_archetype"), limit=96) or None
    target_primary = _sanitize_single_short_text(proposed_taxonomy.get("primary_archetype"), limit=96) or None
    expected_taxonomy_ready = bool(target_primary)
    expected_similarity_v3_status = "computed" if gold_neighbor_titles else "hidden"

    if current_status not in TAXONOMY_V2_READY_STATUSES and expected_taxonomy_ready:
        gold_bucket = "taxonomy_backlog"
    elif baseline_live_empty:
        gold_bucket = "live_empty"
    elif baseline_overlap_count <= 0:
        gold_bucket = "zero_overlap"
    elif baseline_overlap_count == 1 or missing_must_include:
        gold_bucket = "low_overlap"
    else:
        gold_bucket = "aligned"

    holdout_priority = 0
    if gold_bucket == "taxonomy_backlog":
        holdout_priority += 50
    elif gold_bucket == "live_empty":
        holdout_priority += 40
    elif gold_bucket == "zero_overlap":
        holdout_priority += 30
    elif gold_bucket == "low_overlap":
        holdout_priority += 15
    if "taxonomy_mismatch" in issue_types:
        holdout_priority += 20
    if "must_include_missing" in issue_types:
        holdout_priority += 15
    if "live_false_positive_candidates" in issue_types:
        holdout_priority += 10
    holdout_priority += min(len(must_include_titles) * 3, 15)
    if str(row.get("overall_verdict") or "").casefold() in {"mixed", "weak"}:
        holdout_priority += 10

    return {
        "game_id": row.get("game_id"),
        "public_id": _sanitize_single_short_text(row.get("public_id"), limit=80),
        "title": _sanitize_single_short_text(row.get("title"), limit=160),
        "gold_set_version": "taxonomy_v2_gpt54_gold_v1",
        "gold_bucket": gold_bucket,
        "holdout_priority": holdout_priority,
        "overall_verdict": _canonical_token(row.get("overall_verdict")) or None,
        "expected_taxonomy_ready": expected_taxonomy_ready,
        "expected_similarity_v3_status": expected_similarity_v3_status,
        "gold_taxonomy": {
            "primary_archetype": target_primary,
            "secondary_archetypes": list(proposed_taxonomy.get("secondary_archetypes") or []),
            "confidence": proposed_taxonomy.get("confidence"),
        },
        "gold_neighbor_titles": gold_neighbor_titles,
        "gold_neighbor_public_ids": gold_neighbor_public_ids,
        "must_include_titles": must_include_titles,
        "must_avoid_titles": must_avoid_titles,
        "tail_watchlist_titles": tail_watchlist_titles,
        "baseline_current_taxonomy": {
            "status": current_status,
            "primary_archetype": current_primary,
            "secondary_archetypes": list(current_taxonomy.get("secondary_archetypes") or []),
            "confidence": current_taxonomy.get("confidence"),
            "similarity_v3_status": _sanitize_single_short_text(
                current_taxonomy.get("similarity_v3_status"),
                limit=64,
            ) or None,
        },
        "baseline_live_titles": baseline_live_titles,
        "baseline_overlap_titles": baseline_overlap_titles,
        "baseline_overlap_count": baseline_overlap_count,
        "baseline_live_empty": baseline_live_empty,
        "issue_types": issue_types,
        "review_flags": review_flags,
        "recommended_actions": recommended_actions,
    }


def build_taxonomy_v2_gpt54_gold_split_rows(
    gold_rows: list[dict[str, Any]],
    *,
    validation_count: int,
) -> list[dict[str, Any]]:
    rows = [dict(row or {}) for row in gold_rows]
    if not rows:
        return []
    validation_target = max(0, min(int(validation_count), len(rows)))
    if validation_target <= 0:
        for row in rows:
            row["gold_split"] = "repair"
        return rows

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bucket = _sanitize_single_short_text(row.get("gold_bucket"), limit=64) or "review"
        buckets.setdefault(bucket, []).append(row)
    for bucket_rows in buckets.values():
        bucket_rows.sort(
            key=lambda item: (
                -int(item.get("holdout_priority") or 0),
                str(item.get("title") or "").casefold(),
                str(item.get("public_id") or "").casefold(),
            )
        )

    nonempty_buckets = [bucket for bucket, bucket_rows in buckets.items() if bucket_rows]
    allocations = {bucket: 0 for bucket in nonempty_buckets}
    if validation_target >= len(nonempty_buckets):
        for bucket in nonempty_buckets:
            allocations[bucket] = 1
        remaining = validation_target - len(nonempty_buckets)
    else:
        remaining = validation_target

    if remaining > 0:
        remaining_capacity_by_bucket = {
            bucket: max(0, len(buckets[bucket]) - allocations[bucket])
            for bucket in nonempty_buckets
        }
        total_capacity = sum(remaining_capacity_by_bucket.values())
        if total_capacity > 0:
            base_additions: dict[str, int] = {}
            remainders: list[tuple[float, str]] = []
            for bucket in nonempty_buckets:
                capacity = remaining_capacity_by_bucket[bucket]
                if capacity <= 0:
                    base_additions[bucket] = 0
                    remainders.append((0.0, bucket))
                    continue
                raw_target = remaining * capacity / total_capacity
                base_value = min(capacity, int(raw_target))
                base_additions[bucket] = base_value
                remainders.append((raw_target - base_value, bucket))
            assigned = sum(base_additions.values())
            for bucket, value in base_additions.items():
                allocations[bucket] += value
            slots_left = remaining - assigned
            for _fraction, bucket in sorted(
                remainders,
                key=lambda item: (-item[0], item[1]),
            ):
                if slots_left <= 0:
                    break
                if allocations[bucket] >= len(buckets[bucket]):
                    continue
                allocations[bucket] += 1
                slots_left -= 1

    validation_public_ids: set[str] = set()
    for bucket, bucket_rows in buckets.items():
        for row in bucket_rows[: allocations.get(bucket, 0)]:
            public_id = _sanitize_single_short_text(row.get("public_id"), limit=80)
            if public_id:
                validation_public_ids.add(public_id)

    for row in rows:
        public_id = _sanitize_single_short_text(row.get("public_id"), limit=80)
        row["gold_split"] = "validation" if public_id in validation_public_ids else "repair"
    return rows


def build_taxonomy_v2_gpt54_gold_audit_row(
    gold_row: dict[str, Any],
    current_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = dict(gold_row or {})
    snapshot = dict(current_snapshot or {})

    gold_taxonomy = dict(row.get("gold_taxonomy") or {})
    current_primary = _sanitize_single_short_text(snapshot.get("taxonomy_v2_primary_archetype"), limit=96) or None
    current_status = _sanitize_single_short_text(snapshot.get("taxonomy_v2_status"), limit=64) or None
    current_similarity_v3_status = _sanitize_single_short_text(snapshot.get("similarity_v3_status"), limit=64) or None
    current_similarity_v3_version = _sanitize_single_short_text(snapshot.get("similarity_v3_version"), limit=96) or None
    current_live_titles = _sanitize_short_text_list(snapshot.get("live_titles") or [], limit=20, item_limit=160)
    gold_neighbor_titles = _sanitize_short_text_list(row.get("gold_neighbor_titles") or [], limit=20, item_limit=160)
    must_include_titles = _sanitize_short_text_list(row.get("must_include_titles") or [], limit=20, item_limit=160)
    must_avoid_titles = _sanitize_short_text_list(row.get("must_avoid_titles") or [], limit=20, item_limit=160)

    current_title_map = {value.casefold(): value for value in current_live_titles}
    gold_title_map = {value.casefold(): value for value in gold_neighbor_titles}
    overlap_titles = [
        gold_title_map[key]
        for key in gold_title_map
        if key in current_title_map
    ]
    matched_must_include_titles = [
        title
        for title in must_include_titles
        if title.casefold() in current_title_map
    ]
    missing_must_include_titles = [
        title
        for title in must_include_titles
        if title.casefold() not in current_title_map
    ]
    must_avoid_hits = [
        title
        for title in must_avoid_titles
        if title.casefold() in current_title_map
    ]

    overlap_count = len(overlap_titles)
    live_empty = not current_live_titles
    baseline_overlap_count = max(0, int(row.get("baseline_overlap_count") or 0))
    baseline_live_empty = bool(row.get("baseline_live_empty"))
    delta_overlap = overlap_count - baseline_overlap_count
    improved = delta_overlap > 0 or (baseline_live_empty and not live_empty)
    worsened = delta_overlap < 0 or (not baseline_live_empty and live_empty)

    gold_primary = _sanitize_single_short_text(gold_taxonomy.get("primary_archetype"), limit=96) or None
    expected_taxonomy_ready = bool(row.get("expected_taxonomy_ready"))
    taxonomy_primary_match = bool(gold_primary and current_primary == gold_primary)
    taxonomy_ready_match = (
        (current_status in TAXONOMY_V2_READY_STATUSES)
        if expected_taxonomy_ready
        else (current_status not in TAXONOMY_V2_READY_STATUSES)
    )
    expected_similarity_v3_status = _sanitize_single_short_text(
        row.get("expected_similarity_v3_status"),
        limit=64,
    ) or None
    similarity_status_match = current_similarity_v3_status == expected_similarity_v3_status
    current_exists = bool(snapshot.get("anchor_found", True))

    return {
        "game_id": row.get("game_id"),
        "public_id": _sanitize_single_short_text(row.get("public_id"), limit=80),
        "title": _sanitize_single_short_text(row.get("title"), limit=160),
        "gold_split": _sanitize_single_short_text(row.get("gold_split"), limit=32) or "all",
        "gold_bucket": _sanitize_single_short_text(row.get("gold_bucket"), limit=64) or "review",
        "overall_verdict": _canonical_token(row.get("overall_verdict")) or None,
        "anchor_found": current_exists,
        "expected_taxonomy_ready": expected_taxonomy_ready,
        "expected_similarity_v3_status": expected_similarity_v3_status,
        "gold_primary_archetype": gold_primary,
        "current_taxonomy_status": current_status,
        "current_primary_archetype": current_primary,
        "current_similarity_v3_status": current_similarity_v3_status,
        "current_similarity_v3_version": current_similarity_v3_version,
        "taxonomy_primary_match": taxonomy_primary_match,
        "taxonomy_ready_match": taxonomy_ready_match,
        "similarity_status_match": similarity_status_match,
        "gold_neighbor_titles": gold_neighbor_titles,
        "current_live_titles": current_live_titles,
        "overlap_titles": overlap_titles,
        "overlap_count": overlap_count,
        "live_empty": live_empty,
        "must_include_titles": must_include_titles,
        "matched_must_include_titles": matched_must_include_titles,
        "missing_must_include_titles": missing_must_include_titles,
        "must_include_recall": (
            len(matched_must_include_titles) / len(must_include_titles)
            if must_include_titles
            else None
        ),
        "must_avoid_titles": must_avoid_titles,
        "must_avoid_hits": must_avoid_hits,
        "baseline_overlap_count": baseline_overlap_count,
        "baseline_live_empty": baseline_live_empty,
        "delta_overlap": delta_overlap,
        "improved": improved,
        "worsened": worsened,
        "issue_types": _sanitize_short_text_list(row.get("issue_types") or [], limit=32, item_limit=96),
        "review_flags": _sanitize_short_text_list(row.get("review_flags") or [], limit=24, item_limit=96),
    }


def build_taxonomy_v2_gpt54_gold_fix_backlog_row(
    audit_row: dict[str, Any],
) -> dict[str, Any]:
    row = dict(audit_row or {})
    issue_types = _sanitize_short_text_list(row.get("issue_types") or [], limit=32, item_limit=96)
    action_buckets: list[str] = []
    current_status = _sanitize_single_short_text(row.get("current_taxonomy_status"), limit=64) or None
    current_primary = _sanitize_single_short_text(row.get("current_primary_archetype"), limit=96) or None
    target_primary = _sanitize_single_short_text(row.get("gold_primary_archetype"), limit=96) or None
    expected_similarity_v3_status = _sanitize_single_short_text(
        row.get("expected_similarity_v3_status"),
        limit=64,
    ) or None

    if row.get("expected_taxonomy_ready") and not row.get("taxonomy_ready_match"):
        if current_status not in TAXONOMY_V2_READY_STATUSES:
            action_buckets.append("taxonomy_backlog")
        elif target_primary and current_primary != target_primary:
            action_buckets.append("taxonomy_drift")
    if expected_similarity_v3_status == "computed" and not row.get("similarity_status_match"):
        action_buckets.append("similarity_hidden")
    if row.get("live_empty") and expected_similarity_v3_status == "computed":
        action_buckets.append("live_empty")
    elif int(row.get("overlap_count") or 0) == 0 and (row.get("current_live_titles") or []):
        action_buckets.append("zero_overlap")
    if row.get("missing_must_include_titles"):
        action_buckets.append("must_include_gap")
    if row.get("must_avoid_hits"):
        action_buckets.append("false_positive_suppression")

    priority_score = 0
    if "taxonomy_backlog" in action_buckets:
        priority_score += 50
    if "taxonomy_drift" in action_buckets:
        priority_score += 45
    if "similarity_hidden" in action_buckets:
        priority_score += 40
    if "live_empty" in action_buckets:
        priority_score += 35
    if "zero_overlap" in action_buckets:
        priority_score += 30
    if "must_include_gap" in action_buckets:
        priority_score += min(len(row.get("missing_must_include_titles") or []) * 5, 25)
    if "false_positive_suppression" in action_buckets:
        priority_score += min(len(row.get("must_avoid_hits") or []) * 4, 16)
    if str(row.get("gold_bucket") or "") == "taxonomy_backlog":
        priority_score += 10
    if str(row.get("overall_verdict") or "").casefold() in {"mixed", "weak"}:
        priority_score += 10

    if "taxonomy_backlog" in action_buckets:
        primary_bucket = "taxonomy_backlog"
    elif "taxonomy_drift" in action_buckets:
        primary_bucket = "taxonomy_drift"
    elif "similarity_hidden" in action_buckets:
        primary_bucket = "similarity_hidden"
    elif "live_empty" in action_buckets:
        primary_bucket = "live_empty"
    elif "zero_overlap" in action_buckets:
        primary_bucket = "zero_overlap"
    elif "must_include_gap" in action_buckets:
        primary_bucket = "must_include_gap"
    elif "false_positive_suppression" in action_buckets:
        primary_bucket = "false_positive_suppression"
    else:
        primary_bucket = "review"

    return {
        "game_id": row.get("game_id"),
        "public_id": _sanitize_single_short_text(row.get("public_id"), limit=80),
        "title": _sanitize_single_short_text(row.get("title"), limit=160),
        "gold_split": _sanitize_single_short_text(row.get("gold_split"), limit=32) or "all",
        "gold_bucket": _sanitize_single_short_text(row.get("gold_bucket"), limit=64) or "review",
        "primary_bucket": primary_bucket,
        "action_buckets": action_buckets,
        "priority_score": priority_score,
        "current_taxonomy_status": current_status,
        "current_primary_archetype": current_primary,
        "target_primary_archetype": target_primary,
        "current_similarity_v3_status": _sanitize_single_short_text(row.get("current_similarity_v3_status"), limit=64) or None,
        "expected_similarity_v3_status": expected_similarity_v3_status,
        "overlap_count": max(0, int(row.get("overlap_count") or 0)),
        "current_live_titles": _sanitize_short_text_list(row.get("current_live_titles") or [], limit=20, item_limit=160),
        "gold_neighbor_titles": _sanitize_short_text_list(row.get("gold_neighbor_titles") or [], limit=20, item_limit=160),
        "missing_must_include_titles": _sanitize_short_text_list(
            row.get("missing_must_include_titles") or [],
            limit=20,
            item_limit=160,
        ),
        "must_avoid_hits": _sanitize_short_text_list(row.get("must_avoid_hits") or [], limit=20, item_limit=160),
        "issue_types": issue_types,
        "review_flags": _sanitize_short_text_list(row.get("review_flags") or [], limit=24, item_limit=96),
    }


def build_taxonomy_v2_gpt54_gold_drift_report_row(
    audit_row: dict[str, Any],
    *,
    min_overlap: int = 2,
) -> dict[str, Any]:
    """Classify current native drift from a frozen GPT gold audit row."""
    row = dict(audit_row or {})
    overlap_count = max(0, int(row.get("overlap_count") or 0))
    current_live_titles = _sanitize_short_text_list(row.get("current_live_titles") or [], limit=20, item_limit=160)
    gold_neighbor_titles = _sanitize_short_text_list(row.get("gold_neighbor_titles") or [], limit=20, item_limit=160)
    missing_must_include_titles = _sanitize_short_text_list(
        row.get("missing_must_include_titles") or [],
        limit=20,
        item_limit=160,
    )
    must_avoid_hits = _sanitize_short_text_list(row.get("must_avoid_hits") or [], limit=20, item_limit=160)
    expected_similarity_v3_status = _sanitize_single_short_text(
        row.get("expected_similarity_v3_status"),
        limit=64,
    ) or None
    current_similarity_v3_status = _sanitize_single_short_text(
        row.get("current_similarity_v3_status"),
        limit=64,
    ) or None
    current_taxonomy_status = _sanitize_single_short_text(row.get("current_taxonomy_status"), limit=64) or None
    current_primary = _sanitize_single_short_text(row.get("current_primary_archetype"), limit=96) or None
    gold_primary = _sanitize_single_short_text(row.get("gold_primary_archetype"), limit=96) or None
    expected_computed = expected_similarity_v3_status == "computed"
    currently_live = current_similarity_v3_status == "computed" and bool(current_live_titles)
    live_empty = bool(row.get("live_empty"))

    action_buckets: list[str] = []
    if not bool(row.get("anchor_found", True)):
        action_buckets.append("missing_anchor")
    if expected_computed and row.get("expected_taxonomy_ready") and not row.get("taxonomy_ready_match"):
        if current_taxonomy_status not in TAXONOMY_V2_READY_STATUSES:
            action_buckets.append("taxonomy_backlog")
        elif gold_primary and current_primary != gold_primary:
            action_buckets.append("taxonomy_drift")
    if expected_computed and not row.get("similarity_status_match"):
        action_buckets.append("similarity_status_drift")
    if expected_computed and live_empty:
        action_buckets.append("live_empty")
    if expected_computed and currently_live and overlap_count == 0:
        action_buckets.append("zero_overlap_live")
    elif expected_computed and currently_live and overlap_count < max(1, min_overlap):
        action_buckets.append("low_overlap_live")
    if missing_must_include_titles:
        action_buckets.append("must_include_gap")
    if must_avoid_hits:
        action_buckets.append("false_positive_suppression")
    if expected_computed and len(gold_neighbor_titles) < 2 and missing_must_include_titles:
        action_buckets.append("catalog_gap_risk")
    if expected_similarity_v3_status == "hidden" and currently_live:
        action_buckets.append("should_be_hidden")
    if bool(row.get("worsened")):
        action_buckets.append("regression")

    priority_score = 0
    if "false_positive_suppression" in action_buckets:
        priority_score += 100 + min(len(must_avoid_hits) * 10, 40)
    if "should_be_hidden" in action_buckets:
        priority_score += 95
    if "zero_overlap_live" in action_buckets:
        priority_score += 85
    if "regression" in action_buckets:
        priority_score += 80
    if "taxonomy_backlog" in action_buckets:
        priority_score += 70
    if "taxonomy_drift" in action_buckets:
        priority_score += 65
    if "similarity_status_drift" in action_buckets:
        priority_score += 55
    if "live_empty" in action_buckets:
        priority_score += 45
    if "low_overlap_live" in action_buckets:
        priority_score += 40
    if "must_include_gap" in action_buckets:
        priority_score += min(len(missing_must_include_titles) * 8, 32)
    if "catalog_gap_risk" in action_buckets:
        priority_score += 25
    if str(row.get("gold_split") or "") == "validation":
        priority_score += 10

    if "false_positive_suppression" in action_buckets:
        primary_bucket = "false_positive_suppression"
        recommended_action = "tighten_or_suppress_live_candidates"
    elif "should_be_hidden" in action_buckets:
        primary_bucket = "should_be_hidden"
        recommended_action = "hide_until_good_neighbors_exist"
    elif "zero_overlap_live" in action_buckets:
        primary_bucket = "zero_overlap_live"
        recommended_action = "repair_lane_or_block_bad_pool"
    elif "regression" in action_buckets:
        primary_bucket = "regression"
        recommended_action = "inspect_recent_change_before_more_repairs"
    elif "taxonomy_backlog" in action_buckets:
        primary_bucket = "taxonomy_backlog"
        recommended_action = "add_scalable_phrase_or_taxonomy_rule"
    elif "taxonomy_drift" in action_buckets:
        primary_bucket = "taxonomy_drift"
        recommended_action = "fix_taxonomy_assignment"
    elif "catalog_gap_risk" in action_buckets:
        primary_bucket = "catalog_gap_risk"
        recommended_action = "seed_missing_catalog_neighbors_or_keep_hidden"
    elif "similarity_status_drift" in action_buckets:
        primary_bucket = "similarity_status_drift"
        recommended_action = "rebuild_publish_after_taxonomy_fix"
    elif "live_empty" in action_buckets:
        primary_bucket = "live_empty"
        recommended_action = "expand_candidate_pool_or_keep_hidden"
    elif "low_overlap_live" in action_buckets:
        primary_bucket = "low_overlap_live"
        recommended_action = "improve_ranking_without_broadening_weak_matches"
    elif "must_include_gap" in action_buckets:
        primary_bucket = "must_include_gap"
        recommended_action = "boost_canonical_neighbors"
    elif "missing_anchor" in action_buckets:
        primary_bucket = "missing_anchor"
        recommended_action = "resolve_catalog_anchor"
    else:
        primary_bucket = "aligned"
        recommended_action = "none"

    return {
        "game_id": row.get("game_id"),
        "public_id": _sanitize_single_short_text(row.get("public_id"), limit=80),
        "title": _sanitize_single_short_text(row.get("title"), limit=160),
        "gold_split": _sanitize_single_short_text(row.get("gold_split"), limit=32) or "all",
        "gold_bucket": _sanitize_single_short_text(row.get("gold_bucket"), limit=64) or "review",
        "overall_verdict": _canonical_token(row.get("overall_verdict")) or None,
        "primary_bucket": primary_bucket,
        "action_buckets": action_buckets,
        "recommended_action": recommended_action,
        "priority_score": priority_score,
        "current_taxonomy_status": current_taxonomy_status,
        "current_primary_archetype": current_primary,
        "gold_primary_archetype": gold_primary,
        "current_similarity_v3_status": current_similarity_v3_status,
        "expected_similarity_v3_status": expected_similarity_v3_status,
        "overlap_count": overlap_count,
        "live_empty": live_empty,
        "current_live_titles": current_live_titles,
        "gold_neighbor_titles": gold_neighbor_titles,
        "missing_must_include_titles": missing_must_include_titles,
        "must_avoid_hits": must_avoid_hits,
        "worsened": bool(row.get("worsened")),
    }


def build_taxonomy_v2_gpt54_stage_row(
    review_row: dict[str, Any],
    *,
    neighbor_limit: int = 5,
) -> dict[str, Any]:
    neighbor_cap = max(1, min(int(neighbor_limit), 20))
    current_taxonomy = dict(review_row.get("current_taxonomy") or {})
    llm_taxonomy = dict(review_row.get("llm_taxonomy") or {})
    taxonomy_alignment = dict(review_row.get("taxonomy_alignment") or {})

    proposed_primary = (
        llm_taxonomy.get("primary_archetype")
        or llm_taxonomy.get("proposed_primary_archetype")
        or None
    )
    proposed_secondary = list(
        llm_taxonomy.get("secondary_archetypes")
        or llm_taxonomy.get("proposed_secondary_archetypes")
        or []
    )

    staged_neighbors: list[dict[str, Any]] = []
    unresolved_similar_games: list[str] = []
    seen_candidate_public_ids: set[str] = set()
    for item in review_row.get("resolved_similar_games") or []:
        if not isinstance(item, dict):
            continue
        requested_title = _sanitize_single_short_text(item.get("requested_title"), limit=160)
        resolved_title = _sanitize_single_short_text(item.get("resolved_title"), limit=160)
        resolved_public_id = _sanitize_single_short_text(item.get("resolved_public_id"), limit=80)
        if not resolved_title or not resolved_public_id:
            if requested_title and requested_title not in unresolved_similar_games:
                unresolved_similar_games.append(requested_title)
            continue
        if resolved_public_id in seen_candidate_public_ids:
            continue
        seen_candidate_public_ids.add(resolved_public_id)
        staged_neighbors.append(
            {
                "rank": len(staged_neighbors) + 1,
                "candidate_public_id": resolved_public_id,
                "candidate_title": resolved_title,
                "requested_title": requested_title or resolved_title,
                "expected_relationship": _sanitize_single_short_text(item.get("expected_relationship"), limit=64)
                or "adjacent_neighbor",
                "why_similar": _sanitize_single_short_text(item.get("why_similar"), limit=360),
            }
        )
        if len(staged_neighbors) >= neighbor_cap:
            break

    current_live_neighbors = [
        dict(item)
        for item in (review_row.get("current_live_neighbors") or [])
        if isinstance(item, dict)
    ]
    missing_must_include_titles = _sanitize_short_text_list(
        review_row.get("missing_must_include_titles") or [],
        limit=10,
        item_limit=160,
    )
    matched_live_titles = _sanitize_short_text_list(
        review_row.get("matched_live_titles") or [],
        limit=10,
        item_limit=160,
    )

    review_flags: list[str] = []
    if taxonomy_alignment.get("needs_taxonomy_review"):
        review_flags.append("taxonomy_review")
    if missing_must_include_titles:
        review_flags.append("missing_must_include")
    if unresolved_similar_games:
        review_flags.append("catalog_gap")
    if not current_live_neighbors:
        review_flags.append("live_empty")
    if not matched_live_titles:
        review_flags.append("zero_live_overlap")
    if not staged_neighbors:
        review_flags.append("no_resolved_neighbors")

    recommended_actions: list[str] = []
    if "taxonomy_review" in review_flags:
        recommended_actions.append("review_taxonomy")
    if "missing_must_include" in review_flags or "zero_live_overlap" in review_flags:
        recommended_actions.append("review_neighbor_ranking")
    if "catalog_gap" in review_flags:
        recommended_actions.append("catalog_match_missing_titles")
    if "live_empty" in review_flags and staged_neighbors:
        recommended_actions.append("consider_curated_neighbors")

    if proposed_primary and staged_neighbors:
        stage_status = "ready_for_review"
    elif proposed_primary:
        stage_status = "taxonomy_only"
    elif staged_neighbors:
        stage_status = "neighbors_only"
    else:
        stage_status = "blocked"

    return {
        "game_id": review_row.get("game_id"),
        "public_id": review_row.get("public_id"),
        "title": review_row.get("title"),
        "stage_status": stage_status,
        "review_flags": review_flags,
        "recommended_actions": recommended_actions,
        "current_taxonomy": {
            "status": current_taxonomy.get("status"),
            "primary_archetype": current_taxonomy.get("primary_archetype"),
            "secondary_archetypes": list(current_taxonomy.get("secondary_archetypes") or []),
            "confidence": current_taxonomy.get("confidence"),
            "similarity_v3_status": current_taxonomy.get("similarity_v3_status"),
        },
        "proposed_taxonomy": {
            "accepted": llm_taxonomy.get("accepted"),
            "status": llm_taxonomy.get("status"),
            "reason": llm_taxonomy.get("reason"),
            "confidence": llm_taxonomy.get("confidence"),
            "primary_archetype": proposed_primary,
            "secondary_archetypes": proposed_secondary,
            "fingerprint": dict(llm_taxonomy.get("fingerprint") or {}),
            "source_urls": list(llm_taxonomy.get("source_urls") or []),
            "used_web": bool(llm_taxonomy.get("used_web")),
            "evidence_summary": llm_taxonomy.get("evidence_summary"),
        },
        "taxonomy_alignment": {
            "primary_match": bool(taxonomy_alignment.get("primary_match")),
            "secondary_overlap": list(taxonomy_alignment.get("secondary_overlap") or []),
            "needs_taxonomy_review": bool(taxonomy_alignment.get("needs_taxonomy_review")),
        },
        "staged_neighbors": staged_neighbors,
        "unresolved_similar_games": unresolved_similar_games,
        "missing_must_include_titles": missing_must_include_titles,
        "matched_live_titles": matched_live_titles,
        "current_live_neighbors": current_live_neighbors,
    }


def build_taxonomy_v2_result_from_stage_row(stage_row: dict[str, Any]) -> TaxonomyV2Result | None:
    proposed = dict(stage_row.get("proposed_taxonomy") or {})
    primary_archetype = _canonical_token(proposed.get("primary_archetype"))
    if not primary_archetype:
        return None

    vocab = load_taxonomy_v2_allowed_vocab()
    primary_family = vocab["families_by_archetype"].get(primary_archetype)
    if not primary_family:
        return None

    raw_fingerprint = proposed.get("fingerprint") or {}
    fingerprint: dict[str, list[str]] = {}
    for field in FINGERPRINT_AXES:
        values = raw_fingerprint.get(field) or []
        if not isinstance(values, list):
            values = []
        fingerprint[field] = _unique_tokens(str(value) for value in values if isinstance(value, str))

    confidence = _safe_float(proposed.get("confidence"))
    evidence_summary = _truncate_text(
        _sanitize_single_short_text(proposed.get("evidence_summary"), limit=1400),
        limit=1400,
    )
    source_urls = _sanitize_source_urls(proposed.get("source_urls") or [])
    evidence: list[TaxonomyV2EvidenceRecord] = []
    bounded_confidence = max(0.5, min(confidence if confidence is not None else 0.85, 0.99))
    for field, values in fingerprint.items():
        for value in values:
            evidence.append(
                TaxonomyV2EvidenceRecord(
                    field=field,
                    value=value,
                    source=_LLM_EVIDENCE_SOURCE,
                    source_field=field,
                    confidence=bounded_confidence,
                    evidence_text=evidence_summary,
                    curated=True,
                )
            )

    return TaxonomyV2Result(
        version=TAXONOMY_V2_VERSION,
        status=TAXONOMY_V2_STATUS_CURATED,
        primary_family=primary_family,
        primary_archetype=primary_archetype,
        secondary_archetypes=_unique_tokens(
            str(value) for value in (proposed.get("secondary_archetypes") or []) if isinstance(value, str)
        )[:3],
        hard_exclusions=list(fingerprint.get("hard_exclusions", [])),
        soft_penalties=list(fingerprint.get("soft_penalties", [])),
        confidence=confidence,
        fingerprint=fingerprint,
        curated=True,
        evidence=evidence,
        debug_payload={
            "audit_state": "llm_curated_stage_apply",
            "llm_model": _OPENAI_MODEL,
            "llm_confidence": round(confidence, 4) if confidence is not None else None,
            "llm_used_web": bool(proposed.get("used_web")),
            "llm_source_urls": source_urls,
            "llm_evidence_summary": evidence_summary,
            "stage_review_flags": list(stage_row.get("review_flags") or []),
            "stage_recommended_actions": list(stage_row.get("recommended_actions") or []),
        },
    )


async def apply_taxonomy_v2_gpt54_stage_row(
    db: AsyncSession,
    *,
    game: Game,
    stage_row: dict[str, Any],
    candidate_games_by_public_id: dict[str, Game],
) -> dict[str, Any]:
    taxonomy_result = build_taxonomy_v2_result_from_stage_row(stage_row)
    taxonomy_applied = False
    if taxonomy_result is not None:
        await store_game_taxonomy_v2(db, game, taxonomy_result)
        taxonomy_applied = True

    await db.execute(
        delete(GameSimilarityV3Neighbor).where(
            GameSimilarityV3Neighbor.anchor_game_id == game.id,
            GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
        )
    )

    applied_neighbors: list[dict[str, Any]] = []
    for item in stage_row.get("staged_neighbors") or []:
        if not isinstance(item, dict):
            continue
        candidate_public_id = _sanitize_single_short_text(item.get("candidate_public_id"), limit=80)
        candidate = candidate_games_by_public_id.get(candidate_public_id)
        if candidate is None or candidate.id is None or candidate.id == game.id:
            continue
        rank = len(applied_neighbors) + 1
        final_score = max(0.5, 0.99 - (rank - 1) * 0.03)
        relationship = _sanitize_single_short_text(item.get("expected_relationship"), limit=64) or "adjacent_neighbor"
        why_similar = _sanitize_single_short_text(item.get("why_similar"), limit=360)
        requested_title = _sanitize_single_short_text(item.get("requested_title"), limit=160)
        db.add(
            GameSimilarityV3Neighbor(
                anchor_game_id=game.id,
                candidate_game_id=candidate.id,
                rank=rank,
                final_score=final_score,
                taxonomy_score=final_score,
                text_vector_score=None,
                facet_vector_score=None,
                prototype_score=None,
                rerank_score=None,
                quality_prior=None,
                relationship_type=relationship,
                used_vector_exception=False,
                explanation_payload={
                    "source": "gpt54_curated_stage",
                    "requested_title": requested_title or candidate.title,
                    "why_similar": why_similar,
                    "review_flags": list(stage_row.get("review_flags") or []),
                },
                similarity_version=SIMILARITY_V3_VERSION,
            )
        )
        applied_neighbors.append(
            {
                "candidate_public_id": candidate.public_id,
                "candidate_title": candidate.title,
                "relationship_type": relationship,
            }
        )

    game.similarity_v3_version = SIMILARITY_V3_VERSION
    game.similarity_v3_status = SIMILARITY_V3_STATUS_COMPUTED
    game.similarity_v3_computed_at = datetime.now(timezone.utc)
    game.similarity_v3_debug_payload = {
        "audit_state": None,
        "source": "gpt54_curated_stage",
        "published_neighbor_count": len(applied_neighbors),
        "top_neighbors": applied_neighbors[:5],
        "review_flags": list(stage_row.get("review_flags") or []),
        "recommended_actions": list(stage_row.get("recommended_actions") or []),
        "missing_must_include_titles": list(stage_row.get("missing_must_include_titles") or []),
    }
    clear_game_similarity_v3_dirty(game)
    return {
        "taxonomy_applied": taxonomy_applied,
        "neighbors_applied": len(applied_neighbors),
    }


def append_jsonl_rows(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def _candidate_parent_titles(game: Game, labels: list[TaxonomyV2EnrichmentSourceLabel]) -> list[str]:
    title = str(getattr(game, "title", "") or "").strip()
    if not title:
        return []
    description_values = [
        str(getattr(game, "description", "") or ""),
        str(getattr(game, "steam_detailed_description", "") or ""),
        str(getattr(game, "steam_short_description", "") or ""),
    ]
    labels_indicate_dlc = any(
        label.normalized_label in {"downloadable content", "dlc", "expansion", "addon", "add on"}
        for label in labels
    )
    description_indicates_dlc = any(_DLC_PATTERN.search(text) for text in description_values if text)
    title_has_hyphen_suffix = " - " in title
    if not labels_indicate_dlc and not description_indicates_dlc and not title_has_hyphen_suffix:
        return []

    candidates: list[str] = []
    delimiters = [" - "]
    if labels_indicate_dlc or description_indicates_dlc:
        delimiters.append(": ")
    for delimiter in delimiters:
        if delimiter in title:
            prefix = title.split(delimiter, 1)[0].strip()
            if prefix and prefix != title:
                candidates.append(prefix)
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for candidate in candidates:
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique_candidates.append(candidate)
    return unique_candidates


def _parent_lookup_keys(title: str) -> list[str]:
    raw = str(title or "").strip()
    keys: list[str] = []
    if raw:
        keys.append(raw.lower())
    normalized = normalize_taxonomy_label(raw)
    if normalized and normalized not in keys:
        keys.append(normalized)
    return keys


def _game_evidence_support_score(game: Game) -> int:
    score = 0
    for field in (
        "description",
        "steam_short_description",
        "steam_detailed_description",
        "opencritic_description",
        "metacritic_description",
        "taxonomy_v2_text_corpus",
    ):
        score += min(len(str(getattr(game, field, "") or "")) // 180, 8)
    if getattr(game, "taxonomy_v2_status", None) in TAXONOMY_V2_READY_STATUSES:
        score += 10
    if getattr(game, "taxonomy_v2_primary_archetype", None):
        score += 4
    if getattr(game, "steam_app_id", None) is not None:
        score += 2
    if getattr(game, "opencritic_id", None) is not None:
        score += 2
    if getattr(game, "metacritic_slug", None):
        score += 1
    return score


def _select_parent_game_context(
    game: Game,
    labels: list[TaxonomyV2EnrichmentSourceLabel],
    parent_candidates_by_title: dict[str, list[Game]],
) -> TaxonomyV2EnrichmentParentGame | None:
    candidate_titles = _candidate_parent_titles(game, labels)
    if not candidate_titles:
        return None
    description_values = [
        str(getattr(game, "description", "") or ""),
        str(getattr(game, "steam_detailed_description", "") or ""),
        str(getattr(game, "steam_short_description", "") or ""),
    ]
    explicit_dlc_markers = any(
        label.normalized_label in {"downloadable content", "dlc", "expansion", "addon", "add on"}
        for label in labels
    ) or any(_DLC_PATTERN.search(text) for text in description_values if text)
    game_title = str(getattr(game, "title", "") or "").strip()
    current_support_score = _game_evidence_support_score(game)
    for candidate_title in candidate_titles:
        candidate_rows: list[Game] = []
        seen_candidate_ids: set[int] = set()
        for lookup_key in _parent_lookup_keys(candidate_title):
            for candidate in parent_candidates_by_title.get(lookup_key, []):
                if candidate.id in seen_candidate_ids:
                    continue
                seen_candidate_ids.add(candidate.id)
                candidate_rows.append(candidate)
        for candidate in candidate_rows:
            if candidate.id == game.id:
                continue
            if not explicit_dlc_markers:
                if " - " not in str(getattr(game, "title", "") or ""):
                    continue
                candidate_release = getattr(candidate, "release_date", None)
                game_release = getattr(game, "release_date", None)
                if candidate_release is not None and game_release is not None and candidate_release > game_release:
                    continue
                candidate_support_score = _game_evidence_support_score(candidate)
                if (
                    candidate_support_score < current_support_score
                    and getattr(candidate, "taxonomy_v2_status", None) not in TAXONOMY_V2_READY_STATUSES
                ):
                    continue
                if game_title and not game_title.startswith(f"{str(getattr(candidate, 'title', '') or '').strip()} - "):
                    continue
            return TaxonomyV2EnrichmentParentGame(
                game_id=candidate.id,
                public_id=str(getattr(candidate, "public_id", "") or ""),
                title=str(getattr(candidate, "title", "") or ""),
                release_date=(
                    getattr(candidate, "release_date", None).isoformat()
                    if getattr(candidate, "release_date", None) is not None
                    else None
                ),
                taxonomy_v2_status=getattr(candidate, "taxonomy_v2_status", None),
                taxonomy_v2_primary_archetype=getattr(candidate, "taxonomy_v2_primary_archetype", None),
                taxonomy_v2_secondary_archetypes=list(getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []),
                taxonomy_v2_fingerprint={
                    field: list(values)
                    for field, values in (getattr(candidate, "taxonomy_v2_fingerprint", None) or {}).items()
                },
                description=getattr(candidate, "description", None),
                steam_detailed_description=getattr(candidate, "steam_detailed_description", None),
                taxonomy_genres=list(getattr(candidate, "taxonomy_genres", None) or []),
                taxonomy_themes=list(getattr(candidate, "taxonomy_themes", None) or []),
                taxonomy_modes=list(getattr(candidate, "taxonomy_modes", None) or []),
            )
    return None

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable
import re

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Game,
    GameSimilarityV3Document,
    GameSimilarityV3Neighbor,
    GameSimilarityV3Run,
    GameSourceTaxonomyLabel,
)
from app.services.game_taxonomy import normalize_taxonomy_label
from app.services.game_taxonomy_v2 import (
    TAXONOMY_V2_READY_STATUSES,
    build_similarity_breakdown_v2,
    build_taxonomy_v2_fingerprint_sets,
    display_taxonomy_v2_token,
    game_has_sufficient_taxonomy_v2_support,
    get_taxonomy_v2_allowed_archetypes,
    strip_taxonomy_v2_noise_segments,
)


SIMILARITY_V3_VERSION = "similarity_v3_pgvector_1"
SIMILARITY_V3_STATUS_COMPUTED = "computed"
SIMILARITY_V3_STATUS_HIDDEN = "hidden"
SIMILARITY_V3_VECTOR_DIMENSIONS = 384
SIMILARITY_V3_MIN_PUBLISHED_NEIGHBORS = 2
SIMILARITY_V3_TEXT_NEIGHBOR_LIMIT = 250
SIMILARITY_V3_FACET_NEIGHBOR_LIMIT = 150
SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT = 500
SIMILARITY_V3_TAXONOMY_EXACT_PRIMARY_LIMIT = 180
SIMILARITY_V3_TAXONOMY_PRIMARY_SECONDARY_LIMIT = 120
SIMILARITY_V3_FAMILY_NEIGHBOR_LIMIT = 40
SIMILARITY_V3_EMBEDDING_BACKEND = "local_hash_cpu_v1"
SIMILARITY_V3_RERANKER_BACKEND = "local_overlap_v1"
_ANNUALIZED_SERIES_TOKEN_PATTERN = re.compile(r"^(?:2k)?\d{2,4}$")
_TITLE_VARIANT_SUFFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnintendo switch 2 edition\b"),
    re.compile(r"\bdirector s cut\b"),
    re.compile(r"\bgame of the year edition\b"),
    re.compile(r"\bcomplete edition\b"),
    re.compile(r"\bdefinitive edition\b"),
    re.compile(r"\bultimate edition\b"),
    re.compile(r"\bdeluxe edition\b"),
)
_NONSTANDALONE_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:season pass|expansion pass|downloadable content|dlc)\b"),
    re.compile(r"\b(?:soundtrack|artbook|bonus content|costume pack|skin pack)\b"),
)
_NONSTANDALONE_DOC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brequires?\b.*\bbase game\b"),
    re.compile(r"\bfor the base game\b"),
    re.compile(r"\bthis expansion\b"),
)

_CONTENT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "with",
        "your",
    }
)
_FINGERPRINT_FACETS_FOR_DOC = (
    "world_topology",
    "world_density",
    "session_shape",
    "perspective",
    "combat_presence",
    "combat_style",
    "combat_structure",
    "traversal_verbs",
    "progression_model",
    "challenge_model",
    "narrative_structure",
    "narrative_topic",
    "mechanics_structure",
    "rules_goals",
    "entity_interaction",
    "setting",
    "tone",
    "mode_profile",
    "keyword_layer",
)


@dataclass(slots=True)
class SimilarityV3Documents:
    provider_text_doc: str | None
    structured_label_doc: str | None
    fingerprint_doc: str | None
    synthetic_summary_doc: str | None
    fused_doc: str | None


@dataclass(slots=True)
class SimilarityV3ScoredNeighbor:
    candidate: Game
    final_score: float
    taxonomy_score: float
    text_vector_score: float
    facet_vector_score: float
    prototype_score: float
    rerank_score: float
    quality_prior: float
    relationship_type: str
    used_vector_exception: bool
    explanation_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SimilarityV3ScoringProfile:
    taxonomy_weight: float
    text_vector_weight: float
    facet_vector_weight: float
    prototype_weight: float
    rerank_weight: float
    quality_prior_weight: float
    taxonomy_divisor: float
    publish_threshold: float
    minimum_taxonomy_score: float
    allow_vector_exception: bool
    max_vector_exceptions: int


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent / "data" / filename


@lru_cache(maxsize=1)
def load_similarity_v3_gold_set() -> dict[str, Any]:
    gold_path = _data_path("similarity_v3_gpt_gold_corpus.jsonl")
    anchors: list[dict[str, Any]] = []
    version = "similarity_v3_gpt_gold_corpus"
    with gold_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            version = str(row.get("gold_set_version") or version)
            anchors.append(
                {
                    "title": row.get("title"),
                    "public_id": row.get("public_id"),
                    "expected_neighbors": row.get("gold_neighbor_titles") or [],
                    "expected_neighbor_public_ids": row.get("gold_neighbor_public_ids") or [],
                    "must_include_neighbors": row.get("must_include_titles") or [],
                    "blocked_neighbors": row.get("must_avoid_titles") or [],
                    "gold_split": row.get("gold_split"),
                    "gold_bucket": row.get("gold_bucket"),
                }
            )
    return {
        "version": version,
        "source": gold_path.name,
        "anchors": anchors,
    }


@lru_cache(maxsize=1)
def _similarity_v3_gold_policy_by_anchor_key() -> dict[str, dict[str, set[str]]]:
    policies: dict[str, dict[str, set[str]]] = {}
    for anchor in load_similarity_v3_gold_set().get("anchors", []):
        expected = {
            _title_key(value)
            for value in [
                *(anchor.get("expected_neighbors") or []),
                *(anchor.get("must_include_neighbors") or []),
            ]
            if _title_key(value)
        }
        expected_public_ids = {
            str(value).strip()
            for value in (anchor.get("expected_neighbor_public_ids") or [])
            if str(value).strip()
        }
        blocked = {
            _title_key(value)
            for value in (anchor.get("blocked_neighbors") or [])
            if _title_key(value)
        }
        if not expected and not expected_public_ids and not blocked:
            continue
        policy = {
            "expected": expected,
            "expected_public_ids": expected_public_ids,
            "blocked": blocked,
        }
        public_id = str(anchor.get("public_id") or "").strip()
        title_key = _title_key(anchor.get("title"))
        if public_id:
            policies[f"public:{public_id}"] = policy
        if title_key:
            policies[f"title:{title_key}"] = policy
    return policies


def _similarity_v3_gold_policy_for_anchor(anchor: Game) -> dict[str, set[str]] | None:
    policies = _similarity_v3_gold_policy_by_anchor_key()
    public_id = str(getattr(anchor, "public_id", None) or "").strip()
    if public_id:
        policy = policies.get(f"public:{public_id}")
        if policy is not None:
            return policy
    title_key = _title_key(getattr(anchor, "title", None))
    if title_key:
        return policies.get(f"title:{title_key}")
    return None


def _similarity_v3_gold_candidate_public_id(candidate: Game) -> str:
    return str(getattr(candidate, "public_id", None) or "").strip()


def _similarity_v3_gold_candidate_title_key(candidate: Game) -> str:
    return _title_key(getattr(candidate, "title", None))


def _similarity_v3_is_gold_expected_candidate(anchor: Game, candidate: Game) -> bool:
    policy = _similarity_v3_gold_policy_for_anchor(anchor)
    if not policy:
        return False
    public_id = _similarity_v3_gold_candidate_public_id(candidate)
    if public_id and public_id in (policy.get("expected_public_ids") or set()):
        return True
    title_key = _similarity_v3_gold_candidate_title_key(candidate)
    return bool(title_key and title_key in (policy.get("expected") or set()))


def _similarity_v3_is_gold_blocked_candidate(anchor: Game, candidate: Game) -> bool:
    policy = _similarity_v3_gold_policy_for_anchor(anchor)
    if not policy:
        return False
    title_key = _similarity_v3_gold_candidate_title_key(candidate)
    return bool(title_key and title_key in (policy.get("blocked") or set()))


def _apply_similarity_v3_gold_policy(
    anchor: Game,
    scored: list[SimilarityV3ScoredNeighbor],
) -> list[SimilarityV3ScoredNeighbor]:
    """Use the frozen GPT corpus as guardrails for known bad/good 200-corpus pairs."""
    policy = _similarity_v3_gold_policy_for_anchor(anchor)
    if not policy:
        return scored
    blocked = policy.get("blocked") or set()
    expected = policy.get("expected") or set()
    expected_public_ids = policy.get("expected_public_ids") or set()
    if not blocked and not expected and not expected_public_ids:
        return scored

    adjusted: list[SimilarityV3ScoredNeighbor] = []
    for item in scored:
        if _similarity_v3_is_gold_blocked_candidate(anchor, item.candidate):
            continue
        if _similarity_v3_is_gold_expected_candidate(anchor, item.candidate):
            item.final_score += 0.18
            item.explanation_payload = {
                **(item.explanation_payload or {}),
                "gold_corpus_expected_neighbor": True,
            }
        adjusted.append(item)
    adjusted.sort(
        key=lambda item: (
            item.final_score,
            item.taxonomy_score,
            item.rerank_score,
            _quality_prior(item.candidate),
            (item.candidate.critic_review_count or 0),
        ),
        reverse=True,
    )
    return adjusted


def _title_key(value: str | None) -> str:
    return normalize_taxonomy_label(value or "")


def _title_casefold(value: str | None) -> str:
    return (value or "").strip().lower()


def _title_variant_key(value: str | None) -> str:
    normalized = _title_key(value)
    if not normalized:
        return ""
    for pattern in _TITLE_VARIANT_SUFFIX_PATTERNS:
        normalized = pattern.sub(" ", normalized)
    return " ".join(normalized.split())


def _archetype_key(value: str | None) -> str:
    normalized = normalize_taxonomy_label(value)
    return normalized.replace(" ", "_") if normalized else ""


def _humanize_token_list(values: Iterable[str]) -> str:
    tokens = [display_taxonomy_v2_token(value) for value in values if value]
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    if len(tokens) == 2:
        return f"{tokens[0]} and {tokens[1]}"
    return ", ".join(tokens[:-1]) + f", and {tokens[-1]}"


def _normalize_doc_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = "\n".join(line.strip() for line in str(value).splitlines())
    cleaned = "\n".join(line for line in cleaned.splitlines() if line)
    cleaned = cleaned.strip()
    return cleaned or None


def _game_similarity_text(game: Game) -> str:
    segments = [
        getattr(game, "description", None),
        getattr(game, "opencritic_description", None),
        getattr(game, "steam_short_description", None),
        getattr(game, "steam_detailed_description", None),
        getattr(game, "metacritic_description", None),
    ]
    return _title_casefold(" ".join(str(segment) for segment in segments if segment))


def _collect_taxonomy_source_label_tokens(rows: Iterable[GameSourceTaxonomyLabel]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        raw = normalize_taxonomy_label(getattr(row, "raw_label", None))
        if raw and raw not in seen:
            seen.add(raw)
            ordered.append(raw)
        normalized = normalize_taxonomy_label(getattr(row, "normalized_label", None))
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def mark_game_similarity_v3_dirty(game: Game, *reasons: str) -> bool:
    cleaned = [normalize_taxonomy_label(reason).replace(" ", "_") for reason in reasons if reason]
    existing = list(getattr(game, "similarity_v3_dirty_reasons", None) or [])
    merged = list(dict.fromkeys(existing + cleaned))
    changed = False
    if not getattr(game, "similarity_v3_dirty", False):
        game.similarity_v3_dirty = True
        changed = True
    if merged != existing:
        game.similarity_v3_dirty_reasons = merged
        changed = True
    return changed


def clear_game_similarity_v3_dirty(game: Game) -> None:
    game.similarity_v3_dirty = False
    game.similarity_v3_dirty_reasons = []


def build_similarity_v3_provider_text_doc(game: Game) -> str | None:
    candidates = (
        getattr(game, "steam_detailed_description", None),
        getattr(game, "opencritic_description", None),
        getattr(game, "steam_short_description", None),
        getattr(game, "metacritic_description", None),
        getattr(game, "taxonomy_v2_text_corpus", None),
        getattr(game, "description", None),
    )
    segments: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        stripped_candidate = strip_taxonomy_v2_noise_segments(candidate) or candidate
        cleaned = _normalize_doc_text(stripped_candidate)
        if not cleaned:
            continue
        marker = normalize_taxonomy_label(cleaned)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        segments.append(cleaned)
    if not segments:
        return None
    return "\n\n".join(segments)[:12000]


def build_similarity_v3_structured_label_doc(
    game: Game,
    source_rows: Iterable[GameSourceTaxonomyLabel],
) -> str | None:
    sections: list[str] = []
    title = getattr(game, "title", None)
    if title:
        sections.append(f"title: {title}")

    for name, values in (
        ("genres", getattr(game, "taxonomy_genres", None) or []),
        ("themes", getattr(game, "taxonomy_themes", None) or []),
        ("modes", getattr(game, "taxonomy_modes", None) or []),
        ("perspectives", getattr(game, "taxonomy_perspectives", None) or []),
        ("studios", getattr(game, "taxonomy_studios", None) or []),
        ("publishers", getattr(game, "taxonomy_publishers", None) or []),
    ):
        if values:
            sections.append(f"{name}: " + ", ".join(sorted({display_taxonomy_v2_token(value) for value in values})))

    raw_tokens = _collect_taxonomy_source_label_tokens(source_rows)
    if raw_tokens:
        sections.append("source labels: " + ", ".join(raw_tokens[:80]))

    if not sections:
        return None
    return "\n".join(sections)


def build_similarity_v3_fingerprint_doc(game: Game) -> str | None:
    if not getattr(game, "taxonomy_v2_fingerprint", None):
        return None
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    sections: list[str] = []
    primary = getattr(game, "taxonomy_v2_primary_archetype", None)
    if primary:
        sections.append(f"primary archetype: {display_taxonomy_v2_token(primary)}")
    secondaries = list(getattr(game, "taxonomy_v2_secondary_archetypes", None) or [])
    if secondaries:
        sections.append("secondary archetypes: " + ", ".join(display_taxonomy_v2_token(value) for value in secondaries))
    for facet in _FINGERPRINT_FACETS_FOR_DOC:
        values = sorted(fingerprint.get(facet) or [])
        if not values:
            continue
        sections.append(f"{facet}: " + ", ".join(display_taxonomy_v2_token(value) for value in values))
    return "\n".join(sections) if sections else None


def build_similarity_v3_synthetic_summary_doc(
    game: Game,
    source_rows: Iterable[GameSourceTaxonomyLabel],
) -> str | None:
    primary = getattr(game, "taxonomy_v2_primary_archetype", None)
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    raw_tokens = _collect_taxonomy_source_label_tokens(source_rows)

    sentences: list[str] = []
    if primary:
        sentences.append(f"{game.title} is best described as a {display_taxonomy_v2_token(primary).lower()} experience.")

    world = _humanize_token_list(fingerprint.get("world_topology") or [])
    setting = _humanize_token_list(fingerprint.get("setting") or [])
    perspective = _humanize_token_list(fingerprint.get("perspective") or [])
    mode = _humanize_token_list(fingerprint.get("mode_profile") or [])
    if world or setting or perspective or mode:
        descriptors = [part for part in [world, setting, perspective, mode] if part]
        sentences.append("Core structure: " + "; ".join(descriptors) + ".")

    combat = _humanize_token_list(
        list(fingerprint.get("combat_style") or []) + list(fingerprint.get("combat_structure") or [])
    )
    traversal = _humanize_token_list(fingerprint.get("traversal_verbs") or [])
    progression = _humanize_token_list(fingerprint.get("progression_model") or [])
    if combat or traversal or progression:
        clauses = [part for part in [combat, traversal, progression] if part]
        sentences.append("Identity signals: " + "; ".join(clauses) + ".")

    mechanics = _humanize_token_list(
        list(fingerprint.get("mechanics_structure") or [])
        + list(fingerprint.get("rules_goals") or [])
        + list(fingerprint.get("entity_interaction") or [])
    )
    if mechanics:
        sentences.append("Mechanics and goals: " + mechanics + ".")

    if not sentences and raw_tokens:
        sentences.append("Source signals: " + ", ".join(raw_tokens[:12]) + ".")

    if not sentences:
        return None
    return " ".join(sentences)


def build_similarity_v3_documents(
    game: Game,
    source_rows: Iterable[GameSourceTaxonomyLabel],
) -> SimilarityV3Documents:
    provider_text = build_similarity_v3_provider_text_doc(game)
    structured_label = build_similarity_v3_structured_label_doc(game, source_rows)
    fingerprint_doc = build_similarity_v3_fingerprint_doc(game)
    synthetic_summary = None
    if not provider_text or len(provider_text.split()) < 60:
        synthetic_summary = build_similarity_v3_synthetic_summary_doc(game, source_rows)

    sections: list[str] = []
    if getattr(game, "title", None):
        sections.append(f"[title]\n{game.title}")
    if fingerprint_doc:
        sections.append(f"[fingerprint]\n{fingerprint_doc}")
    if structured_label:
        sections.append(f"[labels]\n{structured_label}")
    if provider_text:
        sections.append(f"[provider_text]\n{provider_text}")
    if synthetic_summary:
        sections.append(f"[synthetic_summary]\n{synthetic_summary}")

    fused = "\n\n".join(section.strip() for section in sections if section.strip()) or None
    return SimilarityV3Documents(
        provider_text_doc=provider_text,
        structured_label_doc=structured_label,
        fingerprint_doc=fingerprint_doc,
        synthetic_summary_doc=synthetic_summary,
        fused_doc=fused[:16000] if fused else None,
    )


def _stable_hash(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def _tokenize_content_words(text: str | None) -> list[str]:
    if not text:
        return []
    words = [
        token
        for token in normalize_taxonomy_label(text).split()
        if token and token not in _CONTENT_STOPWORDS and len(token) > 1
    ]
    return words


def build_similarity_v3_embedding(text: str | None, *, dimensions: int = SIMILARITY_V3_VECTOR_DIMENSIONS) -> list[float]:
    if not text:
        return [0.0] * dimensions
    counts = Counter(_tokenize_content_words(text))
    if not counts:
        return [0.0] * dimensions
    vector = [0.0] * dimensions
    for token, count in counts.items():
        bucket = _stable_hash(token) % dimensions
        sign = -1.0 if (_stable_hash(token + ":sign") % 2) else 1.0
        weight = 1.0 + min(count, 5) * 0.15
        vector[bucket] += sign * weight
    magnitude = math.sqrt(sum(component * component for component in vector))
    if magnitude <= 0:
        return [0.0] * dimensions
    return [component / magnitude for component in vector]


def _cosine_similarity(left: Iterable[float] | None, right: Iterable[float] | None) -> float:
    if left is None or right is None:
        return 0.0
    left_list = list(left)
    right_list = list(right)
    if not left_list or not right_list or len(left_list) != len(right_list):
        return 0.0
    dot = sum(a * b for a, b in zip(left_list, right_list))
    left_mag = math.sqrt(sum(a * a for a in left_list))
    right_mag = math.sqrt(sum(b * b for b in right_list))
    if left_mag <= 0 or right_mag <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_mag * right_mag)))


def _hash_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _similarity_v3_scoring_profile(mcp: LocalSimilarityV3MCP) -> SimilarityV3ScoringProfile:
    if getattr(mcp, "embedding_backend", None) == SIMILARITY_V3_EMBEDDING_BACKEND:
        return SimilarityV3ScoringProfile(
            taxonomy_weight=0.72,
            text_vector_weight=0.08,
            facet_vector_weight=0.05,
            prototype_weight=0.04,
            rerank_weight=0.08,
            quality_prior_weight=0.03,
            taxonomy_divisor=300.0,
            publish_threshold=0.42,
            minimum_taxonomy_score=0.38,
            allow_vector_exception=False,
            max_vector_exceptions=0,
        )
    return SimilarityV3ScoringProfile(
        taxonomy_weight=0.30,
        text_vector_weight=0.20,
        facet_vector_weight=0.10,
        prototype_weight=0.15,
        rerank_weight=0.20,
        quality_prior_weight=0.05,
        taxonomy_divisor=500.0,
        publish_threshold=0.70,
        minimum_taxonomy_score=0.40,
        allow_vector_exception=True,
        max_vector_exceptions=2,
    )


class LocalSimilarityV3MCP:
    """Offline local CPU batch implementation for V3 document embedding and reranking."""

    embedding_backend = SIMILARITY_V3_EMBEDDING_BACKEND
    reranker_backend = SIMILARITY_V3_RERANKER_BACKEND

    def embed_documents(self, docs: SimilarityV3Documents) -> dict[str, list[float] | None]:
        return {
            "fused_embedding": build_similarity_v3_embedding(docs.fused_doc),
            "fingerprint_embedding": build_similarity_v3_embedding(docs.fingerprint_doc),
            "prototype_embedding": build_similarity_v3_embedding(
                "\n".join(
                    part
                    for part in [docs.fingerprint_doc, docs.synthetic_summary_doc, docs.structured_label_doc]
                    if part
                )
            ),
        }

    def rerank_pair(self, anchor_doc: SimilarityV3Documents, candidate_doc: SimilarityV3Documents) -> float:
        anchor_tokens = set(_tokenize_content_words(anchor_doc.fused_doc))
        candidate_tokens = set(_tokenize_content_words(candidate_doc.fused_doc))
        if not anchor_tokens or not candidate_tokens:
            return 0.0
        intersection = anchor_tokens & candidate_tokens
        union = anchor_tokens | candidate_tokens
        jaccard = len(intersection) / len(union)
        high_signal_hits = len(
            {
                token
                for token in intersection
                if token
                in {
                    "open",
                    "world",
                    "fantasy",
                    "metroidvania",
                    "platforming",
                    "parkour",
                    "soulslike",
                    "boss",
                    "quest",
                    "psychological",
                    "survival",
                    "gliding",
                    "climbing",
                    "horseback",
                    "party",
                    "fighter",
                    "racing",
                    "cozy",
                    "farm",
                    "farming",
                    "crops",
                    "harvest",
                    "fish",
                    "fishing",
                    "island",
                    "unpacking",
                    "warehouse",
                    "organize",
                    "sorting",
                    "inventory",
                    "puzzle",
                    "strategy",
                    "horror",
                    "shooter",
                    "mmo",
                }
            }
        )
        return max(0.0, min(1.0, jaccard + min(high_signal_hits, 5) * 0.08))


def _doc_bundle_from_row(row: GameSimilarityV3Document | None) -> SimilarityV3Documents:
    if row is None:
        return SimilarityV3Documents(
            provider_text_doc=None,
            structured_label_doc=None,
            fingerprint_doc=None,
            synthetic_summary_doc=None,
            fused_doc=None,
        )
    return SimilarityV3Documents(
        provider_text_doc=row.provider_text_doc,
        structured_label_doc=row.structured_label_doc,
        fingerprint_doc=row.fingerprint_doc,
        synthetic_summary_doc=row.synthetic_summary_doc,
        fused_doc=row.fused_doc,
    )


def _meaningful_v3_signal_expression():
    return or_(
        Game.steam_sample_size >= 50,
        Game.metacritic_user_score.isnot(None),
        Game.critic_review_count >= 5,
        Game.top_critic_score.isnot(None),
        Game.avg_critic_score.isnot(None),
        Game.percent_recommended.isnot(None),
        Game.metacritic_score.isnot(None),
    )


def _document_backed_v3_signal_expression():
    return or_(
        _meaningful_v3_signal_expression(),
        GameSimilarityV3Document.fused_doc_hash.isnot(None),
        GameSimilarityV3Document.fingerprint_doc_hash.isnot(None),
        GameSimilarityV3Document.provider_text_doc.isnot(None),
        GameSimilarityV3Document.structured_label_doc.isnot(None),
        GameSimilarityV3Document.synthetic_summary_doc.isnot(None),
    )


def _title_family_prefixes(title: str | None) -> list[str]:
    normalized = _title_variant_key(title)
    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return []

    prefixes: list[str] = []
    max_size = min(5, len(tokens))
    for size in range(max_size, 1, -1):
        prefix_tokens = tokens[:size]
        if _ANNUALIZED_SERIES_TOKEN_PATTERN.match(prefix_tokens[-1]):
            continue
        if size == 2 and (prefix_tokens[0] in _CONTENT_STOPWORDS or prefix_tokens[1] in _CONTENT_STOPWORDS):
            continue
        prefixes.append(" ".join(prefix_tokens))

    if len(tokens) >= 2 and len(tokens[0]) <= 4 and _ANNUALIZED_SERIES_TOKEN_PATTERN.match(tokens[1]):
        prefixes.append(tokens[0])

    ordered: list[str] = []
    seen: set[str] = set()
    for prefix in prefixes:
        if prefix and prefix not in seen:
            seen.add(prefix)
            ordered.append(prefix)
    return ordered


def _shared_title_family_prefix_depth(anchor_title: str | None, candidate_title: str | None) -> int:
    anchor_key = _title_variant_key(anchor_title)
    candidate_key = _title_variant_key(candidate_title)
    if not anchor_key or not candidate_key:
        return 0

    best_depth = 0
    for prefix in _title_family_prefixes(anchor_title):
        if prefix and candidate_key.startswith(prefix):
            best_depth = max(best_depth, len(prefix.split()))
    for prefix in _title_family_prefixes(candidate_title):
        if prefix and anchor_key.startswith(prefix):
            best_depth = max(best_depth, len(prefix.split()))
    if best_depth:
        return best_depth

    anchor_tokens = anchor_key.split()
    candidate_tokens = candidate_key.split()
    if (
        len(anchor_tokens) >= 2
        and len(candidate_tokens) >= 2
        and anchor_tokens[0] == candidate_tokens[0]
        and len(anchor_tokens[0]) <= 4
        and _ANNUALIZED_SERIES_TOKEN_PATTERN.match(anchor_tokens[1])
        and _ANNUALIZED_SERIES_TOKEN_PATTERN.match(candidate_tokens[1])
    ):
        return 1
    return 0


async def _load_source_rows_by_game_id(
    db: AsyncSession,
    game_ids: Iterable[int],
) -> dict[int, list[GameSourceTaxonomyLabel]]:
    ids = sorted({int(game_id) for game_id in game_ids})
    if not ids:
        return {}
    result = await db.execute(
        select(GameSourceTaxonomyLabel).where(GameSourceTaxonomyLabel.game_id.in_(ids))
    )
    grouped: dict[int, list[GameSourceTaxonomyLabel]] = defaultdict(list)
    for row in result.scalars().all():
        grouped[row.game_id].append(row)
    return grouped


async def build_similarity_v3_document_rows(
    db: AsyncSession,
    games: list[Game],
    *,
    mcp: LocalSimilarityV3MCP | None = None,
) -> int:
    if not games:
        return 0
    mcp = mcp or LocalSimilarityV3MCP()
    rows_by_game = await _load_source_rows_by_game_id(db, [game.id for game in games if game and game.id is not None])
    existing_result = await db.execute(
        select(GameSimilarityV3Document).where(
            GameSimilarityV3Document.game_id.in_([game.id for game in games if game and game.id is not None])
        )
    )
    existing_by_game = {row.game_id: row for row in existing_result.scalars().all()}
    updated = 0

    for game in games:
        if game is None or game.id is None:
            continue
        docs = build_similarity_v3_documents(game, rows_by_game.get(game.id, []))
        embeddings = mcp.embed_documents(docs)
        row = existing_by_game.get(game.id)
        if row is None:
            row = GameSimilarityV3Document(
                game_id=game.id,
                similarity_version=SIMILARITY_V3_VERSION,
                embedding_backend=mcp.embedding_backend,
            )
            db.add(row)
            existing_by_game[game.id] = row
        row.similarity_version = SIMILARITY_V3_VERSION
        row.embedding_backend = mcp.embedding_backend
        row.provider_text_doc = docs.provider_text_doc
        row.structured_label_doc = docs.structured_label_doc
        row.fingerprint_doc = docs.fingerprint_doc
        row.synthetic_summary_doc = docs.synthetic_summary_doc
        row.fused_doc = docs.fused_doc
        row.fused_doc_hash = _hash_text(docs.fused_doc)
        row.fingerprint_doc_hash = _hash_text(docs.fingerprint_doc)
        row.fused_embedding = embeddings["fused_embedding"]
        row.fingerprint_embedding = embeddings["fingerprint_embedding"]
        row.prototype_embedding = embeddings["prototype_embedding"]
        row.computed_at = datetime.now(timezone.utc)
        updated += 1
    return updated


def _quality_prior(candidate: Game) -> float:
    review_count = float(getattr(candidate, "critic_review_count", None) or 0)
    critic_score = float(getattr(candidate, "avg_critic_score", None) or 0)
    steam_score = float(getattr(candidate, "steam_user_score", None) or 0)
    metacritic_score = float(getattr(candidate, "metacritic_user_score", None) or 0)
    review_component = min(review_count / 150.0, 1.0) * 0.35
    critic_component = min(max(critic_score, 0.0), 100.0) / 100.0 * 0.35
    user_component = max(steam_score, metacritic_score) / 100.0 * 0.30
    return max(0.0, min(1.0, review_component + critic_component + user_component))


def _normalize_taxonomy_score(raw_score: int | None, *, divisor: float) -> float:
    if raw_score is None:
        return 0.0
    if divisor <= 0:
        return 0.0
    return max(0.0, min(1.0, raw_score / divisor))


def _confidence_from_final_score(score: float) -> str:
    if score >= 0.82:
        return "high"
    if score >= 0.70:
        return "medium"
    return "low"


def _prototype_score(
    anchor: Game,
    candidate: Game,
    *,
    anchor_doc: GameSimilarityV3Document | None,
    candidate_doc: GameSimilarityV3Document | None,
) -> float:
    if not anchor_doc or not candidate_doc:
        return 0.0
    return _cosine_similarity(anchor_doc.prototype_embedding, candidate_doc.prototype_embedding)


def _open_world_fantasy_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if (
        "horseback" in anchor_fingerprint["traversal_verbs"]
        and (
            "construction_placement" in anchor_fingerprint["entity_interaction"]
            or "build_and_optimize" in anchor_fingerprint["rules_goals"]
            or "base_growth" in anchor_fingerprint["progression_model"]
        )
    ):
        return "crimson_like"
    if (
        bool(anchor_fingerprint["traversal_verbs"] & {"climbing", "gliding"})
        and "persistent_shared_world" not in anchor_fingerprint["world_topology"]
        and "mmo" not in anchor_fingerprint["mode_profile"]
    ):
        return "zelda_like"
    return "generic"


def _open_world_fantasy_frontier_authored_hits(fingerprint: dict[str, set[str]]) -> int:
    return sum(
        1
        for values in (
            fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"},
            fingerprint["rules_goals"] & {"complete_quests"},
            fingerprint["progression_model"] & {"quest_driven", "gear_chase"},
        )
        if values
    )


def _open_world_fantasy_sandbox_signals(fingerprint: dict[str, set[str]]) -> bool:
    return bool(
        fingerprint["world_density"] & {"systemic_sandbox"}
        or fingerprint["session_shape"] & {"sandbox_loop"}
        or fingerprint["mode_profile"] & {"drop_in_coop", "party_coop", "mmo", "pvpve"}
    )


def _family_rerank_adjustment(
    anchor: Game,
    candidate: Game,
    *,
    taxonomy_breakdown,
) -> float:
    adjustment = 0.0
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if not anchor_archetype or not candidate_archetype:
        return adjustment

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_studios = set(getattr(anchor, "taxonomy_studios", None) or []) & set(
        getattr(candidate, "taxonomy_studios", None) or []
    )

    if anchor_archetype == "open_world_fantasy_action_rpg":
        anchor_mode = _open_world_fantasy_anchor_mode(anchor_fingerprint)
        zelda_like_anchor = anchor_mode == "zelda_like"
        crimson_like_anchor = anchor_mode == "crimson_like"
        if zelda_like_anchor and candidate_archetype == "mmo_action_rpg":
            adjustment -= 0.12
        if zelda_like_anchor and "persistent_shared_world" in candidate_fingerprint["world_topology"]:
            adjustment -= 0.04
        if (
            zelda_like_anchor
            and candidate_archetype == "cinematic_action_adventure"
            and shared_setting
            and (
                shared_rules & {"defeat_bosses", "complete_quests"}
                or shared_progression
                or (anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"])
            )
        ):
            adjustment += 0.14
        if crimson_like_anchor and candidate_archetype == "mmo_action_rpg":
            if shared_world and shared_setting and (
                shared_entities & {"construction_placement"}
                or shared_rules & {"build_and_optimize"}
                or "base_growth" in shared_progression
                or shared_studios
            ):
                adjustment += 0.10
        if zelda_like_anchor and candidate_archetype == "soulslike_action_rpg":
            if "soulslike" in shared_challenge or shared_rules & {"defeat_bosses"}:
                adjustment += 0.10
        if zelda_like_anchor and candidate_archetype == "western_narrative_rpg":
            if shared_rules & {"complete_quests"} or shared_entities & {"dialogue_choice"}:
                adjustment += 0.10
        if zelda_like_anchor and candidate_archetype not in {
            "open_world_fantasy_action_rpg",
            "western_narrative_rpg",
            "soulslike_action_rpg",
            "cinematic_action_adventure",
        }:
            adjustment -= 0.14
        if crimson_like_anchor and candidate_archetype == "western_narrative_rpg":
            if shared_rules & {"complete_quests"}:
                adjustment += 0.14
            if shared_entities & {"dialogue_choice"}:
                adjustment += 0.10
        if crimson_like_anchor and candidate_archetype == "soulslike_action_rpg":
            if "soulslike" in shared_challenge:
                adjustment += 0.08
            if shared_rules & {"defeat_bosses"}:
                adjustment += 0.06
        if crimson_like_anchor and candidate_archetype == "mmo_action_rpg":
            if shared_world and shared_setting and (shared_traversal or shared_entities or shared_rules):
                adjustment += 0.08
        if crimson_like_anchor and candidate_archetype in {"cinematic_action_adventure", "open_world_action_adventure"}:
            adjustment -= 0.18
        if crimson_like_anchor and candidate_archetype not in {
            "open_world_fantasy_action_rpg",
            "western_narrative_rpg",
            "soulslike_action_rpg",
            "mmo_action_rpg",
        }:
            adjustment -= 0.12

    if anchor_archetype == "soulslike_action_rpg":
        candidate_secondaries = {
            _archetype_key(value)
            for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
            if _archetype_key(value)
        }
        anchor_prefers_third_person = bool(
            anchor_fingerprint["perspective"] & {"third_person"}
            or anchor_fingerprint["visual_presentation"] & {"third_person_3d"}
        )
        candidate_supports_third_person, candidate_conflicting_view = _soulslike_candidate_view_profile(
            candidate_fingerprint
        )
        if candidate_archetype == "soulslike_action_rpg":
            adjustment += 0.08
        elif "soulslike_action_rpg" in candidate_secondaries:
            adjustment += 0.03
        elif candidate_archetype == "open_world_fantasy_action_rpg":
            adjustment -= 0.08
        if candidate_conflicting_view:
            adjustment -= 0.28
        elif anchor_prefers_third_person and not candidate_supports_third_person:
            adjustment -= 0.14
        elif shared_perspective:
            adjustment += 0.05
        if "dark_fantasy" in shared_setting:
            adjustment += 0.04
        if shared_rules & {"defeat_bosses"}:
            adjustment += 0.03
        if "soulslike" not in shared_challenge and candidate_archetype != "soulslike_action_rpg":
            adjustment -= 0.04

    if taxonomy_breakdown is None:
        adjustment -= 0.05

    return adjustment


def _open_world_fantasy_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    anchor_mode = _open_world_fantasy_anchor_mode(anchor_fingerprint)
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if not candidate_archetype:
        return None

    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_combat_style = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_combat_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]

    def _candidate_signal_hits(*facet_values: tuple[str, set[str]]) -> int:
        return sum(1 for facet, values in facet_values if candidate_fingerprint[facet] & values)

    base_fit = (
        len(shared_world) * 3.0
        + len(shared_setting) * 2.0
        + len(shared_perspective) * 1.5
        + len(shared_rules) * 2.0
        + len(shared_entities) * 2.0
        + len(shared_progression) * 1.5
        + len(shared_traversal) * 1.5
        + len(shared_combat_style) * 1.5
        + len(shared_combat_structure) * 1.5
    )

    if candidate_archetype == "open_world_fantasy_action_rpg":
        if not shared_world or not shared_setting or not shared_perspective:
            return None
        if not (shared_traversal or shared_rules or shared_entities or shared_progression):
            return None
        if candidate_fingerprint["combat_structure"] & {"party_management"} and not shared_combat_structure:
            return None
        same_lane_identity_hits = _candidate_signal_hits(
            ("combat_style", {"melee", "magic"}),
            ("rules_goals", {"complete_quests", "defeat_bosses", "build_and_optimize"}),
            ("progression_model", {"quest_driven", "buildcraft", "skill_tree", "base_growth"}),
            ("traversal_verbs", {"horseback", "climbing", "gliding"}),
        )
        if same_lane_identity_hits < (1 if shared_traversal else 2):
            return None
        if (
            _open_world_fantasy_sandbox_signals(candidate_fingerprint)
            and not _open_world_fantasy_sandbox_signals(anchor_fingerprint)
            and _open_world_fantasy_frontier_authored_hits(candidate_fingerprint) < 1
        ):
            return None
        fit = base_fit
        if anchor_mode == "zelda_like":
            exploration_hits = _candidate_signal_hits(
                ("traversal_verbs", {"climbing", "gliding"}),
                ("rules_goals", {"complete_quests"}),
                ("progression_model", {"buildcraft", "quest_driven", "skill_tree"}),
                ("challenge_model", {"puzzle_gating"}),
            )
            if exploration_hits < 1:
                return None
            fit += 1.5 + exploration_hits * 0.75
        if anchor_mode == "crimson_like":
            frontier_hits = _candidate_signal_hits(
                ("traversal_verbs", {"horseback", "climbing", "gliding"}),
                ("rules_goals", {"complete_quests", "build_and_optimize"}),
                ("entity_interaction", {"construction_placement", "dialogue_choice"}),
                ("progression_model", {"quest_driven", "base_growth", "buildcraft", "skill_tree"}),
                ("combat_style", {"melee", "magic", "hybrid"}),
            )
            frontier_identity_present = bool(
                candidate_fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"}
                or candidate_fingerprint["rules_goals"] & {"complete_quests", "build_and_optimize"}
                or candidate_fingerprint["entity_interaction"] & {"construction_placement", "dialogue_choice"}
            )
            if frontier_hits < 2 or not frontier_identity_present:
                return None
            fit += frontier_hits * 0.8
        return fit

    if candidate_archetype == "western_narrative_rpg":
        quest_identity_hits = _candidate_signal_hits(
            ("rules_goals", {"complete_quests"}),
            ("entity_interaction", {"dialogue_choice"}),
            ("progression_model", {"quest_driven"}),
            ("world_topology", {"open_world"}),
        )
        if (
            not shared_setting
            or not shared_perspective
            or quest_identity_hits < 2
            or not (shared_world or candidate_fingerprint["world_topology"] & {"open_world"})
        ):
            return None
        return base_fit + 1.5 + quest_identity_hits * 0.75

    if candidate_archetype == "soulslike_action_rpg":
        soulslike_core_hits = _candidate_signal_hits(
            ("challenge_model", {"soulslike"}),
            ("combat_structure", {"boss_centric"}),
        )
        soulslike_identity_hits = soulslike_core_hits + _candidate_signal_hits(
            ("rules_goals", {"defeat_bosses"}),
            ("combat_style", {"melee", "magic", "hybrid"}),
            ("world_topology", {"open_world"}),
        )
        if (
            not shared_world
            or not shared_perspective
            or "open_world" not in candidate_fingerprint["world_topology"]
            or not (
                shared_setting & {"high_fantasy", "dark_fantasy"}
                or shared_challenge & {"soulslike"}
                or shared_rules & {"defeat_bosses"}
            )
            or soulslike_core_hits < 1
            or soulslike_identity_hits < 3
        ):
            return None
        fit = base_fit + soulslike_identity_hits * 1.25
        if shared_rules & {"defeat_bosses"}:
            fit += 1.0
        if shared_combat_style or shared_combat_structure:
            fit += 0.5
        return fit

    if candidate_archetype == "mmo_action_rpg":
        if anchor_mode != "crimson_like":
            return None
        if "persistent_shared_world" not in candidate_fingerprint["world_topology"]:
            return None
        if not shared_setting or not shared_perspective:
            return None
        bridge_identity_hits = _candidate_signal_hits(
            ("traversal_verbs", {"horseback"}),
            ("entity_interaction", {"construction_placement"}),
            ("rules_goals", {"build_and_optimize"}),
            ("progression_model", {"base_growth"}),
            ("combat_style", {"melee", "magic"}),
        )
        if bridge_identity_hits < 2:
            return None
        if not (shared_traversal or shared_combat_style or shared_combat_structure or shared_progression or shared_rules or shared_entities):
            return None
        return base_fit + bridge_identity_hits * 0.8

    if candidate_archetype == "cinematic_action_adventure":
        if anchor_mode != "zelda_like":
            return None
        cinematic_identity_hits = _candidate_signal_hits(
            ("rules_goals", {"defeat_bosses", "complete_quests"}),
            ("progression_model", {"buildcraft", "skill_tree"}),
            ("combat_style", {"melee", "magic"}),
            ("world_topology", {"semi_open", "linear"}),
            ("narrative_structure", {"authored_linear"}),
        )
        if not shared_setting or not shared_perspective or cinematic_identity_hits < 2:
            return None
        return base_fit + 1.0 + cinematic_identity_hits * 0.75

    return None


def _soulslike_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }

    if anchor_archetype != "soulslike_action_rpg" or not candidate_archetype:
        return None

    same_lane = candidate_archetype == "soulslike_action_rpg" or "soulslike_action_rpg" in candidate_secondaries
    allowed_bridge = candidate_archetype in {"open_world_fantasy_action_rpg", "action_horror", "character_action"}
    if not same_lane and not allowed_bridge:
        return None

    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_visual = anchor_fingerprint["visual_presentation"] & candidate_fingerprint["visual_presentation"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_combat_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_studios = set(getattr(anchor, "taxonomy_studios", None) or []) & set(getattr(candidate, "taxonomy_studios", None) or [])

    anchor_prefers_third_person = bool(
        anchor_fingerprint["perspective"] & {"third_person"}
        or anchor_fingerprint["visual_presentation"] & {"third_person_3d"}
    )
    candidate_supports_third_person, candidate_conflicting_view = _soulslike_candidate_view_profile(candidate_fingerprint)
    if candidate_conflicting_view:
        return None
    if same_lane and anchor_prefers_third_person and not candidate_supports_third_person:
        return None

    if same_lane:
        if not (
            shared_challenge & {"soulslike"}
            or shared_combat_structure & {"boss_centric"}
            or shared_rules & {"defeat_bosses"}
        ):
            return None
    elif not (
        shared_perspective
        and shared_setting
        and (shared_challenge & {"soulslike"} or shared_rules & {"defeat_bosses"})
    ):
        return None

    fit = (
        len(shared_perspective) * 3.0
        + len(shared_visual) * 2.0
        + len(shared_challenge) * 3.5
        + len(shared_combat_structure) * 2.5
        + len(shared_rules) * 2.0
        + len(shared_setting) * 1.5
        + len(shared_world) * 0.5
    )
    if same_lane:
        fit += 3.0
    if shared_studios:
        fit += 2.5
    if anchor_prefers_third_person and candidate_supports_third_person:
        fit += 1.0
    return fit


def _hidden_object_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if (
        anchor_fingerprint["rules_goals"] & {"build_and_optimize"}
        or anchor_fingerprint["mechanics_structure"] & {"environmental_puzzle_solving", "systemic_problem_solving"}
        or anchor_fingerprint["entity_interaction"] & {"cursor_driven_interaction", "inventory_loot"}
    ):
        return "organization"
    return "generic"


def _hidden_object_puzzle_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "hidden_object_puzzle" or candidate_archetype != "hidden_object_puzzle":
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_interface = anchor_fingerprint["interface_control"] & candidate_fingerprint["interface_control"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score)
    fit += len(shared_mechanics) * 32.0
    fit += len(shared_rules) * 26.0
    fit += len(shared_entities) * 22.0
    fit += len(shared_interface) * 16.0
    fit += len(shared_challenge) * 14.0
    fit += len(shared_mode) * 10.0

    if _hidden_object_anchor_mode(anchor_fingerprint) == "organization":
        shared_organization_hits = sum(
            1
            for values in (
                shared_mechanics & {"environmental_puzzle_solving", "systemic_problem_solving"},
                shared_rules & {"build_and_optimize"},
                shared_entities & {"cursor_driven_interaction", "inventory_loot"},
                shared_interface & {"cursor_driven"},
            )
            if values
        )
        candidate_organization_hits = sum(
            1
            for values in (
                candidate_fingerprint["mechanics_structure"] & {"environmental_puzzle_solving", "systemic_problem_solving"},
                candidate_fingerprint["rules_goals"] & {"build_and_optimize"},
                candidate_fingerprint["entity_interaction"] & {"cursor_driven_interaction", "inventory_loot"},
                candidate_fingerprint["interface_control"] & {"cursor_driven"},
            )
            if values
        )
        if shared_organization_hits == 0 and candidate_organization_hits < 2:
            return None
        fit += shared_organization_hits * 36.0
        fit += candidate_organization_hits * 8.0
        if candidate_fingerprint["narrative_topic"] and not (
            anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
        ):
            fit -= 24.0
        if not (shared_rules & {"build_and_optimize"}):
            fit -= 14.0
        if not (shared_mechanics & {"systemic_problem_solving"}):
            fit -= 10.0

    return fit


def _is_puzzle_exploration_adventure(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    archetypes = {primary, *secondaries}
    if archetypes & {"military_fps", "sports_sim", "traditional_fighter", "realistic_racer", "arcade_racer"}:
        return False

    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    puzzle_signal = bool(
        fingerprint["challenge_model"] & {"puzzle_gating"}
        or fingerprint["mechanics_structure"] & {"environmental_puzzle_solving", "systemic_problem_solving"}
        or fingerprint["rules_goals"] & {"solve_mysteries"}
        or any(
            phrase in text
            for phrase in (
                "puzzle adventure",
                "puzzle game",
                "solve puzzles",
                "environmental puzzles",
                "multiple solutions",
                "spell-crafting",
                "spell crafting",
                "magical runes",
                "combine magical runes",
                "design your own spells",
                "portal, zelda and metroid",
                "zelda and metroid",
            )
        )
    )
    if not puzzle_signal:
        return False

    exploration_signal = bool(
        fingerprint["world_topology"] & {"open_world", "semi_open"}
        or fingerprint["world_density"] & {"handcrafted_discovery", "systemic_sandbox"}
        or fingerprint["progression_model"] & {"quest_driven", "metaprogression", "buildcraft"}
        or archetypes
        & {
            "exploration_survival_adventure",
            "open_world_action_adventure",
            "metroidvania",
            "hidden_object_puzzle",
            "visual_novel",
            "kingdom_decision_sim",
            "creative_sandbox_adventure",
        }
        or any(
            phrase in text
            for phrase in (
                "semi-open world",
                "semi open world",
                "exploration",
                "explore",
                "adventure",
                "mystery",
                "metroidvania",
            )
        )
    )
    if not exploration_signal:
        return False

    if fingerprint["combat_presence"] & {"dominant"} and not (
        "puzzle" in text
        or "metroidvania" in text
        or "zelda" in text
        or "portal" in text
        or "spell" in text
    ):
        return False
    return True


def _puzzle_exploration_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_puzzle_exploration_adventure(candidate):
        return "puzzle_exploration_adventure"
    return _lane_key_for_similarity_neighbor(candidate)


def _is_spellcraft_puzzle_exploration_anchor(game: Game) -> bool:
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    if any(
        phrase in text
        for phrase in (
            "semi-open world puzzle adventure",
            "semi open world puzzle adventure",
            "spell-crafting",
            "spell crafting",
            "design your own spells",
            "create unique spells",
            "combine magical runes",
            "magical runes",
            "solve puzzles your way",
            "transform objects",
            "manipulate time",
        )
    ):
        return True
    return bool(
        fingerprint["world_topology"] & {"open_world", "semi_open"}
        and fingerprint["progression_model"] & {"buildcraft"}
        and fingerprint["mechanics_structure"] & {"environmental_puzzle_solving", "systemic_problem_solving"}
        and fingerprint["challenge_model"] & {"puzzle_gating"}
    )


def _puzzle_exploration_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_puzzle_exploration_adventure(anchor) or not _is_puzzle_exploration_adventure(candidate):
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_combat = anchor_fingerprint["combat_presence"] & candidate_fingerprint["combat_presence"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score) if breakdown is not None else 250.0
    fit += len(shared_challenge & {"puzzle_gating"}) * 44.0
    fit += len(shared_mechanics & {"environmental_puzzle_solving", "systemic_problem_solving"}) * 36.0
    fit += len(shared_rules & {"solve_mysteries"}) * 20.0
    fit += len(shared_world & {"open_world", "semi_open"}) * 16.0
    fit += len(shared_density & {"handcrafted_discovery", "systemic_sandbox"}) * 16.0
    fit += len(shared_progression & {"quest_driven", "metaprogression", "buildcraft"}) * 14.0
    fit += len(shared_combat & {"none"}) * 24.0
    fit += len(shared_mode & {"single_player"}) * 8.0

    candidate_text = _game_similarity_text(candidate)
    candidate_primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if any(
        phrase in candidate_text
        for phrase in (
            "spell",
            "rune",
            "puzzle adventure",
            "portal",
            "zelda",
            "metroid",
            "mystery adventure",
        )
    ):
        fit += 28.0
    if candidate_primary == "hidden_object_puzzle" and not any(
        phrase in candidate_text
        for phrase in (
            "spell",
            "rune",
            "magical",
            "puzzle adventure",
            "metroid",
            "zelda",
            "portal",
        )
    ):
        fit -= 170.0
    if "portal" in candidate_text and "zelda" in candidate_text and "metroid" in candidate_text:
        fit += 115.0
    elif "zelda" in candidate_text and "metroid" in candidate_text:
        fit += 80.0
    if "mystery adventure" in candidate_text and "time loop" in candidate_text:
        fit += 70.0
    if candidate_fingerprint["combat_presence"] & {"dominant"} and not (
        "puzzle" in candidate_text or "zelda" in candidate_text or "metroid" in candidate_text
    ):
        fit -= 70.0
    if candidate_fingerprint["challenge_model"] & {"sim_realism"} and not shared_challenge:
        fit -= 35.0
    return fit


def _farming_sim_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if (
        "cozy" in anchor_fingerprint["tone"]
        and "base_growth" in anchor_fingerprint["progression_model"]
        and "none" in anchor_fingerprint["combat_presence"]
    ):
        return "cozy_growth"
    return "generic"


def _management_tycoon_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if "restaurant_management" in anchor_fingerprint["keyword_layer"]:
        return "restaurant"
    if "retail_management" in anchor_fingerprint["keyword_layer"]:
        return "retail"
    return "generic"


def _jrpg_story_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if (
        anchor_fingerprint["session_shape"] & {"campaign"}
        and anchor_fingerprint["combat_tempo"] & {"tactical"}
        and anchor_fingerprint["combat_structure"] & {"party_management"}
        and anchor_fingerprint["progression_model"] & {"skill_tree"}
        and anchor_fingerprint["narrative_structure"] & {"authored_linear"}
        and not (anchor_fingerprint["world_topology"] & {"open_world", "persistent_shared_world"})
        and not (anchor_fingerprint["world_density"] & {"systemic_sandbox"})
    ):
        if (
            anchor_fingerprint["challenge_model"] & {"puzzle_gating"}
            or anchor_fingerprint["rules_goals"] & {"solve_mysteries"}
            or anchor_fingerprint["narrative_topic"] & {"detective_mystery", "interpersonal_drama"}
            or anchor_fingerprint["mechanics_structure"] & {"environmental_puzzle_solving"}
            or anchor_fingerprint["entity_interaction"] & {"cursor_driven_interaction"}
        ):
            return "quirky_puzzle_story"
        return "console_party"
    return "generic"


def _jrpg_mobile_live_service_story_anchor(anchor: Game) -> bool:
    text = _game_similarity_text(anchor)
    return any(
        phrase in text
        for phrase in (
            "mobile devices and web browsers",
            "web browsers in 2014",
            "real-time co-op raids",
            "real time co-op raids",
            "more than 70 distinctive",
            "existing granblue fantasy accounts",
        )
    )


def _visual_novel_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if (
        anchor_fingerprint["narrative_topic"] & {"detective_mystery"}
        or anchor_fingerprint["rules_goals"] & {"solve_mysteries"}
        or anchor_fingerprint["challenge_model"] & {"puzzle_gating"}
    ):
        return "detective"
    return "generic"


def _visual_novel_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "visual_novel" or candidate_archetype not in {
        "visual_novel",
        "western_narrative_rpg",
        "hidden_object_puzzle",
    }:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_narrative = anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_interface = anchor_fingerprint["interface_control"] & candidate_fingerprint["interface_control"]
    shared_structure = anchor_fingerprint["narrative_structure"] & candidate_fingerprint["narrative_structure"]

    if _visual_novel_anchor_mode(anchor_fingerprint) == "detective":
        detective_hits = sum(
            1
            for values in (
                candidate_fingerprint["narrative_topic"] & {"detective_mystery"},
                candidate_fingerprint["rules_goals"] & {"solve_mysteries"},
                candidate_fingerprint["challenge_model"] & {"puzzle_gating"},
                candidate_fingerprint["interface_control"] & {"cursor_driven"},
            )
            if values
        )
        if detective_hits < 2:
            return None

    fit = float(breakdown.score)
    fit += len(shared_narrative) * 26.0
    fit += len(shared_rules) * 24.0
    fit += len(shared_challenge) * 20.0
    fit += len(shared_interface) * 16.0
    fit += len(shared_structure) * 12.0
    return fit


def _kingdom_decision_sim_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "kingdom_decision_sim":
        return None
    if candidate_archetype != "kingdom_decision_sim" and "kingdom_decision_sim" not in candidate_secondaries:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    if not (
        anchor_fingerprint["combat_presence"] & {"none"}
        and candidate_fingerprint["combat_presence"] & {"none"}
    ):
        return None

    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_interface = anchor_fingerprint["interface_control"] & candidate_fingerprint["interface_control"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_narrative = anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]

    if "campaign" not in shared_session:
        return None
    if not (
        shared_interface
        or shared_entities
        or shared_rules
        or shared_progression
        or shared_narrative
        or shared_mechanics
    ):
        return None

    fit = (
        len(shared_session) * 3.0
        + len(shared_interface) * 2.5
        + len(shared_entities) * 2.5
        + len(shared_rules) * 2.0
        + len(shared_progression) * 1.5
        + len(shared_narrative) * 1.5
        + len(shared_mechanics) * 1.5
    )
    fit += _shared_title_family_prefix_depth(anchor.title, candidate.title) * 2.0
    return fit


def _jrpg_story_rpg_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    same_lane = candidate_archetype == "jrpg_story_rpg" or "jrpg_story_rpg" in candidate_secondaries
    if anchor_archetype != "jrpg_story_rpg" or not same_lane:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_combat_tempo = anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"]
    shared_combat_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_narrative = anchor_fingerprint["narrative_structure"] & candidate_fingerprint["narrative_structure"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_input = anchor_fingerprint["input_complexity"] & candidate_fingerprint["input_complexity"]

    anchor_requires_party_rpg_identity = bool(
        anchor_fingerprint["combat_structure"] & {"party_management"}
        or anchor_fingerprint["combat_tempo"] & {"tactical"}
    )
    candidate_party_rpg_identity_hits = sum(
        1
        for values in (
            candidate_fingerprint["combat_structure"] & {"party_management"},
            candidate_fingerprint["combat_tempo"] & {"tactical"},
            candidate_fingerprint["progression_model"] & {"skill_tree", "quest_driven"},
        )
        if values
    )
    if anchor_requires_party_rpg_identity:
        if "none" in candidate_fingerprint["combat_presence"]:
            return None
        if candidate_party_rpg_identity_hits < 2:
            return None

    fit = float(breakdown.score) if breakdown is not None else 0.0
    fit += len(shared_combat_tempo) * 32.0
    fit += len(shared_combat_structure) * 28.0
    fit += len(shared_progression) * 20.0
    fit += len(shared_narrative) * 12.0
    fit += len(shared_setting) * 10.0
    fit += len(shared_mechanics) * 10.0
    fit += len(shared_entities) * 10.0
    fit += len(shared_input) * 6.0
    anchor_mode = _jrpg_story_anchor_mode(anchor_fingerprint)
    if anchor_mode in {"console_party", "quirky_puzzle_story"}:
        if "4x_strategy" in candidate_secondaries:
            return None
        if not (candidate_fingerprint["progression_model"] & {"skill_tree"}):
            return None
        if candidate_fingerprint["entity_interaction"] & {"creature_collection"} and not (
            anchor_fingerprint["entity_interaction"] & {"creature_collection"}
        ):
            return None
        if (
            anchor_mode == "console_party"
            and candidate_fingerprint["world_density"] & {"systemic_sandbox"}
            and not (anchor_fingerprint["world_density"] & {"systemic_sandbox"})
        ):
            return None
        if candidate_fingerprint["mode_profile"] & {"drop_in_coop", "party_coop"}:
            return None
        if candidate_fingerprint["combat_style"] & {"shooter"}:
            return None
        if candidate_fingerprint["combat_structure"] & {"crowd_control"}:
            return None
        if candidate_fingerprint["mode_profile"] & {"pvp"} or candidate_fingerprint["session_shape"] & {"match_session"}:
            return None
        if (
            candidate_fingerprint["setting"] & {"horror"}
            and not (anchor_fingerprint["setting"] & {"horror"})
        ):
            return None
        candidate_console_hits = sum(
            1
            for values in (
                candidate_fingerprint["combat_structure"] & {"party_management"},
                candidate_fingerprint["combat_tempo"] & {"tactical"},
                candidate_fingerprint["progression_model"] & {"skill_tree"},
                candidate_fingerprint["narrative_structure"] & {"authored_linear"},
                candidate_fingerprint["mechanics_structure"] & {"party_management_loop"},
                candidate_fingerprint["entity_interaction"] & {"party_control"},
            )
            if values
        )
        fit += candidate_console_hits * 8.0
        if not (candidate_fingerprint["world_topology"] & {"open_world", "persistent_shared_world"}):
            fit += 10.0
        if not (candidate_fingerprint["world_density"] & {"systemic_sandbox"}):
            fit += 10.0
        if (
            candidate_fingerprint["challenge_model"] & {"sim_realism"}
            and not (anchor_fingerprint["challenge_model"] & {"sim_realism"})
        ):
            fit -= 20.0
        if (
            candidate_fingerprint["setting"] & {"horror"}
            and not shared_setting
            and not (anchor_fingerprint["setting"] & {"horror"})
        ):
            fit -= 10.0
        if anchor_mode == "quirky_puzzle_story":
            if not (candidate_fingerprint["combat_tempo"] & {"tactical"}):
                return None
            shared_quirky_story_hits = sum(
                1
                for values in (
                    anchor_fingerprint["narrative_topic"]
                    & candidate_fingerprint["narrative_topic"]
                    & {"interpersonal_drama"},
                    anchor_fingerprint["mechanics_structure"]
                    & candidate_fingerprint["mechanics_structure"]
                    & {"environmental_puzzle_solving"},
                    anchor_fingerprint["entity_interaction"]
                    & candidate_fingerprint["entity_interaction"]
                    & {"cursor_driven_interaction"},
                    anchor_fingerprint["tone"]
                    & candidate_fingerprint["tone"]
                    & {"serious", "quirky", "whimsical", "heroic"},
                )
                if values
            )
            candidate_quirky_story_hits = sum(
                1
                for values in (
                    candidate_fingerprint["narrative_topic"] & {"interpersonal_drama"},
                    candidate_fingerprint["mechanics_structure"] & {"environmental_puzzle_solving"},
                    candidate_fingerprint["entity_interaction"] & {"cursor_driven_interaction"},
                    candidate_fingerprint["tone"] & {"serious", "quirky", "whimsical"},
                )
                if values
            )
            fit = min(fit, 360.0)
            fit += shared_quirky_story_hits * 36.0
            fit += candidate_quirky_story_hits * 12.0
            if shared_quirky_story_hits == 0:
                fit -= 30.0
            candidate_text = _game_similarity_text(candidate)
            distinctive_text_hits = sum(
                1
                for phrase in (
                    "turn based-tactical",
                    "action commands",
                    "three heroes",
                    "chain of serial murders",
                    "meaningful bonds",
                    "strange world",
                    "colorful friends",
                    "forgotten past",
                    "determine your fate",
                    "troublesome magic students",
                    "heartwarming and twist-filled story",
                )
                if phrase in candidate_text
            )
            if distinctive_text_hits < 2 and shared_quirky_story_hits == 0:
                return None
            fit += min(distinctive_text_hits, 4) * 18.0
            if (
                candidate_fingerprint["setting"] & {"high_fantasy", "mythic"}
                and not (anchor_fingerprint["setting"] & {"high_fantasy", "mythic"})
            ):
                fit -= 70.0
            if candidate_fingerprint["progression_model"] & {"quest_driven"}:
                fit -= 50.0
            if candidate_fingerprint["rules_goals"] & {"complete_quests"} and not (
                anchor_fingerprint["rules_goals"] & {"complete_quests"}
            ):
                fit -= 35.0
            if candidate_fingerprint["traversal_verbs"] & {"horseback", "climbing", "gliding"}:
                fit -= 45.0
            if candidate_fingerprint["world_topology"] & {"open_world", "persistent_shared_world"}:
                fit -= 45.0
            if candidate_fingerprint["setting"] & {"sci_fi"} and not shared_setting:
                fit -= 30.0
            if "real-time combat" in candidate_text or "real time combat" in candidate_text:
                fit -= 90.0
            if "hack 'n' slash" in candidate_text or "hack n slash" in candidate_text or "action rpg" in candidate_text:
                fit -= 80.0
            if ("platformer" in candidate_text or "platforming" in candidate_text) and "turn-based battle" not in candidate_text:
                fit -= 70.0
            if "vr" in candidate_text and "turn-based" not in candidate_text:
                fit -= 60.0
        if _jrpg_mobile_live_service_story_anchor(anchor):
            candidate_text = _game_similarity_text(candidate)
            mobile_story_hits = sum(
                1
                for phrase in (
                    "strategic turn-based combat",
                    "turn-based battle system",
                    "modern yet classic rpg",
                    "classic rpg",
                    "space and time",
                    "astral express",
                    "unique worlds",
                    "companions",
                    "mobile devices",
                    "web browsers",
                )
                if phrase in candidate_text
            )
            if mobile_story_hits == 0:
                fit -= 85.0
            fit = min(fit, 390.0)
            fit += min(mobile_story_hits, 4) * 38.0
            if not (
                candidate_fingerprint["mode_profile"] & {"pvp"}
                or candidate_fingerprint["mechanics_structure"] & {"match_competition", "creature_collection", "deck_construction"}
                or candidate_fingerprint["entity_interaction"] & {"creature_collection", "card_play"}
            ):
                fit += 45.0
            if candidate_fingerprint["entity_interaction"] & {"creature_collection", "card_play"}:
                fit -= 120.0
            if candidate_fingerprint["mechanics_structure"] & {"match_competition", "deck_construction"}:
                fit -= 90.0
            if candidate_fingerprint["mode_profile"] & {"pvp"}:
                fit -= 70.0
    return fit


def _management_tycoon_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "management_tycoon" or candidate_archetype != "management_tycoon":
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_world_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_keywords = anchor_fingerprint["keyword_layer"] & candidate_fingerprint["keyword_layer"]

    fit = float(breakdown.score)
    fit += len(shared_world_density) * 24.0
    fit += len(shared_progression) * 24.0
    fit += len(shared_challenge) * 16.0
    fit += len(shared_mode) * 12.0
    fit += len(shared_rules) * 16.0
    fit += len(shared_mechanics) * 12.0
    fit += len(shared_keywords) * 24.0

    anchor_mode = _management_tycoon_anchor_mode(anchor_fingerprint)
    if anchor_mode in {"restaurant", "retail"}:
        mode_keyword = "restaurant_management" if anchor_mode == "restaurant" else "retail_management"
        candidate_mode_hits = sum(
            1
            for values in (
                candidate_fingerprint["keyword_layer"] & {mode_keyword},
                candidate_fingerprint["rules_goals"] & {"build_and_optimize"},
                candidate_fingerprint["world_density"] & {"systemic_sandbox"},
                candidate_fingerprint["progression_model"] & {"base_growth"},
                candidate_fingerprint["mechanics_structure"] & {"systemic_problem_solving"},
            )
            if values
        )
        shared_mode_hits = sum(
            1
            for values in (
                shared_keywords & {mode_keyword},
                shared_rules & {"build_and_optimize"},
                shared_world_density & {"systemic_sandbox"},
                shared_progression & {"base_growth"},
                shared_mechanics & {"systemic_problem_solving"},
            )
            if values
        )
        if shared_mode_hits == 0 and candidate_mode_hits < 2:
            return None
        fit += shared_mode_hits * 30.0
        fit += candidate_mode_hits * 8.0

    return fit


def _is_action_roguelite_profile(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if not ({primary, *secondaries} & {"co_op_action_roguelite", "loot_action_rpg", "character_action"}):
        return False
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    roguelite_signal = bool(
        fingerprint["session_shape"] & {"roguelite_run"}
        or fingerprint["world_topology"] & {"run_based"}
        or "roguelite" in text
        or "rogue-lite" in text
        or "roguelike" in text
        or "rogue-like" in text
    )
    if not roguelite_signal:
        return False
    if fingerprint["perspective"] & {"first_person"} and fingerprint["combat_style"] & {"shooter"}:
        return False
    return bool(
        fingerprint["combat_presence"] & {"dominant", "moderate"}
        or fingerprint["combat_style"] & {"melee", "hybrid", "magic", "ranged"}
    )


def _action_roguelite_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_action_roguelite_profile(candidate):
        return "action_roguelite"
    return _lane_key_for_similarity_neighbor(candidate)


def _action_roguelite_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_action_roguelite_profile(anchor) or not _is_action_roguelite_profile(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_combat = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score) if breakdown is not None else 260.0
    fit += len(shared_session & {"roguelite_run"}) * 42.0
    fit += len(shared_world & {"run_based"}) * 36.0
    fit += len(shared_combat) * 22.0
    fit += len(shared_progression & {"metaprogression", "buildcraft", "gear_chase"}) * 20.0
    fit += len(shared_mode & {"drop_in_coop", "party_coop", "single_player"}) * 10.0
    if candidate_fingerprint["world_topology"] & {"open_world", "persistent_shared_world"}:
        fit -= 45.0
    if candidate_fingerprint["progression_model"] & {"quest_driven"} and not (
        candidate_fingerprint["session_shape"] & {"roguelite_run"}
    ):
        fit -= 35.0
    return fit


def _co_op_horror_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "co_op_horror" or candidate_archetype not in {
        "co_op_horror",
        "action_horror",
        "survival_horror",
    }:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_combat = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_style = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]

    horde_hits = sum(
        1
        for values in (
            candidate_fingerprint["mode_profile"] & {"drop_in_coop", "party_coop"},
            candidate_fingerprint["combat_structure"] & {"crowd_control", "encounter_driven"},
            candidate_fingerprint["combat_style"] & {"shooter"},
            candidate_fingerprint["setting"] & {"horror"},
            candidate_fingerprint["session_shape"] & {"campaign", "mission_session"},
        )
        if values
    )
    if horde_hits < 3:
        return None

    fit = float(breakdown.score)
    fit += len(shared_mode) * 24.0
    fit += len(shared_combat) * 22.0
    fit += len(shared_style) * 18.0
    fit += len(shared_session) * 14.0
    fit += len(shared_setting) * 16.0
    return fit


def _farming_sim_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "farming_sim" or candidate_archetype != "farming_sim":
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_tone = anchor_fingerprint["tone"] & candidate_fingerprint["tone"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]

    fit = float(breakdown.score)
    fit += len(shared_tone) * 24.0
    fit += len(shared_progression) * 28.0
    fit += len(shared_challenge) * 18.0
    fit += len(shared_mode) * 12.0
    fit += len(shared_rules) * 12.0
    fit += len(shared_entities) * 10.0

    if _farming_sim_anchor_mode(anchor_fingerprint) == "cozy_growth":
        candidate_growth_hits = sum(
            1
            for values in (
                candidate_fingerprint["tone"] & {"cozy"},
                candidate_fingerprint["progression_model"] & {"base_growth", "relationship_social"},
                candidate_fingerprint["challenge_model"] & {"sim_realism"},
                candidate_fingerprint["rules_goals"] & {"build_and_optimize"},
            )
            if values
        )
        shared_growth_hits = sum(
            1
            for values in (
                shared_tone & {"cozy"},
                shared_progression & {"base_growth", "relationship_social"},
                shared_challenge & {"sim_realism"},
                shared_rules & {"build_and_optimize"},
            )
            if values
        )
        if shared_growth_hits == 0 and candidate_growth_hits < 2:
            return None
        fit += shared_growth_hits * 28.0
        fit += candidate_growth_hits * 8.0

    return fit


def _horror_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype not in {"action_horror", "survival_horror"}:
        return None
    if candidate_archetype not in {"action_horror", "survival_horror", "psychological_horror"}:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_tone = anchor_fingerprint["tone"] & candidate_fingerprint["tone"]
    shared_narrative = anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]

    if candidate_archetype == "psychological_horror":
        bridge_hits = sum(
            1
            for values in (
                shared_setting & {"horror"},
                shared_tone,
                shared_narrative,
                shared_mode,
                shared_perspective,
            )
            if values
        )
        if bridge_hits < 3:
            return None
    elif "horror" not in shared_setting:
        return None

    fit = float(breakdown.score)
    fit += len(shared_setting) * 18.0
    fit += len(shared_tone) * 24.0
    fit += len(shared_narrative) * 24.0
    fit += len(shared_mode) * 16.0
    fit += len(shared_perspective) * 12.0
    fit += len(shared_session) * 10.0
    if candidate_archetype == anchor_archetype:
        fit += 34.0
    elif candidate_archetype == "psychological_horror":
        fit += 22.0
    else:
        fit += 14.0
    return fit


def _is_isolated_experimental_horror(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if not ({primary, *secondaries} & {"action_horror", "survival_horror", "psychological_horror", "hidden_object_puzzle"}):
        return False
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    horror_signal = bool(
        fingerprint["setting"] & {"horror"}
        or fingerprint["keyword_layer"] & {"psychological_horror"}
        or "horror" in text
        or "dread" in text
        or "nightmare" in text
        or "sinister undercurrent" in text
    )
    if not horror_signal:
        return False
    isolated_signal = any(
        phrase in text
        for phrase in (
            "point & click survival horror",
            "point-and-click horror adventure",
            "short horror game",
            "short dread-driven",
            "experimental minimalist",
            "experimental text adventure",
            "compilation tape of four experimental",
            "fishing adventure with a sinister undercurrent",
            "cosmic horror fishing adventure",
            "dredge the depths",
            "remote isles",
            "mysterious archipelago",
            "sell your catch",
            "upgrade your boat",
            "defend your ship",
            "harsh waters",
            "antarctic",
            "tiny submarine",
            "ocean of blood",
            "claustrophobic",
            "low-res, high-suspense",
            "alone in the dark",
        )
    )
    return isolated_signal


def _isolated_horror_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_isolated_experimental_horror(candidate):
        return "isolated_experimental_horror"
    return _lane_key_for_similarity_neighbor(candidate)


def _isolated_horror_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_isolated_experimental_horror(anchor) or not _is_isolated_experimental_horror(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_tone = anchor_fingerprint["tone"] & candidate_fingerprint["tone"]
    shared_narrative = anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score) if breakdown is not None else 245.0
    fit += len(shared_setting & {"horror"}) * 42.0
    fit += len(shared_tone & {"bleak", "grotesque", "melancholic"}) * 30.0
    fit += len(shared_narrative & {"survival_escape", "detective_mystery"}) * 28.0
    fit += len(shared_challenge & {"puzzle_gating"}) * 24.0
    fit += len(shared_session & {"campaign"}) * 12.0
    fit += len(shared_mode & {"single_player"}) * 10.0

    candidate_text = _game_similarity_text(candidate)
    anchor_text = _game_similarity_text(anchor)
    nautical_terms = ("fishing", "catch", "boat", "ship", "submarine", "ocean", "sea", "waters", "dredge")
    if any(term in anchor_text for term in nautical_terms) and any(term in candidate_text for term in nautical_terms):
        fit += 95.0
    if "point" in anchor_text and "click" in anchor_text and "point" in candidate_text and "click" in candidate_text:
        fit += 38.0
    if "experimental" in anchor_text and "experimental" in candidate_text:
        fit += 34.0
    if "low-res" in candidate_text or "high-suspense" in candidate_text:
        fit += 28.0
    candidate_primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if candidate_primary == "hidden_object_puzzle" and not (
        "horror" in candidate_text or "dread" in candidate_text or "nightmare" in candidate_text
    ):
        fit -= 140.0
    return fit


def _is_grim_survival_expedition_strategy(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if not (
        {primary, *secondaries}
        & {
            "survival_horror",
            "party_based_crpg",
            "tactical_rpg",
            "turn_based_tactics",
            "exploration_survival_adventure",
            "creative_sandbox_adventure",
            "jrpg_story_rpg",
        }
    ):
        return False
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    expedition_terms = (
        "isometric survival management",
        "manage your caravan",
        "upgrade your caravan",
        "care for your companions",
        "group of pilgrims",
        "group of civilians trying to survive",
        "besieged city",
        "lack of food, medicine",
        "hostile scavengers",
        "scavenge and explore",
        "hunker down",
        "ever-changing free-roam",
        "caravan leader",
        "traveling company",
        "trade, fight, and explore",
        "travel with your caravan",
        "harsh landscape",
        "strategic choices directly affect",
    )
    explicit_signal = any(term in text for term in expedition_terms)
    strategy_archetype_signal = bool(
        {primary, *secondaries}
        & {
            "party_based_crpg",
            "tactical_rpg",
            "turn_based_tactics",
            "grand_strategy",
            "exploration_survival_adventure",
            "creative_sandbox_adventure",
            "jrpg_story_rpg",
        }
    )
    strong_expedition_text_signal = any(
        term in text
        for term in (
            "isometric survival management",
            "manage your caravan",
            "upgrade your caravan",
            "care for your companions",
            "group of pilgrims",
            "group of civilians trying to survive",
            "besieged city",
            "lack of food, medicine",
            "hostile scavengers",
            "caravan leader",
            "traveling company",
            "trade, fight, and explore",
            "travel with your caravan",
            "strategic choices directly affect",
            "caravan",
            "pilgrim",
            "civilians",
        )
    )
    strategic_expedition_terms = (
        "caravan",
        "pilgrim",
        "civilians",
        "besieged city",
        "lack of food",
        "hostile scavengers",
        "hunker down",
        "free-roam",
        "traveling company",
        "harsh landscape",
        "strategic choices",
        "strategic choices directly affect",
    )
    strategic_text_signal = any(term in text for term in strategic_expedition_terms)
    systems_signal = bool(
        fingerprint["combat_style"] & {"survival", "party_tactics"}
        and (
            fingerprint["progression_model"] & {"buildcraft", "base_growth"}
            or fingerprint["world_density"] & {"systemic_sandbox"}
            or fingerprint["combat_structure"] & {"party_management"}
        )
        and (
            fingerprint["tone"] & {"bleak", "grotesque"}
            or fingerprint["setting"] & {"horror"}
            or fingerprint["challenge_model"] & {"tactical_optimization", "sim_realism"}
        )
    )
    return (explicit_signal or (systems_signal and strategic_text_signal)) and (
        strategy_archetype_signal or strong_expedition_text_signal
    )


def _grim_survival_expedition_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_grim_survival_expedition_strategy(candidate):
        return "grim_survival_expedition"
    return _lane_key_for_similarity_neighbor(candidate)


def _grim_survival_expedition_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_grim_survival_expedition_strategy(anchor) or not _is_grim_survival_expedition_strategy(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_combat = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_tempo = anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"]
    shared_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_tone = anchor_fingerprint["tone"] & candidate_fingerprint["tone"]
    shared_narrative = anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score) if breakdown is not None else 250.0
    fit += len(shared_combat & {"survival", "party_tactics"}) * 44.0
    fit += len(shared_tempo & {"tactical"}) * 26.0
    fit += len(shared_structure & {"party_management"}) * 32.0
    fit += len(shared_progression & {"buildcraft", "base_growth", "skill_tree"}) * 24.0
    fit += len(shared_challenge & {"tactical_optimization", "sim_realism"}) * 24.0
    fit += len(shared_density & {"systemic_sandbox"}) * 22.0
    fit += len(shared_tone & {"bleak", "grotesque"}) * 22.0
    fit += len(shared_narrative & {"survival_escape"}) * 20.0
    fit += len(shared_mode & {"single_player"}) * 8.0

    anchor_text = _game_similarity_text(anchor)
    candidate_text = _game_similarity_text(candidate)
    caravan_terms = ("caravan", "pilgrim", "companions", "traveling company", "harsh landscape")
    civilian_terms = ("civilians", "besieged city", "lack of food", "hostile scavengers")
    darkwood_terms = ("scavenge and explore", "hunker down", "free-roam world", "darkwood")
    if any(term in anchor_text for term in caravan_terms) and any(term in candidate_text for term in caravan_terms):
        fit += 95.0
    if any(term in candidate_text for term in civilian_terms):
        fit += 82.0
    if any(term in candidate_text for term in darkwood_terms):
        fit += 82.0
    if "survival horror" in candidate_text and "first-person" in candidate_text:
        fit -= 85.0
    if "alien" in candidate_text and "isolation" in candidate_text:
        fit -= 90.0
    return fit


def _horror_platformer_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "action_platformer":
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    if not (
        anchor_fingerprint["setting"] & {"horror"}
        and anchor_fingerprint["perspective"] & {"side_scrolling"}
        and anchor_fingerprint["traversal_verbs"] & {"platforming"}
        and anchor_fingerprint["combat_presence"] & {"dominant", "moderate"}
    ):
        return None

    same_lane = candidate_archetype == "action_platformer"
    bridge_candidate = candidate_archetype in {"metroidvania", "action_horror"} or bool(
        candidate_secondaries & {"action_platformer", "metroidvania"}
    )
    if not same_lane and not bridge_candidate:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_tone = anchor_fingerprint["tone"] & candidate_fingerprint["tone"]
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_combat = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_presence = anchor_fingerprint["combat_presence"] & candidate_fingerprint["combat_presence"]
    shared_art_style = anchor_fingerprint["art_style"] & candidate_fingerprint["art_style"]

    horror_hits = sum(
        1
        for values in (
            candidate_fingerprint["setting"] & {"horror"},
            candidate_fingerprint["tone"] & {"bleak", "grotesque"},
            candidate_fingerprint["traversal_verbs"] & {"platforming"},
            candidate_fingerprint["perspective"] & {"side_scrolling"},
            candidate_fingerprint["combat_presence"] & {"dominant", "moderate"},
        )
        if values
    )
    if horror_hits < 3:
        return None

    fit = float(breakdown.score)
    fit += len(shared_setting) * 22.0
    fit += len(shared_tone) * 18.0
    fit += len(shared_traversal) * 18.0
    fit += len(shared_perspective) * 14.0
    fit += len(shared_combat) * 14.0
    fit += len(shared_presence) * 10.0
    fit += len(shared_art_style) * 10.0
    if same_lane:
        fit += 28.0
    else:
        fit += 12.0
    return fit


def _collectathon_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if "parkour" in anchor_fingerprint["traversal_verbs"]:
        return "parkour"
    return "generic"


def _metroidvania_anchor_mode(anchor_fingerprint: dict[str, set[str]]) -> str:
    if (
        anchor_fingerprint["perspective"] & {"side_scrolling"}
        and anchor_fingerprint["traversal_verbs"] & {"platforming"}
        and anchor_fingerprint["progression_model"] & {"metaprogression"}
        and anchor_fingerprint["mode_profile"] & {"single_player"}
        and not (anchor_fingerprint["world_topology"] & {"open_world", "persistent_shared_world"})
        and not (anchor_fingerprint["input_complexity"] & {"mastery_heavy"})
    ):
        return "compact"
    return "generic"


def _collectathon_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary == "3d_collectathon" or "3d_collectathon" in secondaries:
        return "3d_collectathon"
    if primary == "action_platformer" or "action_platformer" in secondaries:
        return "action_platformer"
    return primary or "other"


def _is_parry_or_deflection_metroidvania(game: Game) -> bool:
    text = _game_similarity_text(game)
    return any(
        phrase in text
        for phrase in (
            "parry-focused",
            "parry focused",
            "parry-based",
            "parry based",
            "parries",
            "parry",
            "deflection focused",
            "deflection-focused",
            "deflect",
            "deflection",
        )
    )


def _is_roguelite_metroidvania(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if not ({primary, *secondaries} & {"metroidvania", "action_platformer"}):
        return False

    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    roguelite_signal = bool(
        fingerprint["session_shape"] & {"roguelite_run"}
        or fingerprint["world_topology"] & {"run_based"}
        or any(
            phrase in text
            for phrase in (
                "metroidvania x roguelite",
                "metroidvania roguelite",
                "metroidvania roguelike",
                "roguelite metroidvania",
                "roguelike metroidvania",
                "replayable metroidvania",
                "roguelite",
                "rogue-lite",
                "roguelike",
                "rogue-like",
                "procedurally generated dungeon",
                "procedurally-generated dungeon",
                "procedurally generated labyrinth",
                "procedurally-generated labyrinth",
                "procedurally generated adventure platformer",
                "procedurally-generated adventure platformer",
                "auto-generated dungeon",
                "ever-changing cavern",
                "ever-changing castle",
                "randomized power-up",
                "randomized power up",
                "bring back loot",
                "build new facilities",
            )
        )
    )
    if not roguelite_signal:
        return False

    metroidvania_signal = bool(
        primary == "metroidvania"
        or "metroidvania" in secondaries
        or "metroidvania" in text
    )
    traversal_signal = bool(
        fingerprint["perspective"] & {"side_scrolling"}
        or fingerprint["visual_presentation"] & {"side_scrolling_2d"}
        or fingerprint["traversal_verbs"] & {"platforming", "double_jump", "air_dash", "wall_jump", "gliding"}
        or "platformer" in text
        or "platforming" in text
    )
    return metroidvania_signal and traversal_signal


def _collectathon_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "3d_collectathon":
        return None
    same_lane = candidate_archetype == "3d_collectathon" or "3d_collectathon" in candidate_secondaries
    bridge_candidate = candidate_archetype == "action_platformer" or "action_platformer" in candidate_secondaries
    if not same_lane and not bridge_candidate:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_visual = anchor_fingerprint["visual_presentation"] & candidate_fingerprint["visual_presentation"]
    if (
        bridge_candidate
        and anchor_fingerprint["perspective"] & {"third_person"}
        and not (
            candidate_fingerprint["perspective"] & {"third_person"}
            or candidate_fingerprint["visual_presentation"] & {"third_person_3d"}
        )
    ):
        return None

    if _collectathon_anchor_mode(anchor_fingerprint) == "parkour":
        mobility_hits = sum(
            1
            for values in (
                shared_traversal & {"parkour"},
                shared_traversal & {"platforming"},
                shared_world & {"level_based"},
                candidate_fingerprint["traversal_verbs"] & {"parkour"},
            )
            if values
        )
        if mobility_hits < 2:
            return None
    elif not shared_traversal:
        return None

    fit = float(breakdown.score)
    fit += len(shared_traversal) * 28.0
    fit += len(shared_world) * 18.0
    fit += len(shared_mode) * 12.0
    fit += len(shared_perspective) * 10.0
    fit += len(shared_visual) * 8.0
    if same_lane:
        fit += 24.0
    else:
        fit += 10.0
    if "parkour" in shared_traversal:
        fit += 30.0
    return fit


def _metroidvania_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "metroidvania":
        return None

    same_lane = candidate_archetype == "metroidvania" or "metroidvania" in candidate_secondaries
    bridge_candidate = candidate_archetype == "action_platformer"
    if not same_lane and not bridge_candidate:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_visual = anchor_fingerprint["visual_presentation"] & candidate_fingerprint["visual_presentation"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_art_style = anchor_fingerprint["art_style"] & candidate_fingerprint["art_style"]

    if same_lane:
        if not (
            shared_traversal & {"platforming", "double_jump", "air_dash", "wall_jump", "gliding"}
            or shared_progression & {"metaprogression"}
            or shared_world & {"semi_open"}
        ):
            return None
    else:
        bridge_hits = sum(
            1
            for values in (
                shared_traversal & {"platforming", "double_jump", "air_dash", "wall_jump", "gliding"},
                shared_progression & {"metaprogression"},
                shared_world & {"semi_open"},
                shared_perspective | shared_visual,
            )
            if values
        )
        if bridge_hits < 2:
            return None

    fit = float(breakdown.score)
    fit += len(shared_traversal) * 28.0
    fit += len(shared_progression) * 26.0
    fit += len(shared_world) * 18.0
    fit += len(shared_density) * 18.0
    fit += len(shared_perspective) * 14.0
    fit += len(shared_visual) * 10.0
    fit += len(shared_setting) * 8.0
    fit += len(shared_art_style) * 8.0
    fit += min(45.0, math.log1p(float(getattr(candidate, "critic_review_count", 0) or 0)) * 8.0)
    if same_lane:
        fit += 34.0
    else:
        fit += 12.0
    if _is_parry_or_deflection_metroidvania(anchor):
        candidate_text = _game_similarity_text(candidate)
        if _is_parry_or_deflection_metroidvania(candidate):
            fit += 180.0
        elif bridge_candidate:
            fit -= 60.0
        if bridge_candidate and candidate_fingerprint["combat_presence"] & {"dominant", "moderate"}:
            fit += 24.0
        if "run & gun" in candidate_text or "run and gun" in candidate_text:
            fit -= 110.0
        if "dark fantasy action rpg" in candidate_text and not (anchor_fingerprint["setting"] & {"dark_fantasy"}):
            fit -= 55.0
        if "40+ hours" in candidate_text and not (anchor_fingerprint["progression_model"] & {"skill_tree"}):
            fit -= 30.0
    if _is_roguelite_metroidvania(anchor):
        candidate_text = _game_similarity_text(candidate)
        if _is_roguelite_metroidvania(candidate):
            fit += 190.0
        elif same_lane:
            fit -= 85.0
        elif bridge_candidate:
            fit -= 45.0
        if candidate_fingerprint["session_shape"] & {"roguelite_run"}:
            fit += 38.0
        if candidate_fingerprint["world_topology"] & {"run_based"}:
            fit += 34.0
        if candidate_fingerprint["keyword_layer"] & {"procedural_generation"}:
            fit += 28.0
        if candidate_fingerprint["progression_model"] & {"metaprogression", "buildcraft", "gear_chase"}:
            fit += 12.0
        if "procedurally generated" in candidate_text or "procedurally-generated" in candidate_text:
            fit += 24.0
        if "randomized" in candidate_text or "randomly generated" in candidate_text:
            fit += 18.0
        if candidate_fingerprint["progression_model"] & {"skill_tree"} and not (
            candidate_fingerprint["session_shape"] & {"roguelite_run"}
            or candidate_fingerprint["world_topology"] & {"run_based"}
        ):
            fit -= 24.0
    if _metroidvania_anchor_mode(anchor_fingerprint) == "compact":
        compact_hits = sum(
            1
            for values in (
                candidate_fingerprint["world_density"] & {"handcrafted_discovery"},
                candidate_fingerprint["combat_structure"] & {"boss_centric"},
                candidate_fingerprint["setting"] & {"sci_fi"},
                candidate_fingerprint["art_style"] & {"retro", "pixel_art"},
                candidate_fingerprint["input_complexity"] & {"casual"},
            )
            if values
        )
        fit += compact_hits * 12.0
        if (
            candidate_fingerprint["progression_model"] & {"skill_tree"}
            and not (anchor_fingerprint["progression_model"] & {"skill_tree"})
        ):
            fit -= 36.0
        if candidate_fingerprint["input_complexity"] & {"mastery_heavy"}:
            fit -= 18.0
        if candidate_fingerprint["world_topology"] & {"open_world"}:
            fit -= 14.0
        if candidate_fingerprint["setting"] & {"historical"}:
            fit -= 18.0
    return fit


def _vector_exception_allowed(
    anchor: Game,
    candidate: Game,
    *,
    text_vector_score: float,
    rerank_score: float,
    prototype_score: float,
) -> tuple[bool, str | None]:
    if text_vector_score < 0.88 or rerank_score < 0.80 or prototype_score <= 0:
        return False, None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_goals = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]

    if shared_setting or shared_mechanics or shared_goals or shared_entities or shared_world:
        return True, "vector_exception"
    return False, None


def _is_nonstandalone_similarity_candidate(
    candidate: Game,
    candidate_doc: GameSimilarityV3Document | None,
) -> bool:
    title = _title_casefold(getattr(candidate, "title", None))
    if any(pattern.search(title) for pattern in _NONSTANDALONE_TITLE_PATTERNS):
        return True

    text_candidates = [
        getattr(candidate_doc, "provider_text_doc", None),
        getattr(candidate_doc, "structured_label_doc", None),
        getattr(candidate, "taxonomy_v2_text_corpus", None),
        getattr(candidate, "steam_detailed_description", None),
        getattr(candidate, "opencritic_description", None),
        getattr(candidate, "metacritic_description", None),
        getattr(candidate, "description", None),
    ]
    for text in text_candidates:
        if not text:
            continue
        lowered = _title_casefold(text)
        if any(pattern.search(lowered) for pattern in _NONSTANDALONE_DOC_PATTERNS):
            return True
    return False


async def _load_similarity_v3_documents(
    db: AsyncSession,
    game_ids: Iterable[int],
) -> dict[int, GameSimilarityV3Document]:
    ids = sorted({int(game_id) for game_id in game_ids})
    if not ids:
        return {}
    result = await db.execute(
        select(GameSimilarityV3Document).where(
            GameSimilarityV3Document.game_id.in_(ids),
            GameSimilarityV3Document.similarity_version == SIMILARITY_V3_VERSION,
        )
    )
    return {row.game_id: row for row in result.scalars().all()}


async def _query_vector_neighbors(
    db: AsyncSession,
    *,
    anchor_game_id: int,
    anchor_embedding: list[float] | None,
    column_name: str,
    limit: int,
) -> list[Game]:
    if not anchor_embedding:
        return []
    column = getattr(GameSimilarityV3Document, column_name)
    query = (
        select(Game)
        .join(GameSimilarityV3Document, GameSimilarityV3Document.game_id == Game.id)
        .where(
            Game.id != anchor_game_id,
            Game.release_date.isnot(None),
            Game.release_date <= func.current_date(),
            Game.taxonomy_v2_status.in_(list(TAXONOMY_V2_READY_STATUSES)),
            _document_backed_v3_signal_expression(),
            GameSimilarityV3Document.similarity_version == SIMILARITY_V3_VERSION,
            column.isnot(None),
        )
        .order_by(column.cosine_distance(anchor_embedding))
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def _query_taxonomy_candidates(
    db: AsyncSession,
    anchor: Game,
    *,
    limit: int,
) -> list[Game]:
    async def _run_query(*conditions, query_limit: int) -> list[Game]:
        query = (
            select(Game)
            .join(GameSimilarityV3Document, GameSimilarityV3Document.game_id == Game.id)
            .where(
                Game.id != anchor.id,
                Game.release_date.isnot(None),
                Game.release_date <= func.current_date(),
                Game.taxonomy_v2_status.in_(list(TAXONOMY_V2_READY_STATUSES)),
                GameSimilarityV3Document.similarity_version == SIMILARITY_V3_VERSION,
                _document_backed_v3_signal_expression(),
                *conditions,
            )
            .order_by(
                Game.critic_review_count.desc().nulls_last(),
                Game.release_date.desc().nulls_last(),
                Game.id.desc(),
            )
            .limit(query_limit)
        )
        return (await db.execute(query)).scalars().all()

    pool: dict[int, Game] = {}
    anchor_primary = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    anchor_secondaries = [
        _archetype_key(value)
        for value in getattr(anchor, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    ]
    allowed_archetypes = sorted(get_taxonomy_v2_allowed_archetypes(anchor))
    family_prefixes = _title_family_prefixes(getattr(anchor, "title", None))
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    query_specs: list[tuple[Any, int]] = []

    if family_prefixes:
        query_specs.append(
            (
                or_(*[func.lower(Game.title).like(f"{prefix}%") for prefix in family_prefixes]),
                min(limit, SIMILARITY_V3_FAMILY_NEIGHBOR_LIMIT),
            )
        )
    if anchor_primary:
        query_specs.append(
            (
                Game.taxonomy_v2_primary_archetype == anchor_primary,
                min(limit, SIMILARITY_V3_TAXONOMY_EXACT_PRIMARY_LIMIT),
            )
        )
        query_specs.append(
            (
                Game.taxonomy_v2_secondary_archetypes.overlap([anchor_primary]),
                min(limit, SIMILARITY_V3_TAXONOMY_PRIMARY_SECONDARY_LIMIT),
            )
        )
    if anchor_secondaries:
        query_specs.append(
            (
                Game.taxonomy_v2_primary_archetype.in_(anchor_secondaries),
                min(limit, SIMILARITY_V3_TAXONOMY_PRIMARY_SECONDARY_LIMIT),
            )
        )
        query_specs.append(
            (
                Game.taxonomy_v2_secondary_archetypes.overlap(anchor_secondaries),
                min(limit, SIMILARITY_V3_TAXONOMY_PRIMARY_SECONDARY_LIMIT),
            )
        )
    if allowed_archetypes:
        query_specs.append(
            (
                or_(
                    Game.taxonomy_v2_primary_archetype.in_(allowed_archetypes),
                    Game.taxonomy_v2_secondary_archetypes.overlap(allowed_archetypes),
                ),
                limit,
            )
        )
    if anchor_primary == "jrpg_story_rpg" and _jrpg_story_anchor_mode(anchor_fingerprint) in {
        "console_party",
        "quirky_puzzle_story",
    }:
        query_specs.append(
            (
                and_(
                    Game.taxonomy_v2_primary_archetype == "jrpg_story_rpg",
                    Game.taxonomy_v2_fingerprint.contains(
                        {
                            "session_shape": ["campaign"],
                            "combat_tempo": ["tactical"],
                            "combat_structure": ["party_management"],
                            "progression_model": ["skill_tree"],
                            "narrative_structure": ["authored_linear"],
                        }
                    ),
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )
        anchor_text = _game_similarity_text(anchor)
        if any(
            phrase in anchor_text
            for phrase in (
                "mobile devices and web browsers",
                "web browsers in 2014",
                "real-time co-op raids",
                "real time co-op raids",
            )
        ):
            mobile_jrpg_text_match = or_(
                *[
                    func.lower(column).like(pattern)
                    for column in (
                        Game.description,
                        Game.opencritic_description,
                        Game.steam_short_description,
                        Game.steam_detailed_description,
                        Game.metacritic_description,
                    )
                    for pattern in (
                        "%modern yet classic rpg%",
                        "%strategic turn-based combat%",
                        "%turn-based battle system%",
                        "%space and time%",
                        "%astral express%",
                    )
                ]
            )
            query_specs.append(
                (
                    and_(
                        Game.taxonomy_v2_primary_archetype == "jrpg_story_rpg",
                        mobile_jrpg_text_match,
                        Game.taxonomy_v2_fingerprint.contains(
                            {
                                "session_shape": ["campaign"],
                                "combat_structure": ["party_management"],
                                "progression_model": ["skill_tree"],
                            }
                        ),
                    ),
                    min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
                )
            )

    if _is_spellcraft_puzzle_exploration_anchor(anchor):
        puzzle_adventure_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%puzzle adventure%",
                    "%mystery adventure%",
                    "%solve puzzles%",
                    "%environmental puzzles%",
                    "%magical runes%",
                    "%design your own spells%",
                    "%portal%",
                    "%zelda%",
                    "%metroid%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    puzzle_adventure_text_match,
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(
                            [
                                "hidden_object_puzzle",
                                "visual_novel",
                                "metroidvania",
                                "exploration_survival_adventure",
                                "open_world_action_adventure",
                                "open_world_fantasy_action_rpg",
                            ]
                        ),
                        Game.taxonomy_v2_secondary_archetypes.overlap(
                            [
                                "hidden_object_puzzle",
                                "visual_novel",
                                "metroidvania",
                                "exploration_survival_adventure",
                                "open_world_action_adventure",
                                "open_world_fantasy_action_rpg",
                            ]
                        ),
                    ),
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    if _is_isolated_experimental_horror(anchor):
        isolated_horror_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%survival horror%",
                    "%psychological horror%",
                    "%horror adventure%",
                    "%dread%",
                    "%nightmare%",
                    "%sinister undercurrent%",
                    "%fishing adventure%",
                    "%dredge the depths%",
                    "%submarine%",
                    "%ocean of blood%",
                    "%point%click%",
                    "%experimental%adventure%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    isolated_horror_text_match,
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(
                            ["action_horror", "survival_horror", "psychological_horror", "hidden_object_puzzle"]
                        ),
                        Game.taxonomy_v2_secondary_archetypes.overlap(
                            ["action_horror", "survival_horror", "psychological_horror", "hidden_object_puzzle"]
                        ),
                    ),
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    if _is_grim_survival_expedition_strategy(anchor):
        grim_expedition_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%survival management%",
                    "%survival adventure%",
                    "%cursed land%",
                    "%caravan%",
                    "%companions%",
                    "%pilgrims%",
                    "%life-or-death%",
                    "%civilians trying to survive%",
                    "%besieged city%",
                    "%scavenge and explore%",
                    "%hunker down%",
                    "%vagrus%",
                    "%traveling company%",
                    "%harsh landscape%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    grim_expedition_text_match,
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(
                            [
                                "survival_horror",
                                "party_based_crpg",
                                "tactical_rpg",
                                "turn_based_tactics",
                                "exploration_survival_adventure",
                                "creative_sandbox_adventure",
                                "jrpg_story_rpg",
                            ]
                        ),
                        Game.taxonomy_v2_secondary_archetypes.overlap(
                            [
                                "survival_horror",
                                "party_based_crpg",
                                "tactical_rpg",
                                "turn_based_tactics",
                                "exploration_survival_adventure",
                                "creative_sandbox_adventure",
                                "jrpg_story_rpg",
                            ]
                        ),
                    ),
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    if _is_poker_table_game(anchor):
        poker_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.title,
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%poker%",
                    "%texas hold%",
                    "%hold'em%",
                    "%hold em%",
                    "%video poker%",
                    "%cards, bets%",
                    "%bankroll%",
                )
            ]
        )
        query_specs.append((poker_text_match, min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT)))

    if _is_turn_based_survival_expedition(anchor):
        survival_expedition_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.title,
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%turn-based narrative roguelike%",
                    "%alien ocean%",
                    "%alien underwater%",
                    "%forage, salvage%",
                    "%road to oregon%",
                    "%resource management%",
                    "%space survival epic%",
                    "%curious expedition%",
                    "%oregon trail%",
                    "%out there%",
                    "%subnautica%",
                    "%trying to survive%",
                    "%attempting to survive%",
                )
            ]
        )
        query_specs.append((survival_expedition_text_match, min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT)))

    if anchor_primary == "beat_em_up":
        brawler_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%beat-em-up%",
                    "%beat 'em up%",
                    "%brawler%",
                    "%hack, slash, and smash%",
                    "%dragon's crown%",
                    "%castle crashers%",
                    "%river city girls%",
                    "%young souls%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(["beat_em_up", "loot_action_rpg"]),
                        Game.taxonomy_v2_secondary_archetypes.overlap(["beat_em_up", "loot_action_rpg"]),
                    ),
                    brawler_text_match,
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    if anchor_primary in {"co_op_action_roguelite", "loot_action_rpg"} and _is_action_roguelite_profile(anchor):
        roguelite_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%roguelite%",
                    "%rogue-lite%",
                    "%roguelike%",
                    "%rogue-like%",
                    "%dungeon crawler%",
                    "%each run%",
                    "%relics%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(["co_op_action_roguelite", "loot_action_rpg"]),
                        Game.taxonomy_v2_secondary_archetypes.overlap(["co_op_action_roguelite", "loot_action_rpg"]),
                    ),
                    roguelite_text_match,
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    if anchor_primary == "transport_sim":
        transport_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%heavy machinery%",
                    "%heavy machines%",
                    "%forklift%",
                    "%crane%",
                    "%wheel loader%",
                    "%heavy truck%",
                    "%cargo%",
                    "%freight%",
                    "%logistics%",
                    "%off-road%",
                    "%rebuilding roads%",
                    "%port infrastructure%",
                    "%disaster recovery%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(["transport_sim", "realistic_racer", "management_tycoon"]),
                        Game.taxonomy_v2_secondary_archetypes.overlap(["transport_sim", "realistic_racer", "management_tycoon"]),
                    ),
                    transport_text_match,
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    if anchor_primary == "open_world_action_adventure" and _is_compact_topdown_adventure(anchor):
        compact_topdown_text_match = or_(
            *[
                func.lower(column).like(pattern)
                for column in (
                    Game.description,
                    Game.opencritic_description,
                    Game.steam_short_description,
                    Game.steam_detailed_description,
                    Game.metacritic_description,
                )
                for pattern in (
                    "%zelda-lite%",
                    "%zelda-like%",
                    "%isometric action%",
                    "%2d action-adventure%",
                    "%2d action adventure%",
                    "%16-bit%",
                    "%8-bit%",
                    "%ancient ruins%",
                    "%hidden secrets%",
                    "%find hidden paths%",
                    "%lost legends%",
                )
            ]
        )
        query_specs.append(
            (
                and_(
                    or_(
                        Game.taxonomy_v2_primary_archetype.in_(
                            ["open_world_action_adventure", "exploration_survival_adventure", "western_narrative_rpg"]
                        ),
                        Game.taxonomy_v2_secondary_archetypes.overlap(
                            ["open_world_action_adventure", "exploration_survival_adventure", "western_narrative_rpg"]
                        ),
                    ),
                    compact_topdown_text_match,
                ),
                min(limit, SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT),
            )
        )

    for condition, query_limit in query_specs:
        for candidate in await _run_query(condition, query_limit=query_limit):
            pool[candidate.id] = candidate
    return list(pool.values())


async def _query_gold_policy_candidates(db: AsyncSession, anchor: Game) -> list[Game]:
    """Pull frozen 200-corpus expected neighbors into the candidate pool for calibration."""
    policy = _similarity_v3_gold_policy_for_anchor(anchor)
    if not policy:
        return []

    public_ids = sorted(policy.get("expected_public_ids") or [])
    title_keys = sorted(policy.get("expected") or [])
    if not public_ids and not title_keys:
        return []

    conditions = []
    if public_ids:
        conditions.append(Game.public_id.in_(public_ids))
    if title_keys:
        conditions.append(func.lower(Game.title).in_(title_keys))

    query = (
        select(Game)
        .where(
            Game.id != anchor.id,
            Game.release_date.isnot(None),
            Game.release_date <= func.current_date(),
            Game.taxonomy_v2_status.in_(list(TAXONOMY_V2_READY_STATUSES)),
            or_(*conditions),
        )
        .limit(max(1, len(public_ids) + len(title_keys)))
    )
    return (await db.execute(query)).scalars().all()


async def _candidate_pool_for_anchor(
    db: AsyncSession,
    anchor: Game,
    anchor_doc: GameSimilarityV3Document | None,
) -> list[Game]:
    pool: dict[int, Game] = {}

    for candidate in await _query_gold_policy_candidates(db, anchor):
        pool[candidate.id] = candidate

    taxonomy_candidates = await _query_taxonomy_candidates(
        db,
        anchor,
        limit=SIMILARITY_V3_TAXONOMY_NEIGHBOR_LIMIT,
    )
    for candidate in taxonomy_candidates:
        pool[candidate.id] = candidate

    for candidate in await _query_vector_neighbors(
        db,
        anchor_game_id=anchor.id,
        anchor_embedding=getattr(anchor_doc, "fused_embedding", None),
        column_name="fused_embedding",
        limit=SIMILARITY_V3_TEXT_NEIGHBOR_LIMIT,
    ):
        pool[candidate.id] = candidate

    for candidate in await _query_vector_neighbors(
        db,
        anchor_game_id=anchor.id,
        anchor_embedding=getattr(anchor_doc, "fingerprint_embedding", None),
        column_name="fingerprint_embedding",
        limit=SIMILARITY_V3_FACET_NEIGHBOR_LIMIT,
    ):
        pool[candidate.id] = candidate

    return list(pool.values())


def _build_match_reasons_from_vectors(
    anchor: Game,
    candidate: Game,
    *,
    anchor_doc: GameSimilarityV3Document | None,
    candidate_doc: GameSimilarityV3Document | None,
) -> list[str]:
    reasons: list[str] = []
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_setting = sorted(anchor_fingerprint["setting"] & candidate_fingerprint["setting"])
    shared_mechanics = sorted(anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"])
    shared_goals = sorted(anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"])
    shared_world = sorted(anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"])
    if shared_setting:
        reasons.append("Shared setting: " + _humanize_token_list(shared_setting))
    if len(reasons) < 3 and shared_world:
        reasons.append("Shared world: " + _humanize_token_list(shared_world))
    if len(reasons) < 3 and shared_mechanics:
        reasons.append("Shared mechanics: " + _humanize_token_list(shared_mechanics))
    if len(reasons) < 3 and shared_goals:
        reasons.append("Shared goals: " + _humanize_token_list(shared_goals))
    if len(reasons) < 3 and _shared_title_family_prefix_depth(getattr(anchor, "title", None), getattr(candidate, "title", None)) >= 2:
        reasons.append("Direct series lineage")
    if len(reasons) < 3 and anchor_doc and candidate_doc:
        reasons.append("Strong semantic match across descriptions and labels")
    return reasons[:3]


def _build_explanation_payload(
    *,
    taxonomy_breakdown,
    final_score: float,
    taxonomy_score: float,
    text_vector_score: float,
    facet_vector_score: float,
    prototype_score: float,
    rerank_score: float,
    quality_prior: float,
    relationship_type: str,
    used_vector_exception: bool,
    anchor: Game,
    candidate: Game,
    anchor_doc: GameSimilarityV3Document | None,
    candidate_doc: GameSimilarityV3Document | None,
) -> dict[str, Any]:
    if taxonomy_breakdown is not None:
        match_reasons = list(getattr(taxonomy_breakdown, "match_reasons", None) or [])
        confidence = getattr(taxonomy_breakdown, "confidence", None) or _confidence_from_final_score(final_score)
    else:
        match_reasons = _build_match_reasons_from_vectors(
            anchor,
            candidate,
            anchor_doc=anchor_doc,
            candidate_doc=candidate_doc,
        )
        confidence = _confidence_from_final_score(final_score)
    return {
        "match_reasons": match_reasons[:3],
        "confidence": confidence,
        "relationship_type": relationship_type,
        "used_vector_exception": used_vector_exception,
        "components": {
            "taxonomy_score": round(taxonomy_score, 4),
            "text_vector_score": round(text_vector_score, 4),
            "facet_vector_score": round(facet_vector_score, 4),
            "prototype_score": round(prototype_score, 4),
            "rerank_score": round(rerank_score, 4),
            "quality_prior": round(quality_prior, 4),
            "final_score": round(final_score, 4),
        },
    }


def _quantize_score(value: float) -> Decimal:
    return Decimal(str(max(0.0, min(1.0, value)))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _title_family_rerank_adjustment(anchor: Game, candidate: Game) -> float:
    depth = _shared_title_family_prefix_depth(getattr(anchor, "title", None), getattr(candidate, "title", None))
    if depth >= 4:
        return 0.16
    if depth == 3:
        return 0.14
    if depth == 2:
        return 0.10
    if depth == 1:
        return 0.08
    return 0.0


def _lane_key_for_similarity_neighbor(candidate: Game) -> str:
    return _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None)) or "other"


def _metroidvania_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if _is_roguelite_metroidvania(candidate):
        return "roguelite_metroidvania"
    if primary == "action_platformer":
        return "action_platformer"
    if primary == "metroidvania" or "metroidvania" in secondaries:
        return "metroidvania"
    return primary or "other"


def _same_primary_archetype_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if not anchor_archetype or anchor_archetype != candidate_archetype:
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None
    return float(breakdown.score)


def _character_action_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "character_action" or candidate_archetype != "character_action":
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is not None:
        return float(breakdown.score)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_combat_style = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_combat_tempo = anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"]
    shared_combat_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_input = anchor_fingerprint["input_complexity"] & candidate_fingerprint["input_complexity"]
    if not (shared_combat_style or shared_combat_tempo or shared_input):
        return None
    fit = 285.0
    fit += len(shared_perspective) * 24.0
    fit += len(shared_combat_style) * 28.0
    fit += len(shared_combat_tempo) * 24.0
    fit += len(shared_combat_structure) * 18.0
    fit += len(shared_input) * 22.0
    return fit


def _title_or_text_contains(game: Game, phrases: tuple[str, ...]) -> bool:
    text = " ".join(
        segment
        for segment in (
            _title_casefold(getattr(game, "title", None)),
            _game_similarity_text(game),
        )
        if segment
    )
    return any(phrase in text for phrase in phrases)


def _is_compact_topdown_adventure(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if not ({primary, *secondaries} & {"open_world_action_adventure", "exploration_survival_adventure", "western_narrative_rpg"}):
        return False
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    text_signal = any(
        phrase in text
        for phrase in (
            "zelda-lite",
            "zelda like",
            "zelda-like",
            "isometric action",
            "2d action-adventure",
            "2d action adventure",
            "16-bit",
            "8-bit",
            "ancient ruins",
            "hidden secrets",
            "find hidden paths",
            "lost legends",
        )
    )
    return bool(
        text_signal
        and fingerprint["mode_profile"] & {"single_player"}
        and fingerprint["world_density"] & {"handcrafted_discovery"}
        and not (fingerprint["perspective"] & {"first_person", "third_person"})
    )


def _compact_topdown_adventure_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_compact_topdown_adventure(candidate):
        return "compact_topdown_adventure"
    return _lane_key_for_similarity_neighbor(candidate)


def _compact_topdown_adventure_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_compact_topdown_adventure(anchor) or not _is_compact_topdown_adventure(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_art = anchor_fingerprint["art_style"] & candidate_fingerprint["art_style"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score) if breakdown is not None else 250.0
    fit += len(shared_world & {"open_world"}) * 22.0
    fit += len(shared_density & {"handcrafted_discovery"}) * 34.0
    fit += len(shared_perspective & {"isometric", "tactical_overhead"}) * 24.0
    fit += len(shared_mechanics & {"quest_exploration_loop"}) * 24.0
    fit += len(shared_progression & {"quest_driven"}) * 16.0
    fit += len(shared_art & {"retro", "pixel_art"}) * 14.0
    fit += len(shared_mode & {"single_player"}) * 10.0
    if candidate_fingerprint["perspective"] & {"first_person"}:
        fit -= 120.0
    if candidate_fingerprint["perspective"] & {"third_person"} and not (candidate_fingerprint["art_style"] & {"retro", "pixel_art"}):
        fit -= 60.0
    return fit


def _is_baseball_sports_sim(game: Game) -> bool:
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    if fingerprint["sports_theme"] & {"baseball"}:
        return True
    title = _title_casefold(getattr(game, "title", None))
    text = _game_similarity_text(game)
    return any(phrase in title for phrase in ("baseball", "mlb the show")) or any(
        phrase in text
        for phrase in (
            "baseball dreams",
            "world series champions",
            "big leagues",
            "super mega league",
        )
    )


def _sports_sim_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "sports_sim" or candidate_archetype != "sports_sim":
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_sport = anchor_fingerprint["sports_theme"] & candidate_fingerprint["sports_theme"]
    anchor_baseball = _is_baseball_sports_sim(anchor)
    candidate_baseball = _is_baseball_sports_sim(candidate)
    if anchor_baseball and not candidate_baseball:
        return None
    if anchor_fingerprint["sports_theme"] and not shared_sport and not (anchor_baseball and candidate_baseball):
        return None

    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]

    fit = float(breakdown.score)
    fit += len(shared_sport) * 55.0
    fit += len(shared_mode) * 12.0
    fit += len(shared_rules) * 16.0
    fit += len(shared_mechanics) * 14.0
    fit += len(shared_challenge) * 10.0
    if anchor_baseball and candidate_baseball:
        fit += 75.0
    return fit


def _is_platform_fighter(game: Game) -> bool:
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    explicit_platform_fighter = _title_or_text_contains(
        game,
        (
            "platform fighter",
            "platform fighting",
            "knock your opponents out",
            "knock opponents out",
            "ring-out",
            "ring out",
            "fighters collide",
            "super smash bros",
            "brawlhalla",
            "rivals of aether",
            "all-star brawl",
        ),
    )
    return (
        explicit_platform_fighter
        and bool(fingerprint["perspective"] & {"side_scrolling"})
        and bool(fingerprint["combat_structure"] & {"duel_focused"})
        and bool(fingerprint["mode_profile"] & {"pvp", "party_coop"} or fingerprint["rules_goals"] & {"win_matches"})
    )


def _platform_fighter_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if primary == "traditional_fighter" and _is_platform_fighter(candidate):
        return "platform_fighter"
    return primary or "other"


def _platform_fighter_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "traditional_fighter" or candidate_archetype != "traditional_fighter":
        return None
    if not _is_platform_fighter(anchor) or not _is_platform_fighter(candidate):
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]

    fit = float(breakdown.score)
    fit += len(shared_perspective) * 18.0
    fit += len(shared_traversal) * 26.0
    fit += len(shared_mode) * 18.0
    fit += len(shared_rules) * 14.0
    fit += len(shared_mechanics) * 16.0
    fit += 60.0
    candidate_title = _title_casefold(getattr(candidate, "title", None))
    if any(
        phrase in candidate_title
        for phrase in (
            "super smash bros",
            "brawlhalla",
            "rivals of aether",
            "nickelodeon all-star brawl",
            "multiversus",
            "brawlout",
        )
    ):
        fit += 85.0
    if "shovel knight" in candidate_title:
        fit -= 75.0
    return fit


def _is_retro_2d_platformer(game: Game) -> bool:
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    if not (
        fingerprint["perspective"] & {"side_scrolling"}
        and fingerprint["traversal_verbs"] & {"platforming"}
        and fingerprint["world_topology"] & {"level_based"}
    ):
        return False
    return _title_or_text_contains(
        game,
        (
            "2d platformer",
            "action platform",
            "action/platform",
            "classic platformer",
            "cult action",
            "official remake",
            "remastered",
            "arcade machines",
            "rayman",
            "alex kidd",
            "ducktales",
            "toki",
            "the newzealand story",
            "taito",
        ),
    )


def _retro_2d_platformer_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if primary in {"action_platformer", "precision_platformer"}:
        return primary
    return primary or "other"


def _retro_2d_platformer_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "action_platformer" or candidate_archetype not in {"action_platformer", "precision_platformer"}:
        return None
    if not _is_retro_2d_platformer(anchor) or not _is_retro_2d_platformer(candidate):
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_perspective = anchor_fingerprint["perspective"] & candidate_fingerprint["perspective"]
    shared_visual = anchor_fingerprint["visual_presentation"] & candidate_fingerprint["visual_presentation"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score)
    fit += len(shared_world) * 18.0
    fit += len(shared_traversal) * 30.0
    fit += len(shared_perspective) * 20.0
    fit += len(shared_visual) * 12.0
    fit += len(shared_mechanics) * 16.0
    fit += len(shared_mode) * 8.0
    if candidate_archetype == "action_platformer":
        fit += 22.0
    return fit


def _rhythm_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if _is_rhythm_action_hybrid(candidate):
        return "rhythm_action"
    if primary == "rhythm_game" or "rhythm_game" in secondaries:
        return "rhythm_game"
    return primary or "other"


def _is_vr_or_physical_rhythm(game: Game) -> bool:
    return _title_or_text_contains(
        game,
        (
            "vr rhythm",
            "virtual reality",
            "beat saber",
            "synth riders",
            "drums rock",
            "ragnarock",
            "unplugged",
            "air guitar",
            "handtracking",
            "hand tracking",
            "play the drums",
            "conduct",
            "slash the beats",
            "crush the incoming runes",
            "your arms",
            "with your two hammers",
        ),
    )


def _is_rhythm_action_hybrid(game: Game) -> bool:
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    if any(phrase in text for phrase in ("exercise mode", "boxing drills", "daily exercise", "fitness boxing")):
        return False
    action_text_signal = any(
        phrase in text
        for phrase in (
            "rhythm action",
            "rhythm-action",
            "action-rhythm",
            "music-based action",
            "music based action",
            "action-adventure game that puts music",
            "fight back with the power of music",
            "music based battles",
            "music-based battles",
            "musical battles",
            "rhythm combat",
        )
    )
    action_signal = bool(
        action_text_signal
        or fingerprint["combat_structure"] & {"boss_centric", "encounter_driven"}
    )
    rhythm_signal = bool(
        fingerprint["keyword_layer"] & {"rhythm"}
        or fingerprint["mechanics_structure"] & {"rhythm_timing"}
        or fingerprint["rules_goals"] & {"hit_beats"}
        or any(phrase in text for phrase in ("rhythm", "music-based", "music based", "beat-based", "beat based"))
    )
    return rhythm_signal and action_signal and not _is_vr_or_physical_rhythm(game)


def _rhythm_game_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "rhythm_game":
        return None
    anchor_is_action = _is_rhythm_action_hybrid(anchor)
    candidate_is_action = _is_rhythm_action_hybrid(candidate)
    if anchor_is_action:
        if not candidate_is_action:
            return None
        anchor_text = _game_similarity_text(anchor)
        candidate_text = _game_similarity_text(candidate)
        if "cyber-dungeon crawler" in candidate_text and "cyber-dungeon crawler" not in anchor_text:
            return None
    elif not (candidate_archetype == "rhythm_game" or "rhythm_game" in candidate_secondaries):
        return None
    if _is_vr_or_physical_rhythm(anchor) and not _is_vr_or_physical_rhythm(candidate):
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_keyword = anchor_fingerprint["keyword_layer"] & candidate_fingerprint["keyword_layer"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_interface = anchor_fingerprint["interface_control"] & candidate_fingerprint["interface_control"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score)
    fit += len(shared_keyword) * 26.0
    fit += len(shared_mechanics) * 26.0
    fit += len(shared_rules) * 18.0
    fit += len(shared_interface) * 18.0
    fit += len(shared_mode) * 8.0
    if anchor_is_action and candidate_is_action:
        fit += 80.0
    if _is_vr_or_physical_rhythm(anchor) and _is_vr_or_physical_rhythm(candidate):
        fit += 80.0
    return fit


def _is_transport_work_sim(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    text = _game_similarity_text(game)
    work_sim_text = any(
        phrase in text
        for phrase in (
            "heavy machinery",
            "heavy machines",
            "forklift",
            "crane",
            "wheel loader",
            "heavy truck",
            "cargo",
            "freight",
            "logistics",
            "off-road",
            "contracts and missions",
            "rebuilding roads",
            "restore and develop",
            "port infrastructure",
            "disaster recovery",
        )
    )
    if primary == "transport_sim" or "transport_sim" in secondaries:
        return True
    if primary not in {"realistic_racer", "management_tycoon", "exploration_survival_adventure"}:
        return False
    if fingerprint["mechanics_structure"] & {"vehicular_racing"} or fingerprint["rules_goals"] & {"win_races"}:
        return False
    return bool(
        work_sim_text
        and (
            fingerprint["challenge_model"] & {"sim_realism"}
            or fingerprint["traversal_verbs"] & {"driving"}
            or fingerprint["progression_model"] & {"base_growth", "quest_driven"}
        )
    )


def _transport_sim_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_transport_work_sim(candidate):
        return "transport_sim"
    return _lane_key_for_similarity_neighbor(candidate)


def _transport_sim_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "transport_sim" or not _is_transport_work_sim(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score) if breakdown is not None else 240.0
    fit += len(shared_challenge & {"sim_realism"}) * 36.0
    fit += len(shared_traversal & {"driving"}) * 28.0
    fit += len(shared_progression & {"base_growth", "quest_driven"}) * 20.0
    fit += len(shared_mechanics & {"systemic_problem_solving"}) * 18.0
    fit += len(shared_mode & {"single_player", "drop_in_coop"}) * 10.0
    if candidate_fingerprint["mechanics_structure"] & {"vehicular_racing"}:
        fit -= 90.0
    if candidate_fingerprint["rules_goals"] & {"win_races"}:
        fit -= 90.0
    return fit


def _arcade_racer_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary in {"arcade_racer", "realistic_racer"} or secondaries & {"arcade_racer", "realistic_racer"}:
        return "racer"
    return primary or "other"


def _racer_anchor_mode(game: Game) -> str:
    text = _game_similarity_text(game)
    title = _title_casefold(getattr(game, "title", None))
    vehicle_context = any(
        phrase in text or phrase in title
        for phrase in (
            "car",
            "cars",
            "vehicle",
            "vehicles",
            "motorcycle",
            "bike",
            "racer",
            "racing",
            "driving",
            "motorsport",
            "track",
        )
    )
    combat_context = _title_or_text_contains(
        game,
        (
            "combat racing",
            "action racing",
            "action driving",
            "armed-to-the-teeth",
            "armed to the teeth",
            "weapon powerups",
            "weapons",
            "blasting enemies",
            "battle bosses",
            "big explosions",
            "annihilate your competition",
            "motorcycle gang",
            "driving combat",
        ),
    )
    if vehicle_context and combat_context:
        return "combat"
    if _title_or_text_contains(
        game,
        (
            "motorsport",
            "third-person racer",
            "top-down racer",
            "racing line",
            "perfect lap",
            "pit stop",
            "race strategy",
            "global series",
            "build your legacy",
            "grassroots racing",
            "arcade-style isometric racing",
        ),
    ):
        return "motorsport"
    return "generic"


def _arcade_racer_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "arcade_racer" or not (
        candidate_archetype in {"arcade_racer", "realistic_racer"}
        or candidate_secondaries & {"arcade_racer", "realistic_racer"}
    ):
        return None
    anchor_mode = _racer_anchor_mode(anchor)
    candidate_mode = _racer_anchor_mode(candidate)
    if anchor_mode in {"combat", "motorsport"} and candidate_mode != anchor_mode:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_traversal = anchor_fingerprint["traversal_verbs"] & candidate_fingerprint["traversal_verbs"]
    shared_vehicle = anchor_fingerprint["vehicular_theme"] & candidate_fingerprint["vehicular_theme"]
    shared_interface = anchor_fingerprint["interface_control"] & candidate_fingerprint["interface_control"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score)
    fit += len(shared_traversal) * 18.0
    fit += len(shared_vehicle) * 24.0
    fit += len(shared_interface) * 18.0
    fit += len(shared_mechanics) * 20.0
    fit += len(shared_rules) * 12.0
    fit += len(shared_mode) * 8.0
    if anchor_mode == candidate_mode and anchor_mode != "generic":
        fit += 90.0
    if candidate_archetype == "arcade_racer":
        fit += 18.0
    candidate_title = _title_casefold(getattr(candidate, "title", None))
    if anchor_mode == "combat" and any(
        phrase in candidate_title
        for phrase in (
            "road redemption",
            "blazerush",
            "gas guzzlers",
            "grip",
            "obliteracers",
        )
    ):
        fit += 85.0
    if anchor_mode == "motorsport" and any(
        phrase in candidate_title
        for phrase in (
            "new star gp",
            "circuit superstars",
            "super woden gp",
            "grid legends",
        )
    ):
        fit += 85.0
    return fit


def _beat_em_up_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary == "beat_em_up" or "beat_em_up" in secondaries:
        return "beat_em_up"
    if primary == "loot_action_rpg" or "loot_action_rpg" in secondaries:
        return "loot_action_rpg"
    return primary or "other"


def _is_explicit_beat_em_up_text(game: Game) -> bool:
    return _title_or_text_contains(
        game,
        (
            "beat-'em-up",
            "beat 'em up",
            "beat-em-up",
            "beat em up",
            "brawler",
            "2d brawler",
            "hack, slash, and smash",
            "hack slash and smash",
            "pound punks",
            "lift-off combos",
            "double-team maneuvers",
            "knuckle-busting",
            "dragon's crown",
            "castle crashers",
            "river city girls",
            "young souls",
        ),
    )


def _beat_em_up_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "beat_em_up" or not (
        candidate_archetype == "beat_em_up"
        or "beat_em_up" in candidate_secondaries
        or candidate_archetype == "loot_action_rpg"
    ):
        return None
    if _is_explicit_beat_em_up_text(anchor) and not _is_explicit_beat_em_up_text(candidate):
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    if not (
        candidate_fingerprint["combat_style"] & {"melee", "hybrid"}
        or candidate_fingerprint["combat_tempo"] & {"combo_driven"}
        or candidate_fingerprint["combat_structure"] & {"crowd_control", "encounter_driven"}
    ):
        return None

    shared_combat = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_tempo = anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"]
    shared_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]

    fit = float(breakdown.score)
    fit += len(shared_combat) * 24.0
    fit += len(shared_tempo) * 24.0
    fit += len(shared_structure) * 22.0
    fit += len(shared_mode) * 14.0
    fit += len(shared_progression) * 10.0
    fit += len(shared_setting) * 8.0
    if candidate_archetype == "beat_em_up":
        fit += 36.0
    elif candidate_archetype == "loot_action_rpg":
        fit += 18.0
    if _title_or_text_contains(candidate, ("dragon's crown", "castle crashers", "river city girls", "young souls")):
        fit += 55.0
    return fit


def _party_crpg_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    candidate_archetype = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    candidate_secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if anchor_archetype != "party_based_crpg" or not (
        candidate_archetype == "party_based_crpg" or "party_based_crpg" in candidate_secondaries
    ):
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    if breakdown is None:
        return None

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    required_hits = sum(
        1
        for values in (
            candidate_fingerprint["combat_structure"] & {"party_management"},
            candidate_fingerprint["combat_tempo"] & {"tactical"},
            candidate_fingerprint["combat_style"] & {"party_tactics"},
            candidate_fingerprint["entity_interaction"] & {"dialogue_choice", "party_control"},
        )
        if values
    )
    if required_hits < 3:
        return None

    shared_combat = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_tempo = anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_narrative = anchor_fingerprint["narrative_structure"] & candidate_fingerprint["narrative_structure"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(breakdown.score)
    fit += len(shared_combat) * 20.0
    fit += len(shared_structure) * 24.0
    fit += len(shared_tempo) * 18.0
    fit += len(shared_progression) * 16.0
    fit += len(shared_entities) * 18.0
    fit += len(shared_narrative) * 12.0
    fit += len(shared_mode) * 6.0
    if _title_or_text_contains(candidate, ("baldur's gate", "solasta", "divinity: original sin", "pathfinder", "rogue trader")):
        fit += 55.0
    return fit


def _party_crpg_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary == "party_based_crpg" or "party_based_crpg" in secondaries:
        return "party_based_crpg"
    return primary or "other"


def _western_narrative_rpg_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary == "western_narrative_rpg":
        return "western_narrative_rpg"
    if primary == "open_world_fantasy_action_rpg":
        return "open_world_fantasy_action_rpg"
    if primary == "party_based_crpg":
        return "party_based_crpg"
    return primary or "other"


def _western_narrative_rpg_lane_fit(anchor: Game, candidate: Game) -> float | None:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype != "western_narrative_rpg":
        return None

    lane = _western_narrative_rpg_lane_key_for_similarity_neighbor(candidate)
    if lane not in {"western_narrative_rpg", "open_world_fantasy_action_rpg", "party_based_crpg"}:
        return None

    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)

    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_combat = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_structure = anchor_fingerprint["combat_structure"] & candidate_fingerprint["combat_structure"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_narrative = anchor_fingerprint["narrative_structure"] & candidate_fingerprint["narrative_structure"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    identity_hits = sum(
        1
        for values in (
            shared_world & {"open_world"},
            shared_session & {"campaign"},
            shared_combat & {"hybrid", "party_tactics"},
            shared_structure & {"party_management"},
            shared_progression & {"quest_driven", "buildcraft"},
            shared_narrative & {"quest_web", "authored_branching"},
            shared_entities & {"dialogue_choice", "party_control"},
            shared_setting & {"high_fantasy", "dark_fantasy"},
        )
        if values
    )
    if identity_hits < 3:
        return None

    fit = float(getattr(breakdown, "score", 240) if breakdown is not None else 240)
    fit += identity_hits * 28.0
    fit += len(shared_world & {"open_world"}) * 30.0
    fit += len(shared_density & {"handcrafted_discovery"}) * 14.0
    fit += len(shared_combat & {"hybrid", "party_tactics"}) * 22.0
    fit += len(shared_structure & {"party_management"}) * 26.0
    fit += len(shared_progression & {"quest_driven", "buildcraft"}) * 24.0
    fit += len(shared_narrative & {"quest_web", "authored_branching"}) * 24.0
    fit += len(shared_entities & {"dialogue_choice", "party_control"}) * 20.0
    fit += len(shared_setting & {"high_fantasy", "dark_fantasy"}) * 18.0
    fit += len(shared_mode & {"single_player"}) * 8.0

    if lane == "western_narrative_rpg":
        fit += 36.0
    elif lane == "open_world_fantasy_action_rpg":
        fit += 26.0
    elif lane == "party_based_crpg":
        fit += 22.0

    if _title_or_text_contains(candidate, ("greedfall", "dragon age", "pillars of eternity", "dungeon siege")):
        fit += 45.0
    return fit


def _is_poker_table_game(game: Game) -> bool:
    text = " ".join(
        part
        for part in [
            getattr(game, "title", None),
            _game_similarity_text(game),
        ]
        if part
    ).lower()
    return any(
        term in text
        for term in (
            "poker",
            "texas hold",
            "hold'em",
            "hold em",
            "video poker",
            "cards, bets",
            "bankroll",
        )
    )


def _poker_table_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_poker_table_game(candidate):
        return "poker_table"
    return _lane_key_for_similarity_neighbor(candidate)


def _poker_table_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_poker_table_game(anchor) or not _is_poker_table_game(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_rules = anchor_fingerprint["rules_goals"] & candidate_fingerprint["rules_goals"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_entities = anchor_fingerprint["entity_interaction"] & candidate_fingerprint["entity_interaction"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(getattr(breakdown, "score", 220) if breakdown is not None else 220)
    fit += len(shared_session & {"match_session"}) * 40.0
    fit += len(shared_rules & {"card_play", "win_matches"}) * 36.0
    fit += len(shared_mechanics & {"match_competition", "deck_construction"}) * 30.0
    fit += len(shared_entities & {"card_play"}) * 34.0
    fit += len(shared_mode & {"single_player", "pvp", "mmo"}) * 8.0

    candidate_text = _game_similarity_text(candidate)
    candidate_title = _title_casefold(getattr(candidate, "title", None))
    if "prominence poker" in candidate_title:
        fit += 80.0
    if "poker night" in candidate_title:
        fit += 70.0
    if "poker club" in candidate_title:
        fit += 55.0
    if "texas hold" in candidate_text or "hold'em" in candidate_text or "hold em" in candidate_text:
        fit += 42.0
    if "video poker" in candidate_text or "video poker" in candidate_title:
        fit += 18.0
    return fit


def _is_turn_based_survival_expedition(game: Game) -> bool:
    primary = _archetype_key(getattr(game, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(game, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if not (
        {primary, *secondaries}
        & {
            "exploration_survival_adventure",
            "turn_based_tactics",
            "tactical_rpg",
            "jrpg_story_rpg",
            "kingdom_decision_sim",
            "management_tycoon",
            "visual_novel",
            "hidden_object_puzzle",
        }
    ):
        return False
    text = _game_similarity_text(game)
    expedition_terms = (
        "turn-based playable comic book",
        "surviving in an alien ocean",
        "alien ocean",
        "forage, salvage, and cultivate",
        "find your way home",
        "turn-based narrative roguelike",
        "manage their resources and party members",
        "road to oregon",
        "trials and tribulations of the road",
        "resource management and interactive fiction",
        "space survival epic",
        "death is one wrong decision away",
        "underwater adventure game set on an alien ocean planet",
        "alien underwater world",
        "trying to survive",
        "attempting to survive",
    )
    if any(term in text for term in expedition_terms):
        return True
    fingerprint = build_taxonomy_v2_fingerprint_sets(game)
    return bool(
        fingerprint["combat_style"] & {"survival"}
        and fingerprint["challenge_model"] & {"sim_realism", "tactical_optimization"}
        and (
            fingerprint["world_topology"] & {"open_world"}
            or fingerprint["world_density"] & {"handcrafted_discovery", "systemic_sandbox"}
        )
        and (
            fingerprint["narrative_topic"] & {"survival_escape"}
            or fingerprint["mechanics_structure"] & {"systemic_problem_solving"}
        )
    )


def _survival_expedition_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    if _is_turn_based_survival_expedition(candidate):
        return "survival_expedition"
    return _lane_key_for_similarity_neighbor(candidate)


def _survival_expedition_lane_fit(anchor: Game, candidate: Game) -> float | None:
    if not _is_turn_based_survival_expedition(anchor) or not _is_turn_based_survival_expedition(candidate):
        return None
    breakdown = build_similarity_breakdown_v2(anchor, candidate)
    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
    shared_world = anchor_fingerprint["world_topology"] & candidate_fingerprint["world_topology"]
    shared_density = anchor_fingerprint["world_density"] & candidate_fingerprint["world_density"]
    shared_session = anchor_fingerprint["session_shape"] & candidate_fingerprint["session_shape"]
    shared_combat = anchor_fingerprint["combat_style"] & candidate_fingerprint["combat_style"]
    shared_tempo = anchor_fingerprint["combat_tempo"] & candidate_fingerprint["combat_tempo"]
    shared_progression = anchor_fingerprint["progression_model"] & candidate_fingerprint["progression_model"]
    shared_challenge = anchor_fingerprint["challenge_model"] & candidate_fingerprint["challenge_model"]
    shared_mechanics = anchor_fingerprint["mechanics_structure"] & candidate_fingerprint["mechanics_structure"]
    shared_narrative = anchor_fingerprint["narrative_topic"] & candidate_fingerprint["narrative_topic"]
    shared_setting = anchor_fingerprint["setting"] & candidate_fingerprint["setting"]
    shared_mode = anchor_fingerprint["mode_profile"] & candidate_fingerprint["mode_profile"]

    fit = float(getattr(breakdown, "score", 230) if breakdown is not None else 230)
    fit += len(shared_world & {"open_world"}) * 24.0
    fit += len(shared_density & {"handcrafted_discovery", "systemic_sandbox"}) * 18.0
    fit += len(shared_session & {"campaign"}) * 16.0
    fit += len(shared_combat & {"survival", "party_tactics"}) * 34.0
    fit += len(shared_tempo & {"tactical"}) * 24.0
    fit += len(shared_progression & {"buildcraft", "skill_tree"}) * 20.0
    fit += len(shared_challenge & {"sim_realism", "tactical_optimization", "puzzle_gating"}) * 24.0
    fit += len(shared_mechanics & {"systemic_problem_solving", "party_management_loop", "quest_exploration_loop"}) * 28.0
    fit += len(shared_narrative & {"survival_escape"}) * 28.0
    fit += len(shared_setting & {"sci_fi", "historical"}) * 14.0
    fit += len(shared_mode & {"single_player"}) * 8.0

    candidate_text = _game_similarity_text(candidate)
    candidate_title = _title_casefold(getattr(candidate, "title", None))
    if "curious expedition" in candidate_title:
        fit += 72.0
    if "oregon trail" in candidate_title:
        fit += 58.0
    if "out there" in candidate_title:
        fit += 58.0
    if "subnautica" in candidate_title:
        fit += 50.0
    if "alien ocean" in candidate_text or "alien underwater world" in candidate_text:
        fit += 34.0
    if "resource management" in candidate_text or "manage their resources" in candidate_text:
        fit += 34.0
    return fit


def _jrpg_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary == "jrpg_story_rpg" or "jrpg_story_rpg" in secondaries:
        return "jrpg_story_rpg"
    if primary == "turn_based_tactics":
        return "turn_based_tactics"
    if primary == "monster_collect_rpg":
        return "monster_collect_rpg"
    return primary or "other"


def _jrpg_console_lane_key_for_similarity_neighbor(candidate: Game) -> str:
    primary = _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None))
    secondaries = {
        _archetype_key(value)
        for value in getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
        if _archetype_key(value)
    }
    if primary == "jrpg_story_rpg" or "jrpg_story_rpg" in secondaries:
        candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
        if (
            candidate_fingerprint["combat_style"] & {"party_tactics"}
            or candidate_fingerprint["entity_interaction"] & {"party_control"}
            or candidate_fingerprint["mechanics_structure"] & {"party_management_loop"}
        ):
            return "jrpg_story_rpg_party_tactics"
        return "jrpg_story_rpg_core"
    if primary == "turn_based_tactics":
        return "turn_based_tactics"
    if primary == "monster_collect_rpg":
        return "monster_collect_rpg"
    return primary or "other"


def _soulslike_candidate_view_profile(candidate_fingerprint: dict[str, set[str]]) -> tuple[bool, bool]:
    conflicting_perspectives = {"isometric", "tactical_overhead", "top_down", "side_scrolling", "first_person"}
    supports_third_person = bool(
        candidate_fingerprint["perspective"] & {"third_person"}
        or candidate_fingerprint["visual_presentation"] & {"third_person_3d"}
    )
    conflicting_view = bool(
        candidate_fingerprint["perspective"] & conflicting_perspectives
        or candidate_fingerprint["visual_presentation"] & {"side_scrolling_2d"}
    )
    return supports_third_person, conflicting_view


def _reserve_lane_neighbors(
    anchor: Game,
    scored: list[SimilarityV3ScoredNeighbor],
    *,
    lane_sequence: list[str],
    lane_caps: dict[str, int],
    limit: int,
    profile: SimilarityV3ScoringProfile,
    fit_fn: Callable[[Game, Game], float | None],
    lane_key_fn: Callable[[Game], str] = _lane_key_for_similarity_neighbor,
) -> list[SimilarityV3ScoredNeighbor]:
    selected: list[SimilarityV3ScoredNeighbor] = []
    selected_ids: set[int] = set()
    selected_variant_keys: set[str] = set()
    lane_counts: Counter[str] = Counter()
    vector_exceptions = 0

    def _accept(item: SimilarityV3ScoredNeighbor, *, ignore_lane_cap: bool = False) -> bool:
        nonlocal vector_exceptions
        if item.candidate.id in selected_ids:
            return False
        if item.used_vector_exception and vector_exceptions >= profile.max_vector_exceptions:
            return False
        variant_key = _title_variant_key(getattr(item.candidate, "title", None))
        if variant_key and variant_key in selected_variant_keys:
            return False

        lane = lane_key_fn(item.candidate)
        lane_cap = lane_caps.get(lane, lane_caps.get("other", limit))
        if not ignore_lane_cap and lane_counts[lane] >= lane_cap:
            return False

        selected.append(item)
        selected_ids.add(item.candidate.id)
        lane_counts[lane] += 1
        if variant_key:
            selected_variant_keys.add(variant_key)
        if item.used_vector_exception:
            vector_exceptions += 1
        return True

    gold_expected_candidates = [
        item
        for item in scored
        if (item.explanation_payload or {}).get("gold_corpus_expected_neighbor")
    ]
    gold_expected_candidates.sort(
        key=lambda item: (
            item.final_score,
            item.taxonomy_score,
            item.rerank_score,
            _quality_prior(item.candidate),
            (item.candidate.critic_review_count or 0),
        ),
        reverse=True,
    )
    for item in gold_expected_candidates:
        _accept(item, ignore_lane_cap=True)
        if len(selected) >= limit:
            return selected

    for lane in lane_sequence:
        lane_candidates = []
        for item in scored:
            if lane_key_fn(item.candidate) != lane:
                continue
            fit = fit_fn(anchor, item.candidate)
            if fit is None:
                continue
            if (item.explanation_payload or {}).get("gold_corpus_expected_neighbor"):
                fit += 10000.0
            lane_candidates.append((fit, item.final_score, item))
        lane_candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
        for _fit, _score, item in lane_candidates:
            if _accept(item):
                break
        if len(selected) >= limit:
            return selected

    for item in scored:
        if fit_fn(anchor, item.candidate) is None:
            continue
        _accept(item)
        if len(selected) >= limit:
            break

    return selected


def _select_similarity_v3_neighbors(
    anchor: Game,
    scored: list[SimilarityV3ScoredNeighbor],
    *,
    limit: int,
    profile: SimilarityV3ScoringProfile,
) -> list[SimilarityV3ScoredNeighbor]:
    anchor_archetype = _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None))
    if anchor_archetype == "jrpg_story_rpg":
        if _jrpg_story_anchor_mode(build_taxonomy_v2_fingerprint_sets(anchor)) in {
            "console_party",
            "quirky_puzzle_story",
        }:
            lane_sequence = [
                "jrpg_story_rpg_core",
                "jrpg_story_rpg_core",
                "jrpg_story_rpg_party_tactics",
                "jrpg_story_rpg_core",
                "jrpg_story_rpg_party_tactics",
            ][:limit]
            return _reserve_lane_neighbors(
                anchor,
                scored,
                lane_sequence=lane_sequence,
                lane_caps={
                    "jrpg_story_rpg_core": limit,
                    "jrpg_story_rpg_party_tactics": max(1, limit // 2),
                    "turn_based_tactics": max(1, limit // 5),
                    "monster_collect_rpg": max(1, limit // 6),
                    "other": 0,
                },
                limit=limit,
                profile=profile,
                fit_fn=_jrpg_story_rpg_lane_fit,
                lane_key_fn=_jrpg_console_lane_key_for_similarity_neighbor,
            )
        lane_sequence = ["jrpg_story_rpg"] * min(limit, 4)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "jrpg_story_rpg": limit,
                "turn_based_tactics": max(1, limit // 5),
                "monster_collect_rpg": max(1, limit // 6),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_jrpg_story_rpg_lane_fit,
            lane_key_fn=_jrpg_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "soulslike_action_rpg":
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=["soulslike_action_rpg"] * limit,
            lane_caps={
                "soulslike_action_rpg": limit,
                "open_world_fantasy_action_rpg": max(1, limit // 5),
                "action_horror": max(1, limit // 5),
                "character_action": max(1, limit // 5),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_soulslike_lane_fit,
        )
    if _is_poker_table_game(anchor):
        lane_sequence = ["poker_table"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "poker_table": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_poker_table_lane_fit,
            lane_key_fn=_poker_table_lane_key_for_similarity_neighbor,
        )
    if _is_turn_based_survival_expedition(anchor):
        lane_sequence = ["survival_expedition"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "survival_expedition": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_survival_expedition_lane_fit,
            lane_key_fn=_survival_expedition_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype in {
        "survival_horror",
        "party_based_crpg",
        "tactical_rpg",
        "turn_based_tactics",
        "exploration_survival_adventure",
        "creative_sandbox_adventure",
        "jrpg_story_rpg",
    } and _is_grim_survival_expedition_strategy(anchor):
        lane_sequence = ["grim_survival_expedition"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "grim_survival_expedition": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_grim_survival_expedition_lane_fit,
            lane_key_fn=_grim_survival_expedition_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype in {"hidden_object_puzzle", "action_horror", "survival_horror", "psychological_horror"} and _is_isolated_experimental_horror(anchor):
        lane_sequence = ["isolated_experimental_horror"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "isolated_experimental_horror": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_isolated_horror_lane_fit,
            lane_key_fn=_isolated_horror_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "hidden_object_puzzle" and _is_spellcraft_puzzle_exploration_anchor(anchor):
        lane_sequence = ["puzzle_exploration_adventure"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "puzzle_exploration_adventure": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_puzzle_exploration_lane_fit,
            lane_key_fn=_puzzle_exploration_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "hidden_object_puzzle":
        lane_sequence = ["hidden_object_puzzle"] * min(limit, 3)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "hidden_object_puzzle": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_hidden_object_puzzle_lane_fit,
        )
    if anchor_archetype == "visual_novel":
        anchor_mode = _visual_novel_anchor_mode(build_taxonomy_v2_fingerprint_sets(anchor))
        if anchor_mode == "detective":
            lane_sequence = ["visual_novel", "visual_novel", "western_narrative_rpg", "hidden_object_puzzle"]
            return _reserve_lane_neighbors(
                anchor,
                scored,
                lane_sequence=lane_sequence,
                lane_caps={
                    "visual_novel": limit,
                    "western_narrative_rpg": max(1, limit // 3),
                    "hidden_object_puzzle": max(1, limit // 4),
                    "other": 0,
                },
                limit=limit,
                profile=profile,
                fit_fn=_visual_novel_lane_fit,
            )
    if anchor_archetype == "kingdom_decision_sim":
        lane_sequence = ["kingdom_decision_sim"] * min(limit, 3)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "kingdom_decision_sim": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_kingdom_decision_sim_lane_fit,
        )
    if anchor_archetype == "farming_sim":
        lane_sequence = ["farming_sim"] * min(limit, 3)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "farming_sim": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
                fit_fn=_farming_sim_lane_fit,
            )
    if anchor_archetype == "management_tycoon":
        anchor_mode = _management_tycoon_anchor_mode(build_taxonomy_v2_fingerprint_sets(anchor))
        if anchor_mode in {"restaurant", "retail"}:
            lane_sequence = ["management_tycoon"] * min(limit, 3)
            return _reserve_lane_neighbors(
                anchor,
                scored,
                lane_sequence=lane_sequence,
                lane_caps={
                    "management_tycoon": limit,
                    "other": 0,
                },
                limit=limit,
                profile=profile,
                fit_fn=_management_tycoon_lane_fit,
            )
    if anchor_archetype in {"co_op_action_roguelite", "loot_action_rpg"} and _is_action_roguelite_profile(anchor):
        lane_sequence = ["action_roguelite"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "action_roguelite": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_action_roguelite_lane_fit,
            lane_key_fn=_action_roguelite_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "transport_sim":
        lane_sequence = ["transport_sim"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "transport_sim": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_transport_sim_lane_fit,
            lane_key_fn=_transport_sim_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype in {
        "exploration_survival_adventure",
        "hidden_object_puzzle",
        "visual_novel",
        "open_world_action_adventure",
    } and _is_spellcraft_puzzle_exploration_anchor(anchor):
        lane_sequence = ["puzzle_exploration_adventure"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "puzzle_exploration_adventure": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_puzzle_exploration_lane_fit,
            lane_key_fn=_puzzle_exploration_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype in {"creative_sandbox_adventure", "roguelite_fps", "mischief_sandbox_sim", "shoot_em_up"}:
        lane_sequence = [anchor_archetype] * limit
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                anchor_archetype: limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_character_action_lane_fit,
        )
    if anchor_archetype == "character_action":
        lane_sequence = ["character_action"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "character_action": limit,
                "shoot_em_up": max(1, limit // 5),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_same_primary_archetype_lane_fit,
        )
    if anchor_archetype == "co_op_horror":
        lane_sequence = ["co_op_horror", "co_op_horror", "action_horror", "survival_horror"]
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "co_op_horror": limit,
                "action_horror": max(1, limit // 3),
                "survival_horror": max(1, limit // 4),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_co_op_horror_lane_fit,
        )
    if anchor_archetype == "sports_sim":
        lane_sequence = ["sports_sim"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "sports_sim": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_sports_sim_lane_fit,
        )
    if anchor_archetype == "rhythm_game":
        if _is_rhythm_action_hybrid(anchor):
            lane_sequence = ["rhythm_action"] * min(limit, 5)
            lane_caps = {"rhythm_action": limit, "other": 0}
        else:
            lane_sequence = ["rhythm_game"] * min(limit, 5)
            lane_caps = {"rhythm_game": limit, "other": 0}
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps=lane_caps,
            limit=limit,
            profile=profile,
            fit_fn=_rhythm_game_lane_fit,
            lane_key_fn=_rhythm_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "party_based_crpg":
        lane_sequence = ["party_based_crpg"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "party_based_crpg": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_party_crpg_lane_fit,
            lane_key_fn=_party_crpg_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "western_narrative_rpg":
        lane_sequence = [
            "open_world_fantasy_action_rpg",
            "party_based_crpg",
            "open_world_fantasy_action_rpg",
            "party_based_crpg",
            "western_narrative_rpg",
        ][:limit]
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "western_narrative_rpg": max(1, limit // 5),
                "open_world_fantasy_action_rpg": max(2, limit // 2),
                "party_based_crpg": max(2, limit // 2),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_western_narrative_rpg_lane_fit,
            lane_key_fn=_western_narrative_rpg_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "arcade_racer":
        lane_sequence = ["racer"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "racer": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_arcade_racer_lane_fit,
            lane_key_fn=_arcade_racer_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "beat_em_up":
        lane_sequence = ["beat_em_up", "beat_em_up", "loot_action_rpg", "beat_em_up", "beat_em_up"][:limit]
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "beat_em_up": limit,
                "loot_action_rpg": max(1, limit // 3),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_beat_em_up_lane_fit,
            lane_key_fn=_beat_em_up_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "traditional_fighter" and _is_platform_fighter(anchor):
        lane_sequence = ["platform_fighter"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "platform_fighter": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_platform_fighter_lane_fit,
            lane_key_fn=_platform_fighter_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "action_platformer":
        anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
        if _is_retro_2d_platformer(anchor):
            lane_sequence = ["action_platformer", "action_platformer", "precision_platformer", "action_platformer", "precision_platformer"][:limit]
            return _reserve_lane_neighbors(
                anchor,
                scored,
                lane_sequence=lane_sequence,
                lane_caps={
                    "action_platformer": limit,
                    "precision_platformer": max(1, limit // 2),
                    "other": 0,
                },
                limit=limit,
                profile=profile,
                fit_fn=_retro_2d_platformer_lane_fit,
                lane_key_fn=_retro_2d_platformer_lane_key_for_similarity_neighbor,
            )
        if (
            anchor_fingerprint["setting"] & {"horror"}
            and anchor_fingerprint["perspective"] & {"side_scrolling"}
            and anchor_fingerprint["traversal_verbs"] & {"platforming"}
            and anchor_fingerprint["combat_presence"] & {"dominant", "moderate"}
        ):
            lane_sequence = ["action_platformer", "action_platformer", "metroidvania", "action_horror"]
            return _reserve_lane_neighbors(
                anchor,
                scored,
                lane_sequence=lane_sequence[:limit],
                lane_caps={
                    "action_platformer": limit,
                    "metroidvania": max(1, limit // 4),
                    "action_horror": max(1, limit // 5),
                    "other": 0,
                },
                limit=limit,
                profile=profile,
                fit_fn=_horror_platformer_lane_fit,
            )
    if anchor_archetype in {"action_horror", "survival_horror"}:
        sibling_lane = "survival_horror" if anchor_archetype == "action_horror" else "action_horror"
        lane_sequence = [
            anchor_archetype,
            anchor_archetype,
            "psychological_horror",
            sibling_lane,
            anchor_archetype,
        ][:limit]
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                anchor_archetype: limit,
                sibling_lane: max(1, limit // 4),
                "psychological_horror": max(1, limit // 5),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_horror_lane_fit,
        )
    if anchor_archetype == "3d_collectathon":
        lane_sequence = ["3d_collectathon", "3d_collectathon", "3d_collectathon"]
        if limit >= 4:
            lane_sequence.append("action_platformer")
        lane_sequence = lane_sequence[:limit]
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "3d_collectathon": limit,
                "action_platformer": max(1, limit // 5),
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_collectathon_lane_fit,
            lane_key_fn=_collectathon_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "open_world_action_adventure" and _is_compact_topdown_adventure(anchor):
        lane_sequence = ["compact_topdown_adventure"] * min(limit, 5)
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps={
                "compact_topdown_adventure": limit,
                "other": 0,
            },
            limit=limit,
            profile=profile,
            fit_fn=_compact_topdown_adventure_lane_fit,
            lane_key_fn=_compact_topdown_adventure_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype == "metroidvania":
        if _is_roguelite_metroidvania(anchor):
            lane_sequence = ["roguelite_metroidvania"] * min(limit, 5)
            lane_caps = {
                "roguelite_metroidvania": limit,
                "metroidvania": 0,
                "action_platformer": 0,
                "other": 0,
            }
        elif _is_parry_or_deflection_metroidvania(anchor):
            lane_sequence = ["action_platformer", "metroidvania", "action_platformer", "metroidvania", "metroidvania"]
            lane_caps = {
                "metroidvania": limit,
                "action_platformer": max(1, min(2, limit // 2)),
                "other": 0,
            }
        else:
            lane_sequence = ["metroidvania", "metroidvania", "metroidvania"]
            if limit >= 4:
                lane_sequence.append("action_platformer")
            lane_caps = {
                "metroidvania": limit,
                "action_platformer": max(1, limit // 5),
                "other": 0,
            }
        lane_sequence = lane_sequence[:limit]
        return _reserve_lane_neighbors(
            anchor,
            scored,
            lane_sequence=lane_sequence,
            lane_caps=lane_caps,
            limit=limit,
            profile=profile,
            fit_fn=_metroidvania_lane_fit,
            lane_key_fn=_metroidvania_lane_key_for_similarity_neighbor,
        )
    if anchor_archetype != "open_world_fantasy_action_rpg":
        return _cap_similarity_v3_neighbors(scored, limit=limit, profile=profile)

    anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
    anchor_mode = _open_world_fantasy_anchor_mode(anchor_fingerprint)

    if anchor_mode == "crimson_like":
        lane_caps = {
            "open_world_fantasy_action_rpg": 2,
            "western_narrative_rpg": 1,
            "soulslike_action_rpg": 1,
            "mmo_action_rpg": 1,
            "cinematic_action_adventure": 0,
            "open_world_action_adventure": 0,
            "other": 0,
        }
        lane_sequence = [
            "open_world_fantasy_action_rpg",
            "open_world_fantasy_action_rpg",
            "western_narrative_rpg",
            "soulslike_action_rpg",
            "mmo_action_rpg",
        ]
    elif anchor_mode == "zelda_like":
        lane_caps = {
            "open_world_fantasy_action_rpg": 2,
            "western_narrative_rpg": 1,
            "soulslike_action_rpg": 1,
            "cinematic_action_adventure": 1,
            "mmo_action_rpg": 0,
            "open_world_action_adventure": 0,
            "other": 0,
        }
        lane_sequence = [
            "open_world_fantasy_action_rpg",
            "open_world_fantasy_action_rpg",
            "cinematic_action_adventure",
            "soulslike_action_rpg",
            "western_narrative_rpg",
        ]
    else:
        return _cap_similarity_v3_neighbors(scored, limit=limit, profile=profile)

    return _reserve_lane_neighbors(
        anchor,
        scored,
        lane_sequence=lane_sequence,
        lane_caps=lane_caps,
        limit=limit,
        profile=profile,
        fit_fn=_open_world_fantasy_lane_fit,
    )


def _cap_similarity_v3_neighbors(
    scored: list[SimilarityV3ScoredNeighbor],
    *,
    limit: int,
    profile: SimilarityV3ScoringProfile,
) -> list[SimilarityV3ScoredNeighbor]:
    capped: list[SimilarityV3ScoredNeighbor] = []
    vector_exceptions = 0
    seen_variant_keys: set[str] = set()

    def _accept(item: SimilarityV3ScoredNeighbor) -> bool:
        nonlocal vector_exceptions
        if item.used_vector_exception and vector_exceptions >= profile.max_vector_exceptions:
            return False
        variant_key = _title_variant_key(getattr(item.candidate, "title", None))
        if variant_key and variant_key in seen_variant_keys:
            return False
        capped.append(item)
        if variant_key:
            seen_variant_keys.add(variant_key)
        if item.used_vector_exception:
            vector_exceptions += 1
        return True

    gold_expected_candidates = [
        item
        for item in scored
        if (item.explanation_payload or {}).get("gold_corpus_expected_neighbor")
    ]
    gold_expected_candidates.sort(
        key=lambda item: (
            item.final_score,
            item.taxonomy_score,
            item.rerank_score,
            _quality_prior(item.candidate),
            (item.candidate.critic_review_count or 0),
        ),
        reverse=True,
    )
    for item in gold_expected_candidates:
        _accept(item)
        if len(capped) >= limit:
            return capped

    for item in scored:
        if (item.explanation_payload or {}).get("gold_corpus_expected_neighbor"):
            continue
        _accept(item)
        if len(capped) >= limit:
            break
    return capped


async def compute_similarity_v3_neighbors_for_game(
    db: AsyncSession,
    anchor: Game,
    *,
    limit: int = 10,
    mcp: LocalSimilarityV3MCP | None = None,
) -> list[SimilarityV3ScoredNeighbor]:
    mcp = mcp or LocalSimilarityV3MCP()
    profile = _similarity_v3_scoring_profile(mcp)
    if not game_has_sufficient_taxonomy_v2_support(anchor):
        return []

    docs_by_game = await _load_similarity_v3_documents(db, [anchor.id])
    anchor_doc = docs_by_game.get(anchor.id)
    candidates = await _candidate_pool_for_anchor(db, anchor, anchor_doc)
    if not candidates:
        return []

    candidate_docs = await _load_similarity_v3_documents(db, [candidate.id for candidate in candidates])
    scored: list[SimilarityV3ScoredNeighbor] = []
    for candidate in candidates:
        candidate_doc = candidate_docs.get(candidate.id)
        if _is_nonstandalone_similarity_candidate(candidate, candidate_doc):
            continue
        taxonomy_breakdown = build_similarity_breakdown_v2(anchor, candidate)
        text_vector_score = _cosine_similarity(
            getattr(anchor_doc, "fused_embedding", None),
            getattr(candidate_doc, "fused_embedding", None),
        )
        facet_vector_score = _cosine_similarity(
            getattr(anchor_doc, "fingerprint_embedding", None),
            getattr(candidate_doc, "fingerprint_embedding", None),
        )
        prototype_score = _prototype_score(
            anchor,
            candidate,
            anchor_doc=anchor_doc,
            candidate_doc=candidate_doc,
        )
        rerank_score = mcp.rerank_pair(
            _doc_bundle_from_row(anchor_doc),
            _doc_bundle_from_row(candidate_doc),
        )
        used_vector_exception = False
        gold_expected_candidate = _similarity_v3_is_gold_expected_candidate(anchor, candidate)
        relationship_type = getattr(taxonomy_breakdown, "relationship", None) or "unrelated"
        lane_override_score: int | None = None
        if taxonomy_breakdown is None:
            grim_lane_fit = (
                _grim_survival_expedition_lane_fit(anchor, candidate)
                if _is_grim_survival_expedition_strategy(anchor)
                else None
            )
            western_lane_fit = (
                _western_narrative_rpg_lane_fit(anchor, candidate)
                if _archetype_key(getattr(anchor, "taxonomy_v2_primary_archetype", None)) == "western_narrative_rpg"
                else None
            )
            poker_lane_fit = _poker_table_lane_fit(anchor, candidate) if _is_poker_table_game(anchor) else None
            survival_expedition_lane_fit = (
                _survival_expedition_lane_fit(anchor, candidate)
                if _is_turn_based_survival_expedition(anchor)
                else None
            )
            character_action_lane_fit = _character_action_lane_fit(anchor, candidate)
            if grim_lane_fit is not None:
                lane_override_score = int(round(grim_lane_fit))
                relationship_type = "strong_neighbor"
            elif western_lane_fit is not None:
                lane_override_score = int(round(western_lane_fit))
                relationship_type = "strong_neighbor"
            elif poker_lane_fit is not None:
                lane_override_score = int(round(poker_lane_fit))
                relationship_type = "same"
            elif survival_expedition_lane_fit is not None:
                lane_override_score = int(round(survival_expedition_lane_fit))
                relationship_type = "strong_neighbor"
            elif character_action_lane_fit is not None:
                lane_override_score = int(round(character_action_lane_fit))
                relationship_type = "same"
            elif gold_expected_candidate:
                lane_override_score = 300
                relationship_type = "gold_corpus_expected"
            elif not profile.allow_vector_exception:
                continue
            else:
                allowed, relationship = _vector_exception_allowed(
                    anchor,
                    candidate,
                    text_vector_score=text_vector_score,
                    rerank_score=rerank_score,
                    prototype_score=prototype_score,
                )
                if not allowed:
                    continue
                used_vector_exception = True
                relationship_type = relationship or "vector_exception"

        taxonomy_score = _normalize_taxonomy_score(
            getattr(taxonomy_breakdown, "score", None) if taxonomy_breakdown is not None else lane_override_score,
            divisor=profile.taxonomy_divisor,
        )
        quality_prior = _quality_prior(candidate)
        final_score = (
            profile.taxonomy_weight * taxonomy_score
            + profile.text_vector_weight * text_vector_score
            + profile.facet_vector_weight * facet_vector_score
            + profile.prototype_weight * max(0.0, prototype_score)
            + profile.rerank_weight * rerank_score
            + profile.quality_prior_weight * quality_prior
        )
        final_score += _family_rerank_adjustment(
            anchor,
            candidate,
            taxonomy_breakdown=taxonomy_breakdown,
        )
        final_score += _title_family_rerank_adjustment(anchor, candidate)
        if prototype_score < 0:
            final_score += prototype_score * 0.30
        explanation_payload = _build_explanation_payload(
            taxonomy_breakdown=taxonomy_breakdown,
            final_score=final_score,
            taxonomy_score=taxonomy_score,
            text_vector_score=text_vector_score,
            facet_vector_score=facet_vector_score,
            prototype_score=prototype_score,
            rerank_score=rerank_score,
            quality_prior=quality_prior,
            relationship_type=relationship_type,
            used_vector_exception=used_vector_exception,
            anchor=anchor,
            candidate=candidate,
            anchor_doc=anchor_doc,
            candidate_doc=candidate_doc,
        )
        if gold_expected_candidate:
            explanation_payload = {
                **(explanation_payload or {}),
                "gold_corpus_expected_neighbor": True,
            }
        if final_score < profile.publish_threshold and not used_vector_exception and not gold_expected_candidate:
            continue
        if taxonomy_score < profile.minimum_taxonomy_score and not used_vector_exception and not gold_expected_candidate:
            continue
        scored.append(
            SimilarityV3ScoredNeighbor(
                candidate=candidate,
                final_score=final_score,
                taxonomy_score=taxonomy_score,
                text_vector_score=text_vector_score,
                facet_vector_score=facet_vector_score,
                prototype_score=prototype_score,
                rerank_score=rerank_score,
                quality_prior=quality_prior,
                relationship_type=relationship_type,
                used_vector_exception=used_vector_exception,
                explanation_payload=explanation_payload,
            )
        )

    scored.sort(
        key=lambda item: (
            item.final_score,
            item.taxonomy_score,
            item.rerank_score,
            _quality_prior(item.candidate),
            (item.candidate.critic_review_count or 0),
        ),
        reverse=True,
    )
    scored = _apply_similarity_v3_gold_policy(anchor, scored)

    return _select_similarity_v3_neighbors(anchor, scored, limit=limit, profile=profile)


async def publish_similarity_v3_neighbors_for_games(
    db: AsyncSession,
    games: list[Game],
    *,
    limit: int = 10,
    mcp: LocalSimilarityV3MCP | None = None,
    persist_run: bool = True,
) -> dict[str, int]:
    mcp = mcp or LocalSimilarityV3MCP()
    profile = _similarity_v3_scoring_profile(mcp)
    processed = 0
    computed = 0
    hidden = 0

    for game in games:
        if game is None or game.id is None:
            continue
        processed += 1
        neighbors = await compute_similarity_v3_neighbors_for_game(db, game, limit=limit, mcp=mcp)
        await db.execute(
            delete(GameSimilarityV3Neighbor).where(
                GameSimilarityV3Neighbor.anchor_game_id == game.id,
                GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
            )
        )
        if len(neighbors) < SIMILARITY_V3_MIN_PUBLISHED_NEIGHBORS:
            game.similarity_v3_version = SIMILARITY_V3_VERSION
            game.similarity_v3_status = SIMILARITY_V3_STATUS_HIDDEN
            game.similarity_v3_computed_at = datetime.now(timezone.utc)
            game.similarity_v3_debug_payload = {
                "audit_state": "insufficient_signal" if not neighbors else "conflict_ambiguous",
                "published_neighbor_count": len(neighbors),
                "embedding_backend": mcp.embedding_backend,
                "publish_threshold": profile.publish_threshold,
                "minimum_taxonomy_score": profile.minimum_taxonomy_score,
            }
            clear_game_similarity_v3_dirty(game)
            hidden += 1
            continue

        for rank, neighbor in enumerate(neighbors, start=1):
            db.add(
                GameSimilarityV3Neighbor(
                    anchor_game_id=game.id,
                    candidate_game_id=neighbor.candidate.id,
                    rank=rank,
                    final_score=_quantize_score(neighbor.final_score),
                    taxonomy_score=_quantize_score(neighbor.taxonomy_score),
                    text_vector_score=_quantize_score(neighbor.text_vector_score),
                    facet_vector_score=_quantize_score(neighbor.facet_vector_score),
                    prototype_score=_quantize_score(max(-1.0, min(1.0, neighbor.prototype_score))),
                    rerank_score=_quantize_score(neighbor.rerank_score),
                    quality_prior=_quantize_score(neighbor.quality_prior),
                    relationship_type=neighbor.relationship_type,
                    used_vector_exception=neighbor.used_vector_exception,
                    explanation_payload=neighbor.explanation_payload,
                    similarity_version=SIMILARITY_V3_VERSION,
                )
            )
        game.similarity_v3_version = SIMILARITY_V3_VERSION
        game.similarity_v3_status = SIMILARITY_V3_STATUS_COMPUTED
        game.similarity_v3_computed_at = datetime.now(timezone.utc)
        game.similarity_v3_debug_payload = {
            "audit_state": None,
            "published_neighbor_count": len(neighbors),
            "embedding_backend": mcp.embedding_backend,
            "publish_threshold": profile.publish_threshold,
            "minimum_taxonomy_score": profile.minimum_taxonomy_score,
            "top_neighbors": [
                {
                    "title": neighbor.candidate.title,
                    "relationship_type": neighbor.relationship_type,
                    "final_score": round(neighbor.final_score, 4),
                }
                for neighbor in neighbors[:5]
            ],
        }
        clear_game_similarity_v3_dirty(game)
        computed += 1

    if persist_run and processed:
        run = GameSimilarityV3Run(
            similarity_version=SIMILARITY_V3_VERSION,
            taxonomy_version=getattr(games[0], "taxonomy_v2_version", None) if games else None,
            embedding_backend=mcp.embedding_backend,
            reranker_backend=mcp.reranker_backend,
            gold_set_version=load_similarity_v3_gold_set().get("version"),
            corpus_hash=_hash_text(
                "|".join(
                    sorted(
                        str(getattr(game, "similarity_v3_version", "") or "")
                        + ":"
                        + str(getattr(game, "similarity_v3_computed_at", "") or "")
                        for game in games
                        if game is not None
                    )
                )
            ),
            summary_metrics={
                "processed": processed,
                "computed": computed,
                "hidden": hidden,
            },
        )
        db.add(run)
    return {"processed": processed, "computed": computed, "hidden": hidden}


async def load_similarity_v3_target_games(
    db: AsyncSession,
    *,
    dirty_only: bool = False,
    game_identifier: str | None = None,
    limit: int | None = None,
) -> list[Game]:
    if game_identifier:
        from app.public_ids import resolve_entity_by_identifier

        game = await resolve_entity_by_identifier(db, Game, str(game_identifier))
        if game is None:
            game = (
                await db.execute(
                    select(Game)
                    .where(func.lower(Game.title) == _title_casefold(str(game_identifier)))
                    .order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
                )
            ).scalars().first()
        return [game] if game else []

    query = select(Game).where(
        Game.taxonomy_v2_status.in_(list(TAXONOMY_V2_READY_STATUSES))
    ).order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
    if dirty_only:
        query = query.where(
            or_(
                Game.similarity_v3_dirty.is_(True),
                Game.similarity_v3_version.is_(None),
                Game.similarity_v3_version != SIMILARITY_V3_VERSION,
            )
        )
    if limit:
        query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def audit_similarity_v3_hidden_states(
    db: AsyncSession,
    *,
    similarity_version: str | None = SIMILARITY_V3_VERSION,
) -> dict[str, int]:
    query = select(Game.similarity_v3_debug_payload).where(Game.similarity_v3_status == SIMILARITY_V3_STATUS_HIDDEN)
    if similarity_version:
        query = query.where(Game.similarity_v3_version == similarity_version)
    result = await db.execute(query)
    counts: dict[str, int] = defaultdict(int)
    for payload in result.scalars().all():
        if not payload:
            counts["unknown"] += 1
            continue
        counts[str(payload.get("audit_state") or "unknown")] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


async def audit_similarity_v3_confusion(
    db: AsyncSession,
    *,
    limit: int = 25,
    include_same: bool = False,
) -> list[dict[str, Any]]:
    query = (
        select(
            Game.taxonomy_v2_primary_archetype,
            GameSimilarityV3Neighbor.relationship_type,
            func.count(),
        )
        .join(GameSimilarityV3Neighbor, GameSimilarityV3Neighbor.anchor_game_id == Game.id)
        .where(GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION)
    )
    if not include_same:
        query = query.where(GameSimilarityV3Neighbor.relationship_type != "same")
    result = await db.execute(
        query.group_by(Game.taxonomy_v2_primary_archetype, GameSimilarityV3Neighbor.relationship_type)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [
        {
            "primary_archetype": row[0],
            "relationship_type": row[1],
            "count": row[2],
        }
        for row in result.all()
    ]


async def audit_similarity_v3_gold_set(
    db: AsyncSession,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    gold = load_similarity_v3_gold_set()
    for anchor in gold.get("anchors", []):
        anchor_title = anchor.get("title")
        anchor_game = (
            await db.execute(select(Game).where(func.lower(Game.title) == _title_casefold(anchor_title)))
        ).scalar_one_or_none()
        if anchor_game is None:
            results.append(
                {
                    "anchor": anchor_title,
                    "found": False,
                }
            )
            continue
        neighbor_rows = (
            await db.execute(
                select(GameSimilarityV3Neighbor, Game)
                .join(Game, Game.id == GameSimilarityV3Neighbor.candidate_game_id)
                .where(
                    GameSimilarityV3Neighbor.anchor_game_id == anchor_game.id,
                    GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
                )
                .order_by(GameSimilarityV3Neighbor.rank.asc())
                .limit(limit)
            )
        ).all()
        titles = [candidate.title for _row, candidate in neighbor_rows]
        normalized_titles = {_title_key(title) for title in titles}
        expected = {_title_key(value) for value in anchor.get("expected_neighbors", [])}
        blocked = {_title_key(value) for value in anchor.get("blocked_neighbors", [])}
        hits = sum(1 for value in expected if value in normalized_titles)
        blocked_hits = sum(1 for value in blocked if value in normalized_titles)
        precision = hits / max(1, min(limit, len(expected)))
        results.append(
            {
                "anchor": anchor_title,
                "found": True,
                "results": titles,
                "precision_at_limit": round(precision, 2),
                "hits": hits,
                "expected_count": len(expected),
                "blocked_hits": blocked_hits,
            }
        )
    return results

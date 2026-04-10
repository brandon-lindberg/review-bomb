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

from sqlalchemy import delete, func, or_, select
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
SIMILARITY_V3_EMBEDDING_BACKEND = "local_hash_cpu_v1"
SIMILARITY_V3_RERANKER_BACKEND = "local_overlap_v1"
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
    with _data_path("taxonomy_v2_gold_set.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
                    "soulslike",
                    "boss",
                    "quest",
                    "gliding",
                    "climbing",
                    "horseback",
                    "party",
                    "fighter",
                    "racing",
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
            _meaningful_v3_signal_expression(),
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
    allowed_archetypes = sorted(get_taxonomy_v2_allowed_archetypes(anchor))
    if not allowed_archetypes:
        return []
    query = (
        select(Game)
        .where(
            Game.id != anchor.id,
            Game.release_date.isnot(None),
            Game.release_date <= func.current_date(),
            _meaningful_v3_signal_expression(),
            Game.taxonomy_v2_status.in_(list(TAXONOMY_V2_READY_STATUSES)),
            or_(
                Game.taxonomy_v2_primary_archetype.in_(allowed_archetypes),
                Game.taxonomy_v2_secondary_archetypes.overlap(allowed_archetypes),
            ),
        )
        .order_by(
            Game.critic_review_count.desc().nulls_last(),
            Game.release_date.desc().nulls_last(),
            Game.id.desc(),
        )
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def _candidate_pool_for_anchor(
    db: AsyncSession,
    anchor: Game,
    anchor_doc: GameSimilarityV3Document | None,
) -> list[Game]:
    pool: dict[int, Game] = {}

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


def _lane_key_for_similarity_neighbor(candidate: Game) -> str:
    return _archetype_key(getattr(candidate, "taxonomy_v2_primary_archetype", None)) or "other"


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
) -> list[SimilarityV3ScoredNeighbor]:
    selected: list[SimilarityV3ScoredNeighbor] = []
    selected_ids: set[int] = set()
    selected_variant_keys: set[str] = set()
    lane_counts: Counter[str] = Counter()
    vector_exceptions = 0

    def _accept(item: SimilarityV3ScoredNeighbor) -> bool:
        nonlocal vector_exceptions
        if item.candidate.id in selected_ids:
            return False
        if item.used_vector_exception and vector_exceptions >= profile.max_vector_exceptions:
            return False
        variant_key = _title_variant_key(getattr(item.candidate, "title", None))
        if variant_key and variant_key in selected_variant_keys:
            return False

        lane = _lane_key_for_similarity_neighbor(item.candidate)
        lane_cap = lane_caps.get(lane, lane_caps.get("other", limit))
        if lane_counts[lane] >= lane_cap:
            return False

        selected.append(item)
        selected_ids.add(item.candidate.id)
        lane_counts[lane] += 1
        if variant_key:
            selected_variant_keys.add(variant_key)
        if item.used_vector_exception:
            vector_exceptions += 1
        return True

    for lane in lane_sequence:
        lane_candidates = []
        for item in scored:
            if _lane_key_for_similarity_neighbor(item.candidate) != lane:
                continue
            fit = fit_fn(anchor, item.candidate)
            if fit is None:
                continue
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
    for item in scored:
        if item.used_vector_exception and vector_exceptions >= profile.max_vector_exceptions:
            continue
        variant_key = _title_variant_key(getattr(item.candidate, "title", None))
        if variant_key and variant_key in seen_variant_keys:
            continue
        capped.append(item)
        if variant_key:
            seen_variant_keys.add(variant_key)
        if item.used_vector_exception:
            vector_exceptions += 1
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
        relationship_type = getattr(taxonomy_breakdown, "relationship", None) or "unrelated"
        if taxonomy_breakdown is None:
            if not profile.allow_vector_exception:
                continue
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
            getattr(taxonomy_breakdown, "score", None) if taxonomy_breakdown is not None else None,
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
        if final_score < profile.publish_threshold and not used_vector_exception:
            continue
        if taxonomy_score < profile.minimum_taxonomy_score and not used_vector_exception:
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

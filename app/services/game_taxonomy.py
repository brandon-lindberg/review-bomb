from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Game, GameSourceTaxonomyLabel


CANONICAL_FACETS = (
    "genres",
    "themes",
    "modes",
    "perspectives",
    "studios",
    "publishers",
)
GAMEPLAY_FACETS = ("genres", "themes", "modes", "perspectives")
SOURCE_NAMES = ("opencritic", "steam", "metacritic")
MAX_STORED_SOURCE_LABEL_LENGTH = 255

_DISPLAY_OVERRIDES = {
    "rpg": "RPG",
    "jrpg": "JRPG",
    "mmo": "MMO",
    "pvp": "PvP",
    "vr": "VR",
    "co-op": "Co-op",
    "action-rpg": "Action RPG",
    "deckbuilder": "Deckbuilder",
    "metroidvania": "Metroidvania",
    "soulslike": "Soulslike",
    "turn-based": "Turn-based",
    "top-down": "Top-down",
    "first-person": "First-person",
    "third-person": "Third-person",
    "side-scrolling": "Side-scrolling",
    "real-time": "Real-time",
}
_TOKEN_SPLIT_RE = re.compile(r"[\/,]")
_WORD_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class SimilarityBreakdown:
    score: int
    confidence: str
    match_reasons: list[str]
    shared_genres: list[str]
    shared_themes: list[str]
    shared_modes: list[str]
    shared_perspectives: list[str]
    shared_studios: list[str]
    shared_publishers: list[str]
    shared_outlets: int
    shared_journalists: int


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent / "data" / filename


@lru_cache(maxsize=1)
def load_taxonomy_mappings() -> dict[str, Any]:
    with _data_path("taxonomy_mappings.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_taxonomy_overrides() -> dict[str, Any]:
    with _data_path("taxonomy_overrides.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_taxonomy_label(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace("&", " and ")
    normalized = normalized.replace("'", "")
    normalized = _WORD_RE.sub(" ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def display_taxonomy_token(value: str) -> str:
    if value in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[value]
    return " ".join(part.capitalize() for part in value.split("-") if part)


def _coerce_named_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "," in text or "/" in text:
            parts = [part.strip() for part in _TOKEN_SPLIT_RE.split(text)]
            return [part for part in parts if part]
        return [text]
    if isinstance(value, dict):
        preferred_keys = (
            "description",
            "name",
            "title",
            "label",
            "value",
            "displayName",
            "slug",
        )
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return [candidate.strip()]
        collected: list[str] = []
        for key in preferred_keys:
            if key in value:
                collected.extend(_coerce_named_values(value.get(key)))
        return collected
    if isinstance(value, (list, tuple, set)):
        collected: list[str] = []
        for item in value:
            collected.extend(_coerce_named_values(item))
        return collected
    return []


def _normalized_dict(data: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        normalized[normalize_taxonomy_label(str(key)).replace(" ", "")] = value
    return normalized


def _extract_from_keys(data: dict[str, Any], *keys: str) -> list[str]:
    lookup = _normalized_dict(data)
    collected: list[str] = []
    for key in keys:
        value = lookup.get(normalize_taxonomy_label(key).replace(" ", ""))
        if value is None:
            continue
        collected.extend(_coerce_named_values(value))
    seen: set[str] = set()
    deduped: list[str] = []
    for item in collected:
        marker = item.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _dedupe_labels(labels: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        cleaned = label.strip()
        if not cleaned:
            continue
        marker = cleaned.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(cleaned)
    return deduped


def extract_steam_source_labels(app_details: dict[str, Any] | None) -> dict[str, list[str]]:
    if not app_details:
        return {}
    source_labels = {
        "genre": _extract_from_keys(app_details, "genres"),
        "category": _extract_from_keys(app_details, "categories"),
        "tag": _extract_from_keys(app_details, "store_tags", "tags"),
        "developer": _extract_from_keys(app_details, "developers"),
        "publisher": _extract_from_keys(app_details, "publishers"),
    }
    return {facet: _dedupe_labels(labels) for facet, labels in source_labels.items() if labels}


def extract_opencritic_source_labels(game_data: dict[str, Any] | None) -> dict[str, list[str]]:
    if not game_data:
        return {}
    source_labels = {
        "genre": _extract_from_keys(game_data, "genres", "genre"),
        "platform": _extract_from_keys(game_data, "platforms", "platform"),
        "developer": _extract_from_keys(game_data, "developers", "developer", "developerName"),
        "publisher": _extract_from_keys(game_data, "publishers", "publisher", "publisherName"),
        "theme": _extract_from_keys(game_data, "tags", "themes", "theme"),
    }
    return {facet: _dedupe_labels(labels) for facet, labels in source_labels.items() if labels}


def extract_metacritic_source_labels(score_data: dict[str, Any] | None) -> dict[str, list[str]]:
    if not score_data:
        return {}
    source_labels = {
        "genre": _dedupe_labels(_coerce_named_values(score_data.get("genres"))),
        "platform": _dedupe_labels(_coerce_named_values(score_data.get("platforms"))),
        "developer": _dedupe_labels(_coerce_named_values(score_data.get("developers"))),
        "publisher": _dedupe_labels(_coerce_named_values(score_data.get("publishers"))),
        "theme": _dedupe_labels(_coerce_named_values(score_data.get("themes"))),
    }
    return {facet: labels for facet, labels in source_labels.items() if labels}


def _canonical_result(**kwargs: list[str]) -> dict[str, list[str]]:
    return {facet: values for facet, values in kwargs.items() if values}


def _heuristic_mapping(raw_facet: str, normalized: str) -> dict[str, list[str]]:
    tokens = set(normalized.split())
    if raw_facet == "developer":
        return _canonical_result(studios=[normalized.replace(" ", "-")])
    if raw_facet == "publisher":
        return _canonical_result(publishers=[normalized.replace(" ", "-")])

    if "action rpg" in normalized or ("action" in tokens and "rpg" in tokens):
        return _canonical_result(genres=["action", "rpg"], themes=["action-rpg"])
    if "role playing" in normalized or "role-playing" in normalized or normalized == "rpg":
        return _canonical_result(genres=["rpg"])
    if "jrpg" in normalized:
        return _canonical_result(genres=["rpg"], themes=["jrpg"])
    if "first person shooter" in normalized or normalized == "fps":
        return _canonical_result(genres=["shooter"], perspectives=["first-person"])
    if "third person shooter" in normalized:
        return _canonical_result(genres=["shooter"], perspectives=["third-person"])
    if "real time strategy" in normalized or normalized == "rts":
        return _canonical_result(genres=["strategy"], themes=["real-time"])
    if "turn based" in normalized:
        return _canonical_result(themes=["turn-based"])
    if "deck" in normalized and "build" in normalized:
        return _canonical_result(themes=["deckbuilder"])
    if "souls" in normalized:
        return _canonical_result(themes=["soulslike"])
    if "metroidvania" in normalized:
        return _canonical_result(genres=["adventure", "platformer"], themes=["metroidvania"])
    if "rogue" in normalized:
        return _canonical_result(themes=["roguelike"])
    if "survival horror" in normalized:
        return _canonical_result(genres=["horror"], themes=["survival"])
    if "city builder" in normalized:
        return _canonical_result(genres=["simulation"], themes=["city-builder"])

    if raw_facet in {"genre", "theme", "tag"}:
        if "action" in tokens:
            return _canonical_result(genres=["action"])
        if "adventure" in tokens:
            return _canonical_result(genres=["adventure"])
        if "strategy" in tokens:
            return _canonical_result(genres=["strategy"])
        if "simulation" in tokens or normalized == "sim":
            return _canonical_result(genres=["simulation"])
        if "shooter" in tokens:
            return _canonical_result(genres=["shooter"])
        if "platformer" in tokens or normalized == "platform":
            return _canonical_result(genres=["platformer"])
        if "puzzle" in tokens:
            return _canonical_result(genres=["puzzle"])
        if "horror" in tokens:
            return _canonical_result(genres=["horror"])
        if "sports" in tokens:
            return _canonical_result(genres=["sports"])
        if "racing" in tokens or "driving" in tokens:
            return _canonical_result(genres=["racing"])
        if "fighting" in tokens:
            return _canonical_result(genres=["fighting"])
        if "rhythm" in tokens:
            return _canonical_result(genres=["rhythm"])
        if "sandbox" in tokens:
            return _canonical_result(genres=["sandbox"])
        if "stealth" in tokens:
            return _canonical_result(genres=["stealth"])
        if "visual" in tokens and "novel" in tokens:
            return _canonical_result(genres=["visual-novel"])
        if "mmo" in tokens or ("massively" in tokens and "multiplayer" in tokens):
            return _canonical_result(genres=["mmo"], modes=["multiplayer"])
        if "open" in tokens and "world" in tokens:
            return _canonical_result(themes=["open-world"])
        if "tactical" in tokens:
            return _canonical_result(genres=["strategy"], themes=["tactical"])
        if "survival" in tokens:
            return _canonical_result(themes=["survival"])

    if raw_facet in {"category", "tag"}:
        if "single" in tokens and "player" in tokens:
            return _canonical_result(modes=["single-player"])
        if "multi" in tokens and "player" in tokens or "multiplayer" in tokens:
            return _canonical_result(modes=["multiplayer"])
        if "co" in tokens and "op" in tokens or "coop" in tokens or "co-op" in normalized:
            return _canonical_result(modes=["co-op"])
        if "pvp" in tokens:
            return _canonical_result(modes=["pvp"])
        if "vr" in tokens:
            return _canonical_result(perspectives=["vr"])

    if raw_facet in {"theme", "perspective", "category", "tag"}:
        if "first" in tokens and "person" in tokens:
            return _canonical_result(perspectives=["first-person"])
        if "third" in tokens and "person" in tokens:
            return _canonical_result(perspectives=["third-person"])
        if "top" in tokens and "down" in tokens:
            return _canonical_result(perspectives=["top-down"])
        if "isometric" in tokens:
            return _canonical_result(perspectives=["isometric"])
        if "side" in tokens and ("scrolling" in tokens or "scroller" in tokens):
            return _canonical_result(perspectives=["side-scrolling"])

    return {}


def map_raw_label_to_canonical(
    source: str,
    raw_facet: str,
    raw_label: str,
) -> dict[str, list[str]]:
    normalized = normalize_taxonomy_label(raw_label)
    if not normalized:
        return {}

    mappings = load_taxonomy_mappings()
    source_map = mappings.get(source, {}).get(raw_facet, {})
    global_map = mappings.get("global", {}).get(raw_facet, {})
    mapped = source_map.get(normalized) or global_map.get(normalized)
    if mapped:
        return {
            facet: sorted({normalize_taxonomy_label(item).replace(" ", "-") for item in values if normalize_taxonomy_label(item)})
            for facet, values in mapped.items()
            if values
        }
    return _heuristic_mapping(raw_facet, normalized)


def _override_keys_for_game(game: Game) -> list[str]:
    keys: list[str] = []
    if getattr(game, "public_id", None):
        keys.append(f"public_id:{game.public_id}")
    if getattr(game, "opencritic_id", None) is not None:
        keys.append(f"opencritic_id:{game.opencritic_id}")
    if getattr(game, "steam_app_id", None) is not None:
        keys.append(f"steam_app_id:{game.steam_app_id}")
    if getattr(game, "metacritic_slug", None):
        keys.append(f"metacritic_slug:{game.metacritic_slug}")
    if getattr(game, "title", None):
        keys.append(f"title:{normalize_taxonomy_label(game.title).replace(' ', '-')}")
    return keys


def get_game_override(game: Game) -> dict[str, Any]:
    config = load_taxonomy_overrides().get("games", {})
    merged_add: dict[str, set[str]] = {facet: set() for facet in CANONICAL_FACETS}
    merged_remove: dict[str, set[str]] = {facet: set() for facet in CANONICAL_FACETS}

    for key in _override_keys_for_game(game):
        override = config.get(key)
        if not override:
            continue
        for facet, values in (override.get("add") or {}).items():
            if facet in merged_add:
                merged_add[facet].update(normalize_taxonomy_label(value).replace(" ", "-") for value in values if normalize_taxonomy_label(value))
        for facet, values in (override.get("remove") or {}).items():
            if facet in merged_remove:
                merged_remove[facet].update(normalize_taxonomy_label(value).replace(" ", "-") for value in values if normalize_taxonomy_label(value))

    add = {facet: sorted(values) for facet, values in merged_add.items() if values}
    remove = {facet: sorted(values) for facet, values in merged_remove.items() if values}
    return {"add": add, "remove": remove}


def game_has_curated_override(game: Game) -> bool:
    override = get_game_override(game)
    return bool(override["add"] or override["remove"])


def game_has_sufficient_taxonomy_support(game: Game) -> bool:
    sources = list(getattr(game, "taxonomy_sources", None) or [])
    return len(sources) >= 2 or game_has_curated_override(game)


async def sync_game_source_taxonomy(
    db: AsyncSession,
    game: Game,
    *,
    source: str,
    source_labels: dict[str, list[str]] | None,
) -> bool:
    if source not in SOURCE_NAMES:
        raise ValueError(f"Unsupported taxonomy source: {source}")
    cleaned_labels = {
        facet: _dedupe_labels(labels)
        for facet, labels in (source_labels or {}).items()
        if labels
    }
    existing_result = await db.execute(
        select(GameSourceTaxonomyLabel).where(
            GameSourceTaxonomyLabel.game_id == game.id,
            GameSourceTaxonomyLabel.source == source,
        )
    )
    existing_rows = existing_result.scalars().all()

    existing_by_facet: dict[str, list[str]] = {}
    for row in existing_rows:
        existing_by_facet.setdefault(row.facet, []).append(row.normalized_label)
    existing_by_facet = {
        facet: sorted(values)
        for facet, values in existing_by_facet.items()
        if values
    }
    incoming_by_facet = {
        facet: sorted(
            {
                normalize_taxonomy_label(label)
                for label in labels
                if normalize_taxonomy_label(label)
            }
        )
        for facet, labels in cleaned_labels.items()
        if labels
    }
    if incoming_by_facet == existing_by_facet:
        return False

    await db.execute(
        delete(GameSourceTaxonomyLabel).where(
            GameSourceTaxonomyLabel.game_id == game.id,
            GameSourceTaxonomyLabel.source == source,
        )
    )

    if not cleaned_labels:
        await rebuild_game_taxonomy(db, game)
        from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty

        mark_game_similarity_v3_dirty(game, f"source_labels_{source}")
        return True

    seen_normalized_by_facet: dict[str, set[str]] = {}
    for facet, labels in cleaned_labels.items():
        seen_normalized = seen_normalized_by_facet.setdefault(facet, set())
        for raw_label in labels:
            cleaned_raw_label = raw_label.strip()
            if not cleaned_raw_label or len(cleaned_raw_label) > MAX_STORED_SOURCE_LABEL_LENGTH:
                continue
            normalized_label = normalize_taxonomy_label(cleaned_raw_label)
            if not normalized_label:
                continue
            if len(normalized_label) > MAX_STORED_SOURCE_LABEL_LENGTH:
                continue
            if normalized_label in seen_normalized:
                continue
            seen_normalized.add(normalized_label)
            db.add(
                GameSourceTaxonomyLabel(
                    game_id=game.id,
                    source=source,
                    facet=facet,
                    raw_label=cleaned_raw_label,
                    normalized_label=normalized_label,
                )
            )

    await rebuild_game_taxonomy(db, game)
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty

    mark_game_similarity_v3_dirty(game, f"source_labels_{source}")
    return True


async def rebuild_game_taxonomy(db: AsyncSession, game: Game) -> None:
    flush = getattr(db, "flush", None)
    if flush is not None:
        await flush()

    result = await db.execute(
        select(GameSourceTaxonomyLabel).where(GameSourceTaxonomyLabel.game_id == game.id)
    )
    rows = result.scalars().all()

    canonical: dict[str, set[str]] = {facet: set() for facet in CANONICAL_FACETS}
    gameplay_sources: set[str] = set()

    for row in rows:
        mapped = map_raw_label_to_canonical(row.source, row.facet, row.raw_label)
        if not mapped:
            continue
        contributed_gameplay = False
        for facet, values in mapped.items():
            if facet not in canonical:
                continue
            canonical[facet].update(values)
            if facet in GAMEPLAY_FACETS and values:
                contributed_gameplay = True
        if contributed_gameplay:
            gameplay_sources.add(row.source)

    override = get_game_override(game)
    for facet, values in override["add"].items():
        canonical.setdefault(facet, set()).update(values)
    for facet, values in override["remove"].items():
        canonical.setdefault(facet, set()).difference_update(values)

    game.taxonomy_genres = sorted(canonical["genres"])
    game.taxonomy_themes = sorted(canonical["themes"])
    game.taxonomy_modes = sorted(canonical["modes"])
    game.taxonomy_perspectives = sorted(canonical["perspectives"])
    game.taxonomy_studios = sorted(canonical["studios"])
    game.taxonomy_publishers = sorted(canonical["publishers"])
    game.taxonomy_sources = sorted(gameplay_sources)
    game.taxonomy_synced_at = datetime.now(timezone.utc)


def build_game_taxonomy_sets(game: Game) -> dict[str, set[str]]:
    return {
        "genres": set(getattr(game, "taxonomy_genres", None) or []),
        "themes": set(getattr(game, "taxonomy_themes", None) or []),
        "modes": set(getattr(game, "taxonomy_modes", None) or []),
        "perspectives": set(getattr(game, "taxonomy_perspectives", None) or []),
        "studios": set(getattr(game, "taxonomy_studios", None) or []),
        "publishers": set(getattr(game, "taxonomy_publishers", None) or []),
    }


def build_similarity_breakdown(
    anchor: Game,
    candidate: Game,
    *,
    shared_outlets: int = 0,
    shared_journalists: int = 0,
) -> SimilarityBreakdown | None:
    if not game_has_sufficient_taxonomy_support(anchor) or not game_has_sufficient_taxonomy_support(candidate):
        return None

    anchor_taxonomy = build_game_taxonomy_sets(anchor)
    candidate_taxonomy = build_game_taxonomy_sets(candidate)

    shared_genres = sorted(anchor_taxonomy["genres"] & candidate_taxonomy["genres"])
    shared_themes = sorted(anchor_taxonomy["themes"] & candidate_taxonomy["themes"])
    shared_modes = sorted(anchor_taxonomy["modes"] & candidate_taxonomy["modes"])
    shared_perspectives = sorted(anchor_taxonomy["perspectives"] & candidate_taxonomy["perspectives"])
    shared_studios = sorted(anchor_taxonomy["studios"] & candidate_taxonomy["studios"])
    shared_publishers = sorted(anchor_taxonomy["publishers"] & candidate_taxonomy["publishers"])

    if not shared_genres:
        return None
    if not (shared_themes or shared_modes or shared_perspectives):
        return None

    score = 0
    score += len(shared_themes) * 100
    score += len(shared_genres) * 60
    score += len(shared_modes) * 24
    score += len(shared_perspectives) * 18
    score += len(shared_studios) * 10
    score += len(shared_publishers) * 6
    score += shared_outlets * 3
    score += shared_journalists * 2

    reasons: list[str] = []
    if shared_themes:
        reasons.append(
            f"Shared themes: {', '.join(display_taxonomy_token(item) for item in shared_themes[:2])}"
        )
    if shared_genres:
        reasons.append(
            f"Shared genres: {', '.join(display_taxonomy_token(item) for item in shared_genres[:2])}"
        )
    if shared_modes:
        reasons.append(
            f"Shared modes: {', '.join(display_taxonomy_token(item) for item in shared_modes[:2])}"
        )
    elif shared_perspectives:
        reasons.append(
            f"Shared perspective: {', '.join(display_taxonomy_token(item) for item in shared_perspectives[:2])}"
        )
    if len(reasons) < 3 and shared_studios:
        reasons.append("Shared studio lineage")
    if len(reasons) < 3 and (shared_outlets or shared_journalists):
        reasons.append("Shared critic network")

    confidence = "high" if score >= 180 else "medium"
    return SimilarityBreakdown(
        score=score,
        confidence=confidence,
        match_reasons=reasons[:3],
        shared_genres=shared_genres,
        shared_themes=shared_themes,
        shared_modes=shared_modes,
        shared_perspectives=shared_perspectives,
        shared_studios=shared_studios,
        shared_publishers=shared_publishers,
        shared_outlets=shared_outlets,
        shared_journalists=shared_journalists,
    )


def raw_label_is_mapped(source: str, facet: str, raw_label: str) -> bool:
    mapped = map_raw_label_to_canonical(source, facet, raw_label)
    return any(mapped.get(key) for key in CANONICAL_FACETS)

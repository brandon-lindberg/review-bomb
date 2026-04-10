"""
Curated Steam-only and early-access catalog support.

Some high-signal Steam titles need to exist in our catalog even when they do
not arrive through the normal OpenCritic-led ingest path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Game
from app.services.steam import SteamService


def _data_path(filename: str) -> Path:
    return Path(__file__).resolve().parent.parent / "data" / filename


def _normalize_title(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _should_update_release_date(
    existing_release_date: date | None,
    candidate_release_date: date | None,
) -> bool:
    if candidate_release_date is None:
        return False
    if existing_release_date is None:
        return True
    if candidate_release_date == existing_release_date:
        return False

    today = datetime.now(timezone.utc).date()

    if existing_release_date > today:
        if candidate_release_date <= today:
            return True
        return candidate_release_date < existing_release_date

    if candidate_release_date > today:
        return False

    if candidate_release_date > existing_release_date:
        return (candidate_release_date - existing_release_date).days >= 120

    return False


@dataclass(frozen=True, slots=True)
class TrackedSteamGame:
    steam_app_id: int
    title: str
    aliases: tuple[str, ...] = ()
    release_date: date | None = None
    reason: str | None = None

    @property
    def title_candidates(self) -> tuple[str, ...]:
        values: list[str] = []
        for item in (self.title, *self.aliases):
            cleaned = (item or "").strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
        return tuple(values)

    @property
    def normalized_title_candidates(self) -> set[str]:
        return {_normalize_title(value) for value in self.title_candidates if value.strip()}


@lru_cache(maxsize=1)
def load_tracked_steam_games() -> tuple[TrackedSteamGame, ...]:
    with _data_path("tracked_steam_games.json").open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    entries: list[TrackedSteamGame] = []
    for raw_entry in payload.get("games", []):
        app_id = raw_entry.get("steam_app_id")
        title = (raw_entry.get("title") or "").strip()
        if not isinstance(app_id, int) or not title:
            continue

        release_date = None
        raw_release_date = raw_entry.get("release_date")
        if isinstance(raw_release_date, str) and raw_release_date.strip():
            release_date = date.fromisoformat(raw_release_date)

        raw_aliases = raw_entry.get("aliases") or []
        aliases = tuple(
            alias.strip()
            for alias in raw_aliases
            if isinstance(alias, str) and alias.strip()
        )

        reason = raw_entry.get("reason")
        entries.append(
            TrackedSteamGame(
                steam_app_id=app_id,
                title=title,
                aliases=aliases,
                release_date=release_date,
                reason=str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
            )
        )

    return tuple(entries)


def _build_catalog_transform(
    tracked_game: TrackedSteamGame,
    app_details: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    fallback_used = app_details is None
    if app_details is None:
        transformed: dict[str, Any] = {
            "steam_app_id": tracked_game.steam_app_id,
            "title": tracked_game.title,
            "description": None,
            "steam_short_description": None,
            "steam_detailed_description": None,
            "release_date": tracked_game.release_date,
            "image_url": None,
        }
    else:
        transformed = SteamService.transform_app_details(app_details, tracked_game.steam_app_id)
        transformed["title"] = tracked_game.title or transformed.get("title")
        if transformed.get("release_date") is None and tracked_game.release_date is not None:
            transformed["release_date"] = tracked_game.release_date

    return transformed, fallback_used


async def _find_existing_game(
    db: AsyncSession,
    tracked_game: TrackedSteamGame,
) -> Game | None:
    existing_by_app = (
        await db.execute(
            select(Game).where(Game.steam_app_id == tracked_game.steam_app_id).limit(1)
        )
    ).scalar_one_or_none()
    if existing_by_app is not None:
        return existing_by_app

    lowered_titles = [value.lower() for value in tracked_game.title_candidates]
    if not lowered_titles:
        return None

    return (
        await db.execute(
            select(Game)
            .where(
                func.lower(Game.title).in_(lowered_titles),
                or_(Game.steam_app_id.is_(None), Game.steam_app_id == tracked_game.steam_app_id),
            )
            .order_by(Game.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _apply_catalog_fields(
    game: Game,
    tracked_game: TrackedSteamGame,
    transformed: dict[str, Any],
) -> bool:
    changed = False
    canonical_title = (tracked_game.title or transformed.get("title") or "").strip()
    current_title = (game.title or "").strip()

    if game.steam_app_id != tracked_game.steam_app_id:
        game.steam_app_id = tracked_game.steam_app_id
        changed = True

    if canonical_title and (
        not current_title
        or _normalize_title(current_title) in tracked_game.normalized_title_candidates
    ) and current_title != canonical_title:
        game.title = canonical_title
        changed = True

    for field_name in ("steam_short_description", "steam_detailed_description"):
        value = transformed.get(field_name)
        if value and getattr(game, field_name) != value:
            setattr(game, field_name, value)
            changed = True

    for field_name in ("description", "image_url"):
        value = transformed.get(field_name)
        if value and not getattr(game, field_name):
            setattr(game, field_name, value)
            changed = True

    candidate_release_date = transformed.get("release_date")
    if _should_update_release_date(game.release_date, candidate_release_date):
        game.release_date = candidate_release_date
        changed = True

    return changed


async def ensure_tracked_steam_games(
    db: AsyncSession,
    steam_service: SteamService,
    tracked_games: Iterable[TrackedSteamGame] | None = None,
) -> dict[str, int]:
    """
    Ensure curated Steam-sourced titles exist in the catalog before Steam sync runs.
    """
    stats = {
        "created": 0,
        "updated": 0,
        "fallback_used": 0,
    }
    changed = False

    for tracked_game in tracked_games or load_tracked_steam_games():
        app_details = await steam_service.get_app_details(tracked_game.steam_app_id)
        transformed, fallback_used = _build_catalog_transform(tracked_game, app_details)
        if fallback_used:
            stats["fallback_used"] += 1

        game = await _find_existing_game(db, tracked_game)
        if game is None:
            game = Game(
                title=tracked_game.title,
                steam_app_id=tracked_game.steam_app_id,
                description=transformed.get("description"),
                steam_short_description=transformed.get("steam_short_description"),
                steam_detailed_description=transformed.get("steam_detailed_description"),
                release_date=transformed.get("release_date"),
                image_url=transformed.get("image_url"),
            )
            db.add(game)
            stats["created"] += 1
            changed = True
            continue

        if _apply_catalog_fields(game, tracked_game, transformed):
            stats["updated"] += 1
            changed = True

    if changed:
        await db.flush()

    return stats

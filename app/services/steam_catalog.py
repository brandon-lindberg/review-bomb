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
    *,
    source_coming_soon: bool = False,
) -> bool:
    if candidate_release_date is None:
        return False
    if existing_release_date is None:
        return True
    if candidate_release_date == existing_release_date:
        return False

    today = datetime.now(timezone.utc).date()

    # Authoritative "still upcoming" signal (Steam coming_soon): if the source
    # confirms the game has not released yet, any past date we hold is a stale
    # announced date and must yield to the real future date. This is the case the
    # anti-regression guard below would otherwise wrongly block (delayed games).
    if source_coming_soon and existing_release_date <= today and candidate_release_date > today:
        return True

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

    # When Steam reports the title as still upcoming, the concrete announced date
    # lives in `announced_release_date` (release_date is None while coming_soon).
    # Prefer it so a delayed game's stale past date is corrected to the real date.
    source_coming_soon = bool(transformed.get("release_coming_soon"))
    candidate_release_date = transformed.get("release_date")
    if source_coming_soon and transformed.get("announced_release_date") is not None:
        candidate_release_date = transformed.get("announced_release_date")
    if _should_update_release_date(
        game.release_date,
        candidate_release_date,
        source_coming_soon=source_coming_soon,
    ):
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


@dataclass(frozen=True, slots=True)
class StaleReleaseDateCorrection:
    game_id: int
    title: str
    steam_app_id: int
    old_release_date: date | None
    new_release_date: date


async def reconcile_stale_release_dates(
    db: AsyncSession,
    steam_service: SteamService,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Repair stale "announced then delayed" release dates across all Steam-linked games.

    Anomaly signature: we hold a release date that is already in the past, yet Steam
    authoritatively still marks the title as ``coming_soon`` (i.e. it has not actually
    released). That past date is necessarily a stale announced date the game slipped
    past; replace it with Steam's current announced (future) date.
    """
    today = datetime.now(timezone.utc).date()

    query = select(Game).where(Game.steam_app_id.isnot(None))
    if limit is not None:
        query = query.limit(limit)

    games = (await db.execute(query)).scalars().all()

    stats = {"scanned": 0, "corrected": 0, "skipped_no_details": 0}
    corrections: list[StaleReleaseDateCorrection] = []

    for game in games:
        stats["scanned"] += 1
        app_details = await steam_service.get_app_details(game.steam_app_id)
        if not app_details:
            stats["skipped_no_details"] += 1
            continue

        transformed = SteamService.transform_app_details(app_details, game.steam_app_id)
        if not transformed.get("release_coming_soon"):
            continue

        announced = transformed.get("announced_release_date")
        # Only act on the clear anomaly: a stale past date while Steam reports the
        # game as still upcoming, with a concrete future date to replace it.
        if (
            announced is None
            or announced <= today
            or game.release_date is None
            or game.release_date > today
            or game.release_date == announced
        ):
            continue

        corrections.append(
            StaleReleaseDateCorrection(
                game_id=game.id,
                title=game.title,
                steam_app_id=game.steam_app_id,
                old_release_date=game.release_date,
                new_release_date=announced,
            )
        )
        if not dry_run:
            game.release_date = announced
        stats["corrected"] += 1

    if corrections and not dry_run:
        await db.flush()

    stats["corrections"] = corrections
    return stats

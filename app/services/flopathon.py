"""
Flopathon player peak service.

Fetches public player-history data from Flopathon's JSON endpoint and derives
the 24-hour peak plus all-time peak metadata for a Steam app.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Game, SteamPlayerRangeSnapshot
from app.services.steam import DEFAULT_HEADERS
from app.services.steam_activity import (
    _parse_datetime_string,
    _parse_int,
    build_observed_24h_player_points,
)


flopathon_rate_limiter = AsyncLimiter(1, 1)


def extract_flopathon_history_points(
    payload: Optional[dict[str, Any]],
    *,
    fetched_at: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    payload = payload or {}

    history = payload.get("history")
    ordered_points: list[dict[str, Any]] = []
    if not isinstance(history, list):
        return ordered_points

    for point in history:
        if not isinstance(point, dict):
            continue
        sampled_at_raw = point.get("timestamp")
        concurrent_players = _parse_int(point.get("players"))
        if sampled_at_raw is None or concurrent_players is None or concurrent_players <= 0:
            continue

        sampled_at = _parse_datetime_string(str(sampled_at_raw), fetched_at=fetched_at)
        if sampled_at is None:
            continue

        ordered_points.append(
            {
                "sampled_at": sampled_at,
                "concurrent_players": concurrent_players,
            }
        )

    ordered_points.sort(key=lambda point: point["sampled_at"])
    return ordered_points


def parse_flopathon_peak_summary(
    payload: Optional[dict[str, Any]],
    *,
    fetched_at: Optional[datetime] = None,
) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    payload = payload or {}

    peak_data = payload.get("peak")
    peak_data = peak_data if isinstance(peak_data, dict) else {}

    all_time_peak = _parse_int(peak_data.get("count"))
    if all_time_peak is not None and all_time_peak <= 0:
        all_time_peak = None
    all_time_peak_at = None
    peak_date = peak_data.get("date")
    if peak_date:
        all_time_peak_at = _parse_datetime_string(str(peak_date), fetched_at=fetched_at)

    ordered_points = extract_flopathon_history_points(payload, fetched_at=fetched_at)

    peak_24h = None
    low_24h = None
    if ordered_points:
        reference_time = ordered_points[-1]["sampled_at"]
        cutoff = reference_time - timedelta(hours=24)
        trailing_points = [
            point["concurrent_players"]
            for point in ordered_points
            if point["sampled_at"] >= cutoff
        ]
        if trailing_points:
            peak_24h = max(trailing_points)
            low_24h = min(trailing_points)

    return {
        "steam_player_24h_peak": peak_24h,
        "steam_player_24h_low_observed": low_24h,
        "steam_player_all_time_peak": all_time_peak,
        "steam_player_all_time_peak_at": all_time_peak_at,
    }


def build_flopathon_range_snapshot_rows(
    game_id: int,
    payload: Optional[dict[str, Any]],
    *,
    fetched_at: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    history_points = extract_flopathon_history_points(payload, fetched_at=fetched_at)
    observed_points = build_observed_24h_player_points(history_points)
    return [
        {
            "game_id": game_id,
            "sampled_at": point["sampled_at"],
            "players_24h_high": point["observed_24h_high"],
            "players_24h_low": point["observed_24h_low"],
        }
        for point in observed_points
    ]


class FlopathonService:
    """Fetch Steam-app peak stats from Flopathon's public JSON endpoint."""

    PLAYERS_URL = "https://flopathon.cc/api/steam?action=players&appid={app_id}"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._blocked = False
        self._warned = False

    async def __aenter__(self) -> "FlopathonService":
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    **DEFAULT_HEADERS,
                    "Referer": "https://flopathon.cc/",
                },
                follow_redirects=True,
            )
        return self._client

    async def get_players_payload(self, app_id: int) -> Optional[dict[str, Any]]:
        if self._blocked:
            return None

        async with flopathon_rate_limiter:
            await asyncio.sleep(1.0)
            try:
                client = await self._get_client()
                response = await client.get(self.PLAYERS_URL.format(app_id=app_id))
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {403, 429}:
                    self._blocked = True
                    if not self._warned:
                        print(
                            f"Flopathon returned {exc.response.status_code}. "
                            "Skipping Flopathon peak fetches for the rest of this run."
                        )
                        self._warned = True
                    return None
                print(f"Error fetching Flopathon peaks for app_id={app_id}: {exc}")
                return None
            except Exception as exc:
                print(f"Error fetching Flopathon peaks for app_id={app_id}: {exc}")
                return None

        if not isinstance(payload, dict):
            return None

        return payload

    async def get_peak_summary(self, app_id: int) -> dict[str, Any]:
        payload = await self.get_players_payload(app_id)
        if payload is None:
            return {}

        return parse_flopathon_peak_summary(payload, fetched_at=datetime.now(timezone.utc))


async def sync_game_flopathon_peaks(
    db: AsyncSession,
    game: Game,
    service: FlopathonService,
    *,
    fetched_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Fetch and denormalize Flopathon-backed 24h range and all-time peak stats."""
    if game.steam_app_id is None:
        return {"peaks_updated": False}

    fetched_at = fetched_at or datetime.now(timezone.utc)
    payload = await service.get_players_payload(game.steam_app_id)
    if payload is None:
        return {"peaks_updated": False, "range_snapshots_upserted": 0}

    peaks = parse_flopathon_peak_summary(payload, fetched_at=fetched_at)
    range_rows = build_flopathon_range_snapshot_rows(
        game.id,
        payload,
        fetched_at=fetched_at,
    )

    peaks_updated = False
    summary_updated = False
    if range_rows:
        stmt = insert(SteamPlayerRangeSnapshot).values(range_rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_steam_player_range_snapshots_game_sampled",
            set_={
                "players_24h_high": stmt.excluded.players_24h_high,
                "players_24h_low": stmt.excluded.players_24h_low,
            },
        )
        await db.execute(stmt)
        peaks_updated = True

    peak_24h = peaks.get("steam_player_24h_peak")
    if peak_24h is not None:
        game.steam_player_24h_peak = peak_24h
        peaks_updated = True
        summary_updated = True

    low_24h = peaks.get("steam_player_24h_low_observed")
    if low_24h is not None:
        game.steam_player_24h_low_observed = low_24h
        peaks_updated = True
        summary_updated = True

    all_time_peak = peaks.get("steam_player_all_time_peak")
    if all_time_peak is not None:
        game.steam_player_all_time_peak = all_time_peak
        peaks_updated = True
        summary_updated = True

    all_time_peak_at = peaks.get("steam_player_all_time_peak_at")
    if all_time_peak_at is not None:
        game.steam_player_all_time_peak_at = all_time_peak_at
        peaks_updated = True
        summary_updated = True

    if peaks_updated:
        if game.steam_player_stats_synced_at is None or fetched_at > game.steam_player_stats_synced_at:
            game.steam_player_stats_synced_at = fetched_at

    return {
        "peaks_updated": peaks_updated,
        "summary_updated": summary_updated,
        "range_snapshots_upserted": len(range_rows),
        "steam_player_24h_peak": peak_24h,
        "steam_player_24h_low_observed": low_24h,
        "steam_player_all_time_peak": all_time_peak,
        "steam_player_all_time_peak_at": all_time_peak_at,
    }

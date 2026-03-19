from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.schemas.schemas import SteamPlayerPoint

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_WINDOW = "1y"


@dataclass(slots=True)
class ScraperSteamActivity:
    points: list[SteamPlayerPoint]
    marker_source_points: list[dict[str, object]]
    summary_updates: dict[str, object]


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def downsample_scraper_points(points: list[SteamPlayerPoint], limit: int) -> list[SteamPlayerPoint]:
    if limit <= 0:
        return []
    if len(points) <= limit:
        return points
    if limit == 1:
        return [points[-1]]

    last_index = len(points) - 1
    selected = [
        points[round(step * last_index / (limit - 1))]
        for step in range(limit)
    ]
    return selected


def build_scraper_activity(payload: dict[str, Any], *, limit: int) -> ScraperSteamActivity | None:
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        return None

    parsed_points: list[SteamPlayerPoint] = []
    for raw_point in raw_points:
        if not isinstance(raw_point, dict):
            continue
        sampled_at = _parse_datetime(raw_point.get("window_ending_at") or raw_point.get("bucket_started_at"))
        observed_24h_high = _coerce_int(raw_point.get("observed_24h_high"))
        observed_24h_low = _coerce_int(raw_point.get("observed_24h_low"))
        latest_players = _coerce_int(raw_point.get("latest_players"))
        if sampled_at is None or observed_24h_high is None or observed_24h_low is None:
            continue
        parsed_points.append(
            SteamPlayerPoint(
                sampled_at=sampled_at,
                observed_24h_high=observed_24h_high,
                observed_24h_low=observed_24h_low,
                latest_players=latest_players if latest_players is not None else observed_24h_high,
            )
        )

    parsed_points.sort(key=lambda point: point.sampled_at)
    visible_points = downsample_scraper_points(parsed_points, limit)

    app_payload = payload.get("app") if isinstance(payload.get("app"), dict) else {}
    latest_24h_high = _coerce_int(app_payload.get("latest_24h_high"))
    latest_24h_low = _coerce_int(app_payload.get("latest_24h_low"))
    all_time_peak = _coerce_int(app_payload.get("all_time_peak_players"))
    all_time_peak_at = _parse_datetime(app_payload.get("all_time_peak_at"))
    last_success_at = _parse_datetime(app_payload.get("last_success_at"))

    summary_updates: dict[str, object] = {}
    if latest_24h_high is not None:
        summary_updates["steam_player_24h_peak"] = latest_24h_high
    elif visible_points:
        summary_updates["steam_player_24h_peak"] = visible_points[-1].observed_24h_high

    if latest_24h_low is not None:
        summary_updates["steam_player_24h_low_observed"] = latest_24h_low
    elif visible_points:
        summary_updates["steam_player_24h_low_observed"] = visible_points[-1].observed_24h_low

    if all_time_peak is not None:
        summary_updates["steam_player_all_time_peak"] = all_time_peak
    if all_time_peak_at is not None:
        summary_updates["steam_player_all_time_peak_at"] = all_time_peak_at

    if last_success_at is not None:
        summary_updates["steam_player_stats_synced_at"] = last_success_at
    elif visible_points:
        summary_updates["steam_player_stats_synced_at"] = visible_points[-1].sampled_at

    marker_source_points = [
        {
            "sampled_at": point.sampled_at,
            "concurrent_players": point.latest_players if point.latest_players is not None else point.observed_24h_high,
        }
        for point in visible_points
    ]

    return ScraperSteamActivity(
        points=visible_points,
        marker_source_points=marker_source_points,
        summary_updates=summary_updates,
    )


class PlayerScraperClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.player_scraper_base_url)

    async def __aenter__(self) -> "PlayerScraperClient":
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
            headers = {"Accept": "application/json"}
            if self.settings.player_scraper_api_token:
                headers["Authorization"] = f"Bearer {self.settings.player_scraper_api_token}"
            self._client = httpx.AsyncClient(
                timeout=self.settings.player_scraper_timeout_seconds,
                headers=headers,
            )
        return self._client

    async def get_steam_activity(self, steam_app_id: int, *, limit: int) -> ScraperSteamActivity | None:
        if not self.is_configured:
            return None

        client = await self._get_client()
        url = (
            f"{self.settings.player_scraper_base_url.rstrip('/')}"
            f"/api/v1/apps/{steam_app_id}/history"
        )

        try:
            response = await client.get(url, params={"window": DEFAULT_HISTORY_WINDOW})
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Player scraper request failed for Steam app %s: %s", steam_app_id, exc)
            return None

        payload = response.json()
        if not isinstance(payload, dict):
            return None
        return build_scraper_activity(payload, limit=limit)

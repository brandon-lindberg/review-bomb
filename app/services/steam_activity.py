"""
Steam activity service.

Fetches public current-player data from Steam, public achievement totals from
Steam store app details, and helper utilities for derived activity datasets.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from html import unescape
from statistics import median
from typing import Any, Optional

import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Game, SteamPlayerSnapshot
from app.services.steam import DEFAULT_HEADERS, SteamService


steam_api_rate_limiter = AsyncLimiter(5, 1)
steamdb_rate_limiter = AsyncLimiter(2, 1)


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    return int(digits)


def _format_players(value: int) -> str:
    return f"{value:,} players"


def filter_transient_zeros(
    points: list[dict[str, Any]],
    *,
    player_key: str = "concurrent_players",
    time_key: str = "sampled_at",
    max_gap: timedelta = timedelta(hours=2),
) -> list[dict[str, Any]]:
    """Remove isolated zero-player readings that indicate server blips, not real drops.

    A zero is considered *transient* (and removed) when both:
      - a non-zero reading exists within ``max_gap`` before it, AND
      - a non-zero reading exists within ``max_gap`` after it.

    Consecutive runs of zeros are evaluated as a group: if the entire run is
    bounded by non-zero neighbours within ``max_gap`` of the run's start/end,
    the whole run is removed.  Sustained zeros (no nearby recovery) are kept.
    """
    if not points:
        return points

    n = len(points)
    keep = [True] * n

    # Identify contiguous runs of zero values
    i = 0
    while i < n:
        if points[i][player_key] == 0:
            run_start = i
            while i < n and points[i][player_key] == 0:
                i += 1
            run_end = i - 1  # inclusive

            # Look for a non-zero neighbour before the run within max_gap
            has_before = False
            if run_start > 0:
                gap_before = points[run_start][time_key] - points[run_start - 1][time_key]
                if gap_before <= max_gap and points[run_start - 1][player_key] > 0:
                    has_before = True

            # Look for a non-zero neighbour after the run within max_gap
            has_after = False
            if run_end < n - 1:
                gap_after = points[run_end + 1][time_key] - points[run_end][time_key]
                if gap_after <= max_gap and points[run_end + 1][player_key] > 0:
                    has_after = True

            # Only remove if BOTH sides have a nearby non-zero neighbour
            if has_before and has_after:
                for j in range(run_start, run_end + 1):
                    keep[j] = False
        else:
            i += 1

    return [p for p, k in zip(points, keep) if k]


def _parse_datetime_string(value: str, *, fetched_at: datetime) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None

    if text.isdigit():
        timestamp = int(text)
        if timestamp < 1_000_000_000:
            return None
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    lower = text.lower()
    relative_match = re.search(
        r"(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago",
        lower,
    )
    if relative_match:
        value_num = int(relative_match.group(1))
        unit = relative_match.group(2)
        if unit.startswith("minute"):
            delta = timedelta(minutes=value_num)
        elif unit.startswith("hour"):
            delta = timedelta(hours=value_num)
        elif unit.startswith("day"):
            delta = timedelta(days=value_num)
        elif unit.startswith("week"):
            delta = timedelta(weeks=value_num)
        elif unit.startswith("month"):
            delta = timedelta(days=value_num * 30)
        else:
            delta = timedelta(days=value_num * 365)
        return fetched_at - delta

    date_formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %b, %Y",
        "%d %B, %Y",
        "%b %d %Y",
    ]
    normalized = text.replace("UTC", "+0000").replace("Z", "+0000")
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def extract_achievement_count(app_details: Optional[dict[str, Any]]) -> Optional[int]:
    if not app_details:
        return None
    achievements = app_details.get("achievements")
    if not isinstance(achievements, dict):
        return None
    return _parse_int(achievements.get("total"))


def parse_steamdb_peak_summary(html: str, *, fetched_at: Optional[datetime] = None) -> dict[str, Any]:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    raw_html = unescape(html or "")
    raw_html = raw_html.replace("\xa0", " ")
    raw_html = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", raw_html)
    plain_text = re.sub(r"<[^>]+>", "\n", raw_html)
    plain_text = re.sub(r"[^\S\n]+", " ", plain_text)
    plain_text = re.sub(r"\n+", "\n", plain_text).strip()
    flat_text = re.sub(r"\s+", " ", plain_text).strip()

    steam_block_match = re.search(
        r"Steam charts(.*?)(?:Store data|Twitch stats|Owner estimations|Monthly players breakdown|How many players are playing|Embed Steam charts|$)",
        flat_text,
        flags=re.IGNORECASE,
    )
    steam_block = steam_block_match.group(1).strip() if steam_block_match else flat_text

    def find_value(label: str, text: str) -> Optional[int]:
        patterns = [
            rf"([\d,]+)\s+{re.escape(label)}\b",
            rf"{re.escape(label)}\s+([\d,]+)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return _parse_int(match.group(1))
        return None

    peak_24h = find_value("24-hour peak", steam_block) or find_value("24 hour peak", steam_block)
    all_time_peak = find_value("all-time peak", steam_block) or find_value("all time peak", steam_block)

    all_time_peak_at: Optional[datetime] = None
    label_match = re.search(r"all-time peak|all time peak", steam_block, flags=re.IGNORECASE)
    if label_match:
        segment = steam_block[label_match.start():label_match.start() + 400]
        candidates = []
        candidates.extend(re.findall(r'(?:datetime|title|data-time|data-timestamp|data-sort)="([^"]+)"', segment, flags=re.IGNORECASE))
        candidates.extend(re.findall(r">(today|yesterday|\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago)<", segment, flags=re.IGNORECASE))
        candidates.extend(re.findall(r"\b(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?)?)\b", segment))
        candidates.extend(re.findall(r"\b([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\b", segment))
        candidates.extend(re.findall(r"\b(\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})\b", segment))
        candidates.extend(re.findall(r"\b([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b", segment))
        candidates.extend(re.findall(r"\b(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})\b", segment))
        for candidate in candidates:
            parsed = _parse_datetime_string(candidate, fetched_at=fetched_at)
            if parsed is not None:
                all_time_peak_at = parsed
                break

    if all_time_peak_at is None:
        relative_match = re.search(
            r"all-time peak(?:\s+[\d,]+)?\s+(today|yesterday|\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago)",
            steam_block,
            flags=re.IGNORECASE,
        )
        if relative_match:
            all_time_peak_at = _parse_datetime_string(relative_match.group(1), fetched_at=fetched_at)

    faq_match = re.search(
        r"had an all-time peak of\s+([\d,]+)\s+concurrent players on\s+([^.]+)\.",
        flat_text,
        flags=re.IGNORECASE,
    )
    if all_time_peak is None and faq_match:
        all_time_peak = _parse_int(faq_match.group(1))
    if all_time_peak_at is None and faq_match:
        all_time_peak_at = _parse_datetime_string(faq_match.group(2), fetched_at=fetched_at)

    return {
        "steam_player_24h_peak": peak_24h,
        "steam_player_all_time_peak": all_time_peak,
        "steam_player_all_time_peak_at": all_time_peak_at,
    }


def build_steam_activity_markers(
    points: list[dict[str, Any]],
    *,
    all_time_peak: Optional[int] = None,
    all_time_peak_at: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    if not points and (all_time_peak is None or all_time_peak_at is None):
        return []

    ordered_points = sorted(points, key=lambda point: point["sampled_at"])
    ordered_points = filter_transient_zeros(ordered_points)
    markers: list[dict[str, Any]] = []

    if ordered_points:
        first = ordered_points[0]
        markers.append(
            {
                "marker_type": "first_tracked",
                "sampled_at": first["sampled_at"],
                "concurrent_players": first["concurrent_players"],
                "label": "First Steam Activity Sample",
                "detail": f"Started tracking at {_format_players(first['concurrent_players'])}.",
            }
        )

    if all_time_peak is not None and all_time_peak_at is not None:
        markers.append(
            {
                "marker_type": "all_time_peak",
                "sampled_at": all_time_peak_at,
                "concurrent_players": all_time_peak,
                "label": "All-Time Peak",
                "detail": f"All-time peak reached {_format_players(all_time_peak)}.",
            }
        )

    last_dynamic_marker_at: Optional[datetime] = None
    last_drop_point: Optional[dict[str, Any]] = None
    window = timedelta(days=7)
    cooldown = timedelta(hours=48)

    for index, point in enumerate(ordered_points):
        point_time = point["sampled_at"]
        baseline_values = [
            candidate["concurrent_players"]
            for candidate in ordered_points[:index]
            if point_time - candidate["sampled_at"] <= window
        ]
        if len(baseline_values) < 2:
            continue

        baseline = float(median(baseline_values))
        if baseline <= 0:
            continue

        player_count = point["concurrent_players"]
        diff = player_count - baseline
        pct = diff / baseline

        if last_dynamic_marker_at is not None and point_time - last_dynamic_marker_at < cooldown:
            if last_drop_point is not None and point_time - last_drop_point["sampled_at"] > window:
                last_drop_point = None
            continue

        if diff >= 5_000 and pct >= 0.30:
            markers.append(
                {
                    "marker_type": "major_surge",
                    "sampled_at": point_time,
                    "concurrent_players": player_count,
                    "label": "Major Player Surge",
                    "detail": f"{_format_players(player_count)} was {diff:,.0f} above the prior 7-day median.",
                }
            )
            last_dynamic_marker_at = point_time
            continue

        if diff <= -5_000 and abs(pct) >= 0.30:
            markers.append(
                {
                    "marker_type": "major_drop",
                    "sampled_at": point_time,
                    "concurrent_players": player_count,
                    "label": "Major Player Drop",
                    "detail": f"{_format_players(player_count)} was {abs(diff):,.0f} below the prior 7-day median.",
                }
            )
            last_dynamic_marker_at = point_time
            last_drop_point = point
            continue

        if last_drop_point is not None and point_time > last_drop_point["sampled_at"]:
            rebound_diff = player_count - last_drop_point["concurrent_players"]
            rebound_pct = (
                rebound_diff / last_drop_point["concurrent_players"]
                if last_drop_point["concurrent_players"] > 0
                else 0
            )
            if rebound_diff >= 5_000 and rebound_pct >= 0.30:
                markers.append(
                    {
                        "marker_type": "rebound",
                        "sampled_at": point_time,
                        "concurrent_players": player_count,
                        "label": "Player Rebound",
                        "detail": f"Recovered by {rebound_diff:,.0f} players from the recent drop.",
                    }
                )
                last_dynamic_marker_at = point_time
                last_drop_point = None

        if last_drop_point is not None and point_time - last_drop_point["sampled_at"] > window:
            last_drop_point = None

    markers.sort(key=lambda marker: marker["sampled_at"])
    return markers


def build_observed_24h_player_points(
    points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build rolling observed 24-hour high/low points from sampled player data."""
    if not points:
        return []

    ordered_points = sorted(points, key=lambda point: point["sampled_at"])
    ordered_points = filter_transient_zeros(ordered_points)
    if not ordered_points:
        return []

    window = timedelta(hours=24)
    values = [point["concurrent_players"] for point in ordered_points]
    times = [point["sampled_at"] for point in ordered_points]

    high_window: deque[int] = deque()
    low_window: deque[int] = deque()
    left = 0
    series: list[dict[str, Any]] = []

    for index, (point_time, player_count) in enumerate(zip(times, values)):
        while left < index and times[left] < point_time - window:
            if high_window and high_window[0] == left:
                high_window.popleft()
            if low_window and low_window[0] == left:
                low_window.popleft()
            left += 1

        while high_window and values[high_window[-1]] <= player_count:
            high_window.pop()
        high_window.append(index)

        while low_window and values[low_window[-1]] >= player_count:
            low_window.pop()
        low_window.append(index)

        if point_time - times[left] < window:
            continue

        series.append(
            {
                "sampled_at": point_time,
                "observed_24h_high": values[high_window[0]],
                "observed_24h_low": values[low_window[0]],
                "latest_players": player_count,
            }
        )

    return series


class SteamActivityService:
    """Fetch Steam activity stats from public Steam and SteamDB endpoints."""

    STEAM_CURRENT_PLAYERS_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
    STEAMDB_CHARTS_URL = "https://steamdb.info/app/{app_id}/charts/"

    def __init__(self):
        self.steam_service = SteamService()
        self._client: Optional[httpx.AsyncClient] = None
        self._steamdb_blocked = False
        self._steamdb_warned = False

    async def __aenter__(self) -> "SteamActivityService":
        await self._get_client()
        await self.steam_service.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
        await self.steam_service.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    **DEFAULT_HEADERS,
                    "Referer": "https://steamdb.info/",
                },
                follow_redirects=True,
            )
        return self._client

    async def get_current_players(self, app_id: int) -> Optional[int]:
        async with steam_api_rate_limiter:
            await asyncio.sleep(0.2)
            try:
                client = await self._get_client()
                response = await client.get(
                    self.STEAM_CURRENT_PLAYERS_URL,
                    params={"appid": str(app_id)},
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                print(f"Error fetching Steam current players for app_id={app_id}: {exc}")
                return None

        return _parse_int(payload.get("response", {}).get("player_count"))

    async def get_achievement_count(self, app_id: int) -> Optional[int]:
        app_details = await self.steam_service.get_app_details(app_id)
        return extract_achievement_count(app_details)

    async def get_steamdb_peak_summary(self, app_id: int) -> dict[str, Any]:
        if self._steamdb_blocked:
            return {}

        async with steamdb_rate_limiter:
            await asyncio.sleep(0.4)
            try:
                client = await self._get_client()
                response = await client.get(self.STEAMDB_CHARTS_URL.format(app_id=app_id))
                response.raise_for_status()
                html = response.text
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    self._steamdb_blocked = True
                    if not self._steamdb_warned:
                        print(
                            "SteamDB returned 403 Forbidden. "
                            "Skipping SteamDB peak fetches for the rest of this run; "
                            "Steam current players and achievement counts will still sync."
                        )
                        self._steamdb_warned = True
                    return {}
                print(f"Error fetching SteamDB peaks for app_id={app_id}: {exc}")
                return {}
            except Exception as exc:
                print(f"Error fetching SteamDB peaks for app_id={app_id}: {exc}")
                return {}

        return parse_steamdb_peak_summary(html, fetched_at=datetime.now(timezone.utc))


async def sync_game_steam_public_activity(
    db: AsyncSession,
    game: Game,
    service: SteamActivityService,
    *,
    sampled_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Fetch, persist, and denormalize Steam-owned activity stats for one game."""
    if game.steam_app_id is None:
        return {
            "snapshot_created": False,
            "achievement_updated": False,
            "current_players": None,
        }

    sampled_at = sampled_at or datetime.now(timezone.utc)
    current_players = await service.get_current_players(game.steam_app_id)
    achievement_count = await service.get_achievement_count(game.steam_app_id)

    snapshot_created = False
    achievement_updated = False
    player_stats_updated = False

    if current_players is not None:
        db.add(
            SteamPlayerSnapshot(
                game_id=game.id,
                sampled_at=sampled_at,
                concurrent_players=current_players,
            )
        )
        await db.flush()
        snapshot_created = True
        player_stats_updated = True
        game.steam_current_players = current_players
        game.steam_current_players_sampled_at = sampled_at

    if achievement_count is not None:
        achievement_updated = True
        game.steam_achievement_count = achievement_count
        game.steam_achievement_count_synced_at = sampled_at

    if player_stats_updated:
        game.steam_player_stats_synced_at = sampled_at

    return {
        "snapshot_created": snapshot_created,
        "achievement_updated": achievement_updated,
        "current_players": current_players,
    }


async def sync_game_steamdb_peaks(
    game: Game,
    service: SteamActivityService,
    *,
    fetched_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Fetch and denormalize SteamDB-only peak stats for one game."""
    if game.steam_app_id is None:
        return {"peaks_updated": False}

    fetched_at = fetched_at or datetime.now(timezone.utc)
    peaks = await service.get_steamdb_peak_summary(game.steam_app_id)

    peaks_updated = False

    peak_24h = peaks.get("steam_player_24h_peak")
    if peak_24h is not None:
        game.steam_player_24h_peak = peak_24h
        peaks_updated = True

    all_time_peak = peaks.get("steam_player_all_time_peak")
    if all_time_peak is not None:
        game.steam_player_all_time_peak = all_time_peak
        peaks_updated = True

    all_time_peak_at = peaks.get("steam_player_all_time_peak_at")
    if all_time_peak_at is not None:
        game.steam_player_all_time_peak_at = all_time_peak_at
        peaks_updated = True

    if peaks_updated:
        if game.steam_player_stats_synced_at is None or fetched_at > game.steam_player_stats_synced_at:
            game.steam_player_stats_synced_at = fetched_at

    return {
        "peaks_updated": peaks_updated,
        "steam_player_24h_peak": peak_24h,
        "steam_player_all_time_peak": all_time_peak,
        "steam_player_all_time_peak_at": all_time_peak_at,
    }

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.models import SteamPlayerSnapshot
from app.services.player_scraper import (
    build_scraper_activity,
    downsample_scraper_points,
    sync_scraper_activity_to_db,
)
from app.schemas.schemas import SteamPlayerPoint


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


def test_downsample_scraper_points_preserves_range():
    points = [
        SteamPlayerPoint(sampled_at=_utc(2026, 3, 1, hour), observed_24h_high=hour * 10, observed_24h_low=hour * 5)
        for hour in range(6)
    ]

    visible = downsample_scraper_points(points, limit=3)

    assert visible == [points[0], points[2], points[5]]


def test_build_scraper_activity_normalizes_payload_and_summary_updates():
    payload = {
        "app": {
            "latest_24h_high": 8888,
            "latest_24h_low": 2222,
            "last_success_at": "2026-03-19T12:00:00Z",
        },
        "points": [
            {
                "bucket_started_at": "2026-03-18T10:00:00Z",
                "window_ending_at": "2026-03-18T10:59:00Z",
                "observed_24h_high": 5000,
                "observed_24h_low": 2200,
            },
            {
                "bucket_started_at": "2026-03-19T10:00:00Z",
                "window_ending_at": "2026-03-19T10:59:00Z",
                "observed_24h_high": 7000,
                "observed_24h_low": 3200,
            },
            {
                "bucket_started_at": "2026-03-20T10:00:00Z",
                "window_ending_at": "2026-03-20T10:59:00Z",
                "observed_24h_high": 9000,
                "observed_24h_low": 4200,
            },
        ],
    }

    activity = build_scraper_activity(payload, limit=2)

    assert activity is not None
    assert activity.points == [
        SteamPlayerPoint(
            sampled_at=_utc(2026, 3, 19, 10).replace(minute=59),
            observed_24h_high=7000,
            observed_24h_low=3200,
            latest_players=7000,
        ),
        SteamPlayerPoint(
            sampled_at=_utc(2026, 3, 20, 10).replace(minute=59),
            observed_24h_high=9000,
            observed_24h_low=4200,
            latest_players=9000,
        ),
    ]
    assert activity.storage_points == [
        SteamPlayerPoint(
            sampled_at=_utc(2026, 3, 19, 10).replace(minute=59),
            observed_24h_high=7000,
            observed_24h_low=3200,
            latest_players=7000,
        ),
        SteamPlayerPoint(
            sampled_at=_utc(2026, 3, 20, 10).replace(minute=59),
            observed_24h_high=9000,
            observed_24h_low=4200,
            latest_players=9000,
        ),
    ]
    assert activity.marker_source_points == [
        {
            "sampled_at": _utc(2026, 3, 19, 10).replace(minute=59),
            "concurrent_players": 7000,
        },
        {
            "sampled_at": _utc(2026, 3, 20, 10).replace(minute=59),
            "concurrent_players": 9000,
        },
    ]
    assert activity.summary_updates == {
        "steam_player_24h_peak": 8888,
        "steam_player_24h_low_observed": 2222,
        "steam_player_stats_synced_at": _utc(2026, 3, 19, 12),
    }


def test_build_scraper_activity_drops_points_before_tracking_start():
    payload = {
        "app": {
            "latest_24h_high": 9000,
            "latest_24h_low": 3000,
            "last_success_at": "2026-03-20T12:00:00Z",
        },
        "points": [
            {
                "window_ending_at": "2025-12-19T10:00:00Z",
                "observed_24h_high": 450000,
                "observed_24h_low": 300000,
                "latest_players": 320000,
            },
            {
                "window_ending_at": "2026-03-18T23:59:59Z",
                "observed_24h_high": 12000,
                "observed_24h_low": 4000,
                "latest_players": 5000,
            },
            {
                "window_ending_at": "2026-03-19T00:00:00Z",
                "observed_24h_high": 7000,
                "observed_24h_low": 3000,
                "latest_players": 4500,
            },
            {
                "window_ending_at": "2026-03-20T10:00:00Z",
                "observed_24h_high": 9000,
                "observed_24h_low": 3500,
                "latest_players": 6000,
            },
        ],
    }

    activity = build_scraper_activity(payload, limit=100)

    assert activity is not None
    assert [point.sampled_at for point in activity.storage_points] == [
        _utc(2026, 3, 19),
        _utc(2026, 3, 20, 10),
    ]
    assert [point.sampled_at for point in activity.points] == [
        _utc(2026, 3, 19),
        _utc(2026, 3, 20, 10),
    ]
    assert [point["sampled_at"] for point in activity.marker_source_points] == [
        _utc(2026, 3, 19),
        _utc(2026, 3, 20, 10),
    ]


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeAsyncSession:
    def __init__(self, results):
        self.results = list(results)
        self.executed = []
        self.added = []

    async def execute(self, statement):
        self.executed.append(statement)
        if self.results:
            return self.results.pop(0)
        return _FakeScalarResult([])

    def add_all(self, items):
        self.added.extend(items)


@pytest.mark.asyncio
async def test_sync_scraper_activity_to_db_mirrors_scraper_history():
    payload = {
        "app": {
            "latest_24h_high": 641,
            "latest_24h_low": 282,
            "all_time_peak_players": 641,
            "all_time_peak_at": "2026-03-19T10:04:00Z",
            "last_success_at": "2026-03-19T10:04:00Z",
        },
        "points": [
            {
                "window_ending_at": "2026-03-19T08:18:00Z",
                "observed_24h_high": 579,
                "observed_24h_low": 282,
                "latest_players": 308,
            },
            {
                "window_ending_at": "2026-03-19T10:04:00Z",
                "observed_24h_high": 641,
                "observed_24h_low": 282,
                "latest_players": 308,
            },
        ],
    }
    activity = build_scraper_activity(payload, limit=100)

    game = SimpleNamespace(
        id=99,
        steam_current_players=None,
        steam_current_players_sampled_at=None,
        steam_player_24h_peak=None,
        steam_player_24h_low_observed=None,
        steam_player_all_time_peak=None,
        steam_player_all_time_peak_at=None,
        steam_player_stats_synced_at=None,
    )
    session = _FakeAsyncSession([
        _FakeScalarResult([]),
    ])

    result = await sync_scraper_activity_to_db(session, game, activity)

    assert result == {
        "range_snapshots_upserted": 2,
        "player_snapshots_inserted": 2,
        "summary_updated": True,
    }
    assert len(session.executed) == 2
    assert len(session.added) == 2
    assert all(isinstance(snapshot, SteamPlayerSnapshot) for snapshot in session.added)
    assert game.steam_current_players == 308
    assert game.steam_current_players_sampled_at == _utc(2026, 3, 19, 10).replace(minute=4)
    assert game.steam_player_24h_peak == 641
    assert game.steam_player_24h_low_observed == 282
    assert game.steam_player_all_time_peak == 641
    assert game.steam_player_all_time_peak_at == _utc(2026, 3, 19, 10).replace(minute=4)
    assert game.steam_player_stats_synced_at == _utc(2026, 3, 19, 10).replace(minute=4)

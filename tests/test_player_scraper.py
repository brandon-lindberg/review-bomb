from datetime import datetime, timezone

from app.services.player_scraper import build_scraper_activity, downsample_scraper_points
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
            sampled_at=_utc(2026, 3, 18, 10).replace(minute=59),
            observed_24h_high=5000,
            observed_24h_low=2200,
            latest_players=5000,
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
            "sampled_at": _utc(2026, 3, 18, 10).replace(minute=59),
            "concurrent_players": 5000,
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

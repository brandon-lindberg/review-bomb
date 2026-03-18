from datetime import datetime, timezone

from app.services.flopathon import (
    build_flopathon_range_snapshot_rows,
    parse_flopathon_peak_summary,
)


def _utc(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


def test_parse_flopathon_peak_summary_derives_24h_peak_and_all_time_peak():
    payload = {
        "history": [
            {"timestamp": int(_utc(2026, 3, 15, 9).timestamp() * 1000), "players": 41000},
            {"timestamp": int(_utc(2026, 3, 16, 10).timestamp() * 1000), "players": 56520},
            {"timestamp": int(_utc(2026, 3, 17, 8).timestamp() * 1000), "players": 49021},
        ],
        "peak": {
            "count": 77358,
            "date": "Mar 8, 2026",
        },
    }

    parsed = parse_flopathon_peak_summary(payload, fetched_at=_utc(2026, 3, 17, 9))

    assert parsed["steam_player_24h_peak"] == 56520
    assert parsed["steam_player_24h_low_observed"] == 49021
    assert parsed["steam_player_all_time_peak"] == 77358
    assert parsed["steam_player_all_time_peak_at"] == _utc(2026, 3, 8, 0)


def test_parse_flopathon_peak_summary_does_not_fallback_to_current_players():
    payload = {
        "currentPlayers": 49021,
        "peak": {
            "count": 77358,
            "date": "Mar 8, 2026",
        },
    }

    parsed = parse_flopathon_peak_summary(payload, fetched_at=_utc(2026, 3, 17, 9))

    assert parsed["steam_player_24h_peak"] is None
    assert parsed["steam_player_24h_low_observed"] is None
    assert parsed["steam_player_all_time_peak"] == 77358
    assert parsed["steam_player_all_time_peak_at"] == _utc(2026, 3, 8, 0)


def test_parse_flopathon_peak_summary_treats_zero_peaks_as_missing():
    payload = {
        "history": [
            {"timestamp": int(_utc(2026, 3, 17, 8).timestamp() * 1000), "players": 0},
        ],
        "peak": {
            "count": 0,
            "date": "Mar 17, 2026",
        },
    }

    parsed = parse_flopathon_peak_summary(payload, fetched_at=_utc(2026, 3, 17, 9))

    assert parsed["steam_player_24h_peak"] is None
    assert parsed["steam_player_24h_low_observed"] is None
    assert parsed["steam_player_all_time_peak"] is None


def test_build_flopathon_range_snapshot_rows_returns_rolling_high_low_series():
    payload = {
        "history": [
            {"timestamp": int(_utc(2026, 3, 9, 0).timestamp() * 1000), "players": 20000},
            {"timestamp": int(_utc(2026, 3, 9, 12).timestamp() * 1000), "players": 27000},
            {"timestamp": int(_utc(2026, 3, 10, 0).timestamp() * 1000), "players": 55000},
        ]
    }

    rows = build_flopathon_range_snapshot_rows(11, payload, fetched_at=_utc(2026, 3, 10, 1))

    assert rows == [
        {
            "game_id": 11,
            "sampled_at": _utc(2026, 3, 10, 0),
            "players_24h_high": 55000,
            "players_24h_low": 20000,
        }
    ]

from datetime import datetime, timezone

from app.services.steam_activity import (
    build_observed_24h_player_points,
    build_steam_activity_markers,
    extract_achievement_count,
    parse_steamdb_peak_summary,
)


def _utc(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


def test_extract_achievement_count_from_app_details():
    app_details = {
        "name": "Example Game",
        "achievements": {"total": 58},
    }

    assert extract_achievement_count(app_details) == 58


def test_parse_steamdb_peak_summary_handles_relative_all_time_text():
    fetched_at = _utc(2026, 3, 16, 9)
    html = """
        <div class="header-thing-number">62,830</div>
        <div class="header-thing-label">24-hour peak</div>
        <div class="header-thing-number">88,337</div>
        <div class="header-thing-label">all-time peak 10 days ago</div>
    """

    parsed = parse_steamdb_peak_summary(html, fetched_at=fetched_at)

    assert parsed["steam_player_24h_peak"] == 62830
    assert parsed["steam_player_all_time_peak"] == 88337
    assert parsed["steam_player_all_time_peak_at"] == _utc(2026, 3, 6, 9)


def test_parse_steamdb_peak_summary_handles_live_steam_charts_copy():
    html = """
        <h2>Steam charts</h2>
        <p>Peak concurrent players yesterday on Steam.</p>
        <ul>
            <li>51 24-hour peak</li>
            <li>45,049 all-time peak 9 May 2018</li>
        </ul>
        <p>Oddworld: Abe's Oddysee had an all-time peak of 45049 concurrent players on 9 May 2018.</p>
    """

    parsed = parse_steamdb_peak_summary(html, fetched_at=_utc(2026, 3, 16, 9))

    assert parsed["steam_player_24h_peak"] == 51
    assert parsed["steam_player_all_time_peak"] == 45049
    assert parsed["steam_player_all_time_peak_at"] == _utc(2018, 5, 9, 0)


def test_parse_steamdb_peak_summary_falls_back_to_faq_sentence():
    html = """
        <p>Store data blah blah</p>
        <p>Slay the Spire II had an all-time peak of 125,678 concurrent players on 8 March 2026.</p>
    """

    parsed = parse_steamdb_peak_summary(html, fetched_at=_utc(2026, 3, 16, 9))

    assert parsed["steam_player_24h_peak"] is None
    assert parsed["steam_player_all_time_peak"] == 125678
    assert parsed["steam_player_all_time_peak_at"] == _utc(2026, 3, 8, 0)


def test_build_steam_activity_markers_creates_first_tracked_peak_and_surge():
    points = [
        {"sampled_at": _utc(2026, 3, 1), "concurrent_players": 10000},
        {"sampled_at": _utc(2026, 3, 2), "concurrent_players": 11000},
        {"sampled_at": _utc(2026, 3, 3), "concurrent_players": 12000},
        {"sampled_at": _utc(2026, 3, 4), "concurrent_players": 12500},
        {"sampled_at": _utc(2026, 3, 5), "concurrent_players": 13000},
        {"sampled_at": _utc(2026, 3, 6), "concurrent_players": 13500},
        {"sampled_at": _utc(2026, 3, 7), "concurrent_players": 20000},
    ]

    markers = build_steam_activity_markers(
        points,
        all_time_peak=88337,
        all_time_peak_at=_utc(2026, 3, 6),
    )

    marker_types = [marker["marker_type"] for marker in markers]
    assert "first_tracked" in marker_types
    assert "all_time_peak" in marker_types
    assert "major_surge" in marker_types


def test_build_steam_activity_markers_creates_drop_and_rebound():
    points = [
        {"sampled_at": _utc(2026, 3, 1), "concurrent_players": 40000},
        {"sampled_at": _utc(2026, 3, 2), "concurrent_players": 41000},
        {"sampled_at": _utc(2026, 3, 3), "concurrent_players": 42000},
        {"sampled_at": _utc(2026, 3, 4), "concurrent_players": 43000},
        {"sampled_at": _utc(2026, 3, 5), "concurrent_players": 44000},
        {"sampled_at": _utc(2026, 3, 6), "concurrent_players": 45000},
        {"sampled_at": _utc(2026, 3, 9), "concurrent_players": 25000},
        {"sampled_at": _utc(2026, 3, 12), "concurrent_players": 38000},
    ]

    markers = build_steam_activity_markers(points)
    marker_types = [marker["marker_type"] for marker in markers]

    assert "major_drop" in marker_types
    assert "rebound" in marker_types


def test_build_observed_24h_player_points_returns_rolling_highs_and_lows():
    points = [
        {"sampled_at": datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc), "concurrent_players": 20000},
        {"sampled_at": datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc), "concurrent_players": 27000},
        {"sampled_at": datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc), "concurrent_players": 55000},
    ]

    observed = build_observed_24h_player_points(points)

    assert [point["observed_24h_high"] for point in observed] == [55000]
    assert [point["observed_24h_low"] for point in observed] == [20000]

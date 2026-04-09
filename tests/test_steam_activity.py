from datetime import datetime, timezone

from app.services.steam_activity import (
    build_observed_24h_player_points,
    build_steam_activity_markers,
    extract_achievement_count,
    filter_transient_zeros,
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


def _utc_hour(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


# ── filter_transient_zeros tests ──────────────────────────────────────


def test_filter_transient_zeros_removes_single_isolated_zero():
    """A lone zero sandwiched between healthy readings within 2h is removed."""
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, 10), "concurrent_players": 5000},
        {"sampled_at": _utc_hour(2026, 3, 9, 11), "concurrent_players": 0},
        {"sampled_at": _utc_hour(2026, 3, 9, 12), "concurrent_players": 4800},
    ]
    result = filter_transient_zeros(points)
    assert len(result) == 2
    assert all(p["concurrent_players"] > 0 for p in result)


def test_filter_transient_zeros_removes_short_consecutive_run():
    """Two consecutive zeros bounded by healthy readings are removed."""
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, 10), "concurrent_players": 5000},
        {"sampled_at": _utc_hour(2026, 3, 9, 11), "concurrent_players": 0},
        {"sampled_at": _utc_hour(2026, 3, 9, 12), "concurrent_players": 0},
        {"sampled_at": _utc_hour(2026, 3, 9, 13), "concurrent_players": 4800},
    ]
    result = filter_transient_zeros(points)
    assert len(result) == 2
    assert all(p["concurrent_players"] > 0 for p in result)


def test_filter_transient_zeros_keeps_sustained_zero_no_recovery():
    """Zero at the end with no recovery neighbour after is kept (game died)."""
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, 10), "concurrent_players": 5000},
        {"sampled_at": _utc_hour(2026, 3, 9, 11), "concurrent_players": 0},
    ]
    result = filter_transient_zeros(points)
    assert len(result) == 2


def test_filter_transient_zeros_keeps_zero_with_distant_neighbour():
    """Zero kept when the next non-zero reading is more than 2h away."""
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, 10), "concurrent_players": 5000},
        {"sampled_at": _utc_hour(2026, 3, 9, 11), "concurrent_players": 0},
        {"sampled_at": _utc_hour(2026, 3, 9, 14), "concurrent_players": 4800},
    ]
    result = filter_transient_zeros(points)
    # After neighbour is >2h away, so the zero is kept
    assert len(result) == 3


def test_filter_transient_zeros_keeps_zero_at_start():
    """Zero at the start with no prior neighbour is kept."""
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, 10), "concurrent_players": 0},
        {"sampled_at": _utc_hour(2026, 3, 9, 11), "concurrent_players": 5000},
    ]
    result = filter_transient_zeros(points)
    assert len(result) == 2


def test_filter_transient_zeros_no_zeros_unchanged():
    """Points with no zeros pass through unchanged."""
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, 10), "concurrent_players": 5000},
        {"sampled_at": _utc_hour(2026, 3, 9, 11), "concurrent_players": 6000},
    ]
    result = filter_transient_zeros(points)
    assert result == points


def test_filter_transient_zeros_empty_input():
    assert filter_transient_zeros([]) == []


def test_build_observed_24h_does_not_include_transient_zero_in_low():
    """A transient zero blip should not become the observed 24h low."""
    # Hourly samples across >24h so the sliding window produces output.
    # The zero at hour 12 has neighbours at hour 11 and hour 13 (within 2h).
    points = [
        {"sampled_at": _utc_hour(2026, 3, 9, h), "concurrent_players": count}
        for h, count in [
            (0, 20000), (1, 19500), (2, 19000), (3, 18500),
            (4, 18000), (5, 17500), (6, 18000), (7, 18500),
            (8, 19000), (9, 19500), (10, 20000), (11, 20500),
            (12, 0),  # transient blip
            (13, 19000), (14, 19500), (15, 20000), (16, 20500),
            (17, 21000), (18, 21500), (19, 22000), (20, 22500),
            (21, 23000), (22, 23500), (23, 24000),
        ]
    ] + [
        {"sampled_at": _utc_hour(2026, 3, 10, 0), "concurrent_players": 24500},
        {"sampled_at": _utc_hour(2026, 3, 10, 1), "concurrent_players": 25000},
    ]
    observed = build_observed_24h_player_points(points)
    assert observed, "Expected at least one observed point"
    for point in observed:
        assert point["observed_24h_low"] > 0, (
            f"Transient zero should not be the 24h low, got {point['observed_24h_low']}"
        )


def test_build_steam_activity_markers_no_false_drop_from_transient_zero():
    """A transient zero should not produce a 'major_drop' milestone."""
    # Daily points for the baseline window, then a transient zero with a
    # recovery 1 hour later (within the 2h max_gap).
    points = [
        {"sampled_at": _utc(2026, 3, 1), "concurrent_players": 40000},
        {"sampled_at": _utc(2026, 3, 2), "concurrent_players": 41000},
        {"sampled_at": _utc(2026, 3, 3), "concurrent_players": 42000},
        {"sampled_at": _utc(2026, 3, 4), "concurrent_players": 43000},
        {"sampled_at": _utc(2026, 3, 5), "concurrent_players": 44000},
        {"sampled_at": _utc(2026, 3, 6), "concurrent_players": 45000},
        {"sampled_at": _utc_hour(2026, 3, 7, 11), "concurrent_players": 44500},
        {"sampled_at": _utc_hour(2026, 3, 7, 12), "concurrent_players": 0},
        {"sampled_at": _utc_hour(2026, 3, 7, 13), "concurrent_players": 44000},
    ]
    markers = build_steam_activity_markers(points)
    marker_types = [m["marker_type"] for m in markers]
    assert "major_drop" not in marker_types, (
        f"Transient zero should not trigger a major_drop, got markers: {marker_types}"
    )


def test_build_observed_24h_player_points_returns_rolling_highs_and_lows():
    points = [
        {"sampled_at": datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc), "concurrent_players": 20000},
        {"sampled_at": datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc), "concurrent_players": 27000},
        {"sampled_at": datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc), "concurrent_players": 55000},
    ]

    observed = build_observed_24h_player_points(points)

    assert [point["observed_24h_high"] for point in observed] == [55000]
    assert [point["observed_24h_low"] for point in observed] == [20000]

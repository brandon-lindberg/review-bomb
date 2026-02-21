from datetime import date

from app.cli import _should_update_release_date_from_metacritic


def test_metacritic_release_date_fills_missing():
    assert _should_update_release_date_from_metacritic(
        None,
        date(2026, 2, 14),
        today=date(2026, 2, 21),
    )


def test_metacritic_release_date_blocks_released_to_future_regression():
    assert not _should_update_release_date_from_metacritic(
        date(2026, 2, 14),
        date(2026, 12, 1),
        today=date(2026, 2, 21),
    )


def test_metacritic_release_date_allows_future_placeholder_replacement():
    assert _should_update_release_date_from_metacritic(
        date(2027, 1, 1),
        date(2026, 2, 14),
        today=date(2026, 2, 21),
    )


def test_metacritic_release_date_allows_large_forward_past_correction():
    # Example stale-year fix: 2025 placeholder corrected to 2026 release.
    assert _should_update_release_date_from_metacritic(
        date(2025, 2, 14),
        date(2026, 2, 14),
        today=date(2026, 2, 21),
    )


def test_metacritic_release_date_blocks_small_past_shift():
    assert not _should_update_release_date_from_metacritic(
        date(2026, 1, 10),
        date(2026, 2, 14),
        today=date(2026, 2, 21),
    )


def test_metacritic_release_date_blocks_backward_past_shift():
    # Avoid replacing remaster/port dates with older original-release dates.
    assert not _should_update_release_date_from_metacritic(
        date(2026, 2, 14),
        date(2023, 3, 10),
        today=date(2026, 2, 21),
    )

from datetime import date

from app.services.sync_orchestrator import SyncOrchestrator


def test_release_date_guard_blocks_past_to_future_regression():
    # Known released date should not be replaced by future placeholder date.
    existing = date(2026, 2, 19)
    incoming = date(2027, 1, 1)
    today = date(2026, 2, 20)

    assert not SyncOrchestrator._should_replace_release_date(existing, incoming, today=today)


def test_release_date_guard_allows_future_to_earlier_date():
    # Placeholder future dates should be replaceable by earlier/corrected dates.
    existing = date(2027, 1, 1)
    incoming = date(2026, 2, 19)
    today = date(2026, 2, 20)

    assert SyncOrchestrator._should_replace_release_date(existing, incoming, today=today)


def test_release_date_guard_blocks_backward_past_shift():
    # Once a released date is known, don't drift backward to older past dates.
    existing = date(2026, 2, 19)
    incoming = date(2025, 10, 25)
    today = date(2026, 2, 20)

    assert not SyncOrchestrator._should_replace_release_date(existing, incoming, today=today)


def test_release_date_guard_allows_forward_past_correction():
    # Allow correcting stale-year dates forward in time for already-released games.
    existing = date(2025, 10, 25)
    incoming = date(2026, 2, 19)
    today = date(2026, 2, 20)

    assert SyncOrchestrator._should_replace_release_date(existing, incoming, today=today)

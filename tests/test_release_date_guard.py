from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services.sync_orchestrator import SyncOrchestrator


def _compile(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDb:
    """Records queries; answers whether an established-coverage review exists."""

    def __init__(self, has_established_review: bool = False):
        self.has_established_review = has_established_review
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return _FakeResult((1,) if self.has_established_review else None)


def _orchestrator(db: _FakeDb) -> SyncOrchestrator:
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = db
    return orchestrator


def _game(release_date, steam_sample_size=None, metacritic_user_score=None):
    return SimpleNamespace(
        id=16730,
        release_date=release_date,
        steam_sample_size=steam_sample_size,
        metacritic_user_score=metacritic_user_score,
    )


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


def test_outlet_staff_opencritic_id_is_stable_negative_namespace():
    assert SyncOrchestrator._outlet_staff_opencritic_id(896) == -1000000896


def test_release_date_guard_allows_past_placeholder_to_future_without_evidence():
    # Marvel's Wolverine: ingested with OpenCritic's 2024-10-01 stand-in, then
    # announced for 2026-09-15. With no sign it shipped, the past date is the
    # placeholder and must give way.
    assert SyncOrchestrator._should_replace_release_date(
        date(2024, 10, 1),
        date(2026, 9, 15),
        today=date(2026, 9, 13),
        has_release_evidence=False,
    )


def test_release_date_evidence_only_relaxes_past_to_future_shifts():
    # Backward drift between two past dates stays blocked either way.
    assert not SyncOrchestrator._should_replace_release_date(
        date(2026, 2, 19),
        date(2025, 10, 25),
        today=date(2026, 2, 20),
        has_release_evidence=False,
    )


@pytest.mark.asyncio
async def test_apply_release_date_skips_evidence_lookup_when_not_decisive():
    db = _FakeDb()
    orchestrator = _orchestrator(db)

    # Future placeholder corrected to an earlier date: no lookup needed.
    assert await orchestrator._should_apply_release_date(
        _game(date(2027, 1, 1)), date(2026, 2, 19), date(2026, 2, 20)
    )
    # Missing incoming date keeps the existing one.
    assert not await orchestrator._should_apply_release_date(
        _game(date(2024, 10, 1)), None, date(2026, 9, 13)
    )
    assert db.queries == []


@pytest.mark.asyncio
async def test_apply_release_date_corrects_unshipped_past_placeholder():
    db = _FakeDb(has_established_review=False)
    orchestrator = _orchestrator(db)

    assert await orchestrator._should_apply_release_date(
        _game(date(2024, 10, 1)), date(2026, 9, 15), date(2026, 9, 13)
    )
    assert len(db.queries) == 1


@pytest.mark.asyncio
async def test_apply_release_date_keeps_released_date_with_established_reviews():
    db = _FakeDb(has_established_review=True)
    orchestrator = _orchestrator(db)

    assert not await orchestrator._should_apply_release_date(
        _game(date(2026, 2, 19)), date(2027, 1, 1), date(2026, 2, 20)
    )


@pytest.mark.parametrize(
    "game",
    [
        _game(date(2026, 2, 19), steam_sample_size=40),
        _game(date(2026, 2, 19), metacritic_user_score=7.1),
    ],
    ids=["steam-user-reviews", "metacritic-user-score"],
)
@pytest.mark.asyncio
async def test_user_reviews_prove_release_without_a_review_lookup(game):
    # User reviews only open at launch, so they settle it on their own.
    db = _FakeDb(has_established_review=False)
    orchestrator = _orchestrator(db)

    assert not await orchestrator._should_apply_release_date(
        game, date(2027, 1, 1), date(2026, 2, 20)
    )
    assert db.queries == []


@pytest.mark.asyncio
async def test_embargo_reviews_do_not_count_as_release_evidence():
    # Only reviews published well before the claimed launch prove the game is
    # out; the lookup's cutoff sits PRE_RELEASE_REVIEW_WINDOW_DAYS before it.
    db = _FakeDb()
    orchestrator = _orchestrator(db)

    await orchestrator._has_release_evidence(_game(date(2024, 10, 1)), date(2026, 9, 15))

    sql = _compile(db.queries[0])
    assert "reviews.game_id = 16730" in sql
    assert "reviews.score_normalized IS NOT NULL" in sql
    assert "reviews.published_at < '2026-07-17 00:00:00+00:00'" in sql


def test_no_release_evidence_condition_requires_no_reviews_or_user_scores():
    sql = _compile(SyncOrchestrator._no_release_evidence_condition())

    assert "coalesce(games.steam_sample_size, 0) = 0" in sql
    assert "games.metacritic_user_score IS NULL" in sql
    assert "NOT (EXISTS (SELECT reviews.id" in sql
    assert "reviews.game_id = games.id" in sql


def test_targeted_review_refresh_ignores_release_window():
    orchestrator = _orchestrator(_FakeDb())

    sql = _compile(
        orchestrator._build_recent_review_refresh_query(
            days=14,
            all_games=False,
            opencritic_ids=[17842],
        )
    )

    assert "games.opencritic_id IN (17842)" in sql
    assert "games.release_date >=" not in sql
    assert "games.created_at >=" not in sql

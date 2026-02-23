from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.models.models import (
    DisparitySnapshot,
    Game,
    Journalist,
    JournalistOutletDisparitySnapshot,
    Outlet,
    Review,
)
from app.routers.games import get_game, get_game_reviews
from app.routers.journalists import get_journalist, get_journalist_reviews
from app.routers.outlets import get_outlet, get_outlet_reviews
from app.services.disparity import DisparityCalculator


_UNSET = object()


class FakeScalars:
    def __init__(self, items: list[Any]):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(
        self,
        *,
        scalar_one_or_none: Any = _UNSET,
        scalar: Any = _UNSET,
        one: Any = _UNSET,
        all_rows: Any = _UNSET,
        scalars_all: Any = _UNSET,
    ):
        self._scalar_one_or_none = scalar_one_or_none
        self._scalar = scalar
        self._one = one
        self._all_rows = all_rows
        self._scalars_all = scalars_all

    def scalar_one_or_none(self):
        if self._scalar_one_or_none is _UNSET:
            raise AssertionError("scalar_one_or_none() was not expected for this fake result")
        return self._scalar_one_or_none

    def scalar(self):
        if self._scalar is _UNSET:
            raise AssertionError("scalar() was not expected for this fake result")
        return self._scalar

    def one(self):
        if self._one is _UNSET:
            raise AssertionError("one() was not expected for this fake result")
        return self._one

    def all(self):
        if self._all_rows is _UNSET:
            raise AssertionError("all() was not expected for this fake result")
        return self._all_rows

    def scalars(self):
        if self._scalars_all is _UNSET:
            raise AssertionError("scalars() was not expected for this fake result")
        return FakeScalars(self._scalars_all)


class FakeAsyncSession:
    def __init__(self, results: list[Any] | None = None):
        self._results = list(results or [])
        self.execute_calls: list[tuple[Any, Any]] = []
        self.added: list[Any] = []
        self.flush_calls = 0

    async def execute(self, statement, params=None):
        self.execute_calls.append((statement, params))
        if not self._results:
            return FakeResult()
        result = self._results.pop(0)
        if callable(result):
            return result(statement, params)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_calls += 1


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_refresh_review_disparity_cache_persists_canonical_values():
    db = FakeAsyncSession(results=[FakeResult()])
    calc = DisparityCalculator(db)
    calc._reviews_cache = [
        (1, 10, 100, 200, Decimal("80.00")),
    ]
    calc._user_scores_cache = {
        10: {
            "steam_score": Decimal("70.00"),
            "metacritic_score": Decimal("90.00"),
        }
    }
    calc._load_all_user_scores = AsyncMock(return_value=calc._user_scores_cache)
    calc._load_all_reviews = AsyncMock(return_value=calc._reviews_cache)

    processed = await calc._refresh_review_disparity_cache(batch_size=100)

    assert processed == 1
    assert db.flush_calls == 1
    assert len(db.execute_calls) == 1

    _stmt, params = db.execute_calls[0]
    assert isinstance(params, list)
    assert len(params) == 1
    payload = params[0]
    assert payload["id"] == 1
    assert payload["cached_steam_user_score"] == Decimal("70.00")
    assert payload["cached_metacritic_user_score"] == Decimal("90.00")
    assert payload["cached_disparity_steam"] == Decimal("10")
    assert payload["cached_disparity_metacritic"] == Decimal("-10")
    assert payload["cached_disparity_combined"] == Decimal("0")


@pytest.mark.asyncio
async def test_generate_journalist_outlet_snapshots_uses_pipeline_review_level_combined():
    db = FakeAsyncSession(results=[FakeResult()])
    calc = DisparityCalculator(db)
    calc._reviews_cache = [
        # review_id, game_id, journalist_id, outlet_id, critic_score
        (1, 10, 7, 9, Decimal("80.00")),  # combined = (10 + -10)/2 = 0
        (2, 11, 7, 9, Decimal("70.00")),  # combined = (10 + 20)/2 = 15
    ]
    calc._user_scores_cache = {
        10: {"steam_score": Decimal("70.00"), "metacritic_score": Decimal("90.00")},
        11: {"steam_score": Decimal("60.00"), "metacritic_score": Decimal("50.00")},
    }
    calc._load_all_user_scores = AsyncMock(return_value=calc._user_scores_cache)
    calc._load_all_reviews = AsyncMock(return_value=calc._reviews_cache)

    count = await calc._generate_journalist_outlet_snapshots(date(2026, 2, 23))

    assert count == 1
    assert db.flush_calls == 1
    assert len(db.added) == 1

    snap = db.added[0]
    assert isinstance(snap, JournalistOutletDisparitySnapshot)
    assert snap.journalist_id == 7
    assert snap.outlet_id == 9
    assert snap.review_count == 2
    assert snap.avg_disparity_steam == Decimal("10")
    assert snap.avg_disparity_metacritic == Decimal("5")
    assert snap.avg_disparity_combined == Decimal("7.5")
    assert snap.min_disparity == Decimal("0")
    assert snap.max_disparity == Decimal("15")
    assert snap.std_deviation == Decimal("10.61")


@pytest.mark.asyncio
async def test_get_game_reviews_returns_cached_review_disparity_values():
    game = Game(id=1, title="Example", release_date=date(2026, 2, 20))
    journalist = Journalist(id=2, name="Critic", image_url="https://img")
    outlet = Outlet(id=3, name="Outlet")
    review = Review(
        id=4,
        journalist_id=2,
        game_id=1,
        outlet_id=3,
        score_raw="8",
        score_scale="10",
        score_normalized=Decimal("80.00"),
        cached_disparity_steam=Decimal("33.33"),
        cached_disparity_metacritic=Decimal("-22.22"),
        published_at=_utc(2026, 2, 21),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, journalist, outlet)]),
        ]
    )

    resp = await get_game_reviews.__wrapped__(
        request=SimpleNamespace(),
        game_id=1,
        page=1,
        per_page=20,
        review_timing=None,
        sort_order=None,
        db=db,
    )

    assert resp.total == 1
    assert resp.items[0].disparity_steam == Decimal("33.33")
    assert resp.items[0].disparity_metacritic == Decimal("-22.22")


@pytest.mark.asyncio
async def test_get_outlet_reviews_returns_cached_review_disparity_values():
    journalist = Journalist(id=2, name="Critic", image_url=None)
    game = Game(id=1, title="Example", release_date=date(2026, 2, 20))
    review = Review(
        id=5,
        journalist_id=2,
        game_id=1,
        outlet_id=3,
        score_raw="9",
        score_scale="10",
        score_normalized=Decimal("90.00"),
        cached_disparity_steam=Decimal("12.50"),
        cached_disparity_metacritic=Decimal("-4.75"),
        published_at=_utc(2026, 2, 22),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=3),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, journalist, game)]),
        ]
    )

    resp = await get_outlet_reviews.__wrapped__(
        request=SimpleNamespace(),
        outlet_id=3,
        page=1,
        per_page=20,
        db=db,
    )

    assert resp.total == 1
    assert resp.items[0].disparity_steam == Decimal("12.50")
    assert resp.items[0].disparity_metacritic == Decimal("-4.75")


@pytest.mark.asyncio
async def test_get_journalist_reviews_returns_cached_user_scores_and_disparities():
    game = Game(id=1, title="Example", release_date=date(2026, 2, 20))
    outlet = Outlet(id=3, name="Outlet")
    review = Review(
        id=6,
        journalist_id=2,
        game_id=1,
        outlet_id=3,
        score_raw="7",
        score_scale="10",
        score_normalized=Decimal("70.00"),
        cached_steam_user_score=Decimal("81.00"),
        cached_metacritic_user_score=Decimal("65.00"),
        cached_disparity_steam=Decimal("-11.00"),
        cached_disparity_metacritic=Decimal("5.00"),
        published_at=_utc(2026, 2, 23),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=2),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, game, outlet)]),
        ]
    )

    resp = await get_journalist_reviews.__wrapped__(
        request=SimpleNamespace(),
        journalist_id=2,
        page=1,
        per_page=20,
        db=db,
    )

    assert resp.total == 1
    item = resp.items[0]
    assert item.steam_user_score == Decimal("81.00")
    assert item.metacritic_user_score == Decimal("65.00")
    assert item.disparity_steam == Decimal("-11.00")
    assert item.disparity_metacritic == Decimal("5.00")


@pytest.mark.asyncio
async def test_get_journalist_detail_uses_pipeline_snapshots_for_disparity_and_outlet_breakdown():
    now = _utc(2026, 2, 23)
    journalist = Journalist(
        id=2,
        name="Angelus Victor",
        avg_disparity=None,
        created_at=now,
        updated_at=now,
    )
    review = Review(
        id=10,
        journalist_id=2,
        game_id=1,
        outlet_id=3,
        score_raw="8",
        score_scale="10",
        score_normalized=Decimal("80.00"),
        published_at=_utc(2026, 2, 21),
    )
    game = Game(id=1, title="Example", release_date=date(2026, 2, 20))
    latest_snapshot = DisparitySnapshot(
        id=100,
        journalist_id=2,
        snapshot_date=date(2026, 2, 23),
        avg_disparity_steam=Decimal("-7.03"),
        avg_disparity_metacritic=Decimal("17.75"),
        avg_disparity_combined=Decimal("-1.15"),
        review_count=52,
        std_deviation=Decimal("8.88"),
    )
    pair_snapshot = JournalistOutletDisparitySnapshot(
        id=200,
        journalist_id=2,
        outlet_id=3,
        snapshot_date=date(2026, 2, 23),
        avg_disparity_combined=Decimal("2.90"),
        review_count=10,
    )

    stats_row = SimpleNamespace(
        total_reviews=1,
        avg_score_given=Decimal("80.00"),
        min_score_given=Decimal("80.00"),
        max_score_given=Decimal("80.00"),
    )
    outlet_row = SimpleNamespace(
        outlet_id=3,
        outlet_name="IGN Spain",
        review_count=10,
        date_range_start=_utc(2025, 1, 1),
        date_range_end=_utc(2026, 2, 21),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=journalist),
            FakeResult(one=stats_row),
            FakeResult(all_rows=[(review, game)]),
            FakeResult(scalar_one_or_none=latest_snapshot),
            FakeResult(all_rows=[outlet_row]),
            FakeResult(scalars_all=[pair_snapshot]),
        ]
    )

    resp = await get_journalist(journalist_id=2, db=db)

    assert resp.avg_disparity == Decimal("-1.15")
    assert resp.stats.overall_disparity_steam == Decimal("-7.03")
    assert resp.stats.overall_disparity_metacritic == Decimal("17.75")
    assert resp.stats.overall_disparity_combined == Decimal("-1.15")
    assert resp.outlet_breakdown[0].avg_disparity == Decimal("2.90")


@pytest.mark.asyncio
async def test_get_outlet_detail_prefers_denormalized_combined_and_snapshot_source_values():
    now = _utc(2026, 2, 23)
    outlet = Outlet(
        id=3,
        name="IGN Spain",
        avg_disparity=Decimal("2.90"),
        review_count_scored=1386,
        journalist_count=53,
        score_std_dev=Decimal("14.70"),
        created_at=now,
        updated_at=now,
    )
    snapshot = DisparitySnapshot(
        id=300,
        outlet_id=3,
        snapshot_date=date(2026, 2, 23),
        avg_disparity_steam=Decimal("-4.50"),
        avg_disparity_metacritic=Decimal("8.10"),
        avg_disparity_combined=Decimal("1.80"),
        review_count=1386,
    )
    metrics_row = SimpleNamespace(
        avg_score=Decimal("75.80"),
        min_score=Decimal("30.00"),
        max_score=Decimal("100.00"),
        early_review_count=1,
        launch_window_review_count=2,
        late_review_count=3,
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=outlet),
            FakeResult(one=metrics_row),
            FakeResult(scalar_one_or_none=snapshot),
        ]
    )

    resp = await get_outlet(outlet_id=3, db=db)

    # Combined shown to users should match canonical denormalized value, not snapshot fallback.
    assert resp.avg_disparity_combined == Decimal("2.90")
    # Source values come from the latest pipeline snapshot.
    assert resp.avg_disparity_steam == Decimal("-4.50")
    assert resp.avg_disparity_metacritic == Decimal("8.10")


@pytest.mark.asyncio
async def test_get_game_detail_returns_stored_denormalized_disparities():
    now = _utc(2026, 2, 23)
    game = Game(
        id=1,
        title="Ys X: Proud Nordics",
        release_date=date(2026, 2, 20),
        steam_user_score=Decimal("88.00"),
        steam_sample_size=200,
        metacritic_user_score=Decimal("90.00"),
        metacritic_sample_size=50,
        disparity_steam=Decimal("-3.25"),
        disparity_metacritic=Decimal("1.75"),
        critic_review_count=12,
        created_at=now,
        updated_at=now,
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalars_all=[]),
        ]
    )

    resp = await get_game(game_id=1, db=db)

    assert resp.disparity_steam == Decimal("-3.25")
    assert resp.disparity_metacritic == Decimal("1.75")

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
    SteamPlayerRangeSnapshot,
    SteamPlayerSnapshot,
)
from app.routers.games import get_game, get_game_reviews
from app.routers.games import get_game_history, get_game_steam_activity
from app.routers.journalists import get_journalist, get_journalist_history, get_journalist_reviews
from app.routers.outlets import get_outlet, get_outlet_history, get_outlet_reviews
from app.schemas.schemas import DisparitySnapshot as ChartDisparitySnapshot
from app.services.disparity import DisparityCalculator
from app.services.disparity_timeline import build_disparity_timeline_from_reviews


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

    def __iter__(self):
        if self._all_rows is _UNSET:
            raise AssertionError("iteration was not expected for this fake result")
        return iter(self._all_rows)

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
        self.commit_calls = 0

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

    async def commit(self):
        self.commit_calls += 1


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_refresh_review_disparity_cache_persists_canonical_values():
    db = FakeAsyncSession(results=[FakeResult(all_rows=[]), FakeResult()])
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
    assert db.flush_calls == 0
    assert db.commit_calls == 1
    assert len(db.execute_calls) == 2

    _stmt, params = db.execute_calls[1]
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
async def test_refresh_review_disparity_cache_skips_unchanged_rows():
    db = FakeAsyncSession(
        results=[
            FakeResult(
                all_rows=[
                    (
                        1,
                        Decimal("70.00"),
                        Decimal("90.00"),
                        Decimal("10.00"),
                        Decimal("-10.00"),
                        Decimal("0.00"),
                    )
                ]
            )
        ]
    )
    calc = DisparityCalculator(db)
    calc._reviews_cache = [(1, 10, 100, 200, Decimal("80.00"))]
    calc._user_scores_cache = {
        10: {"steam_score": Decimal("70.00"), "metacritic_score": Decimal("90.00")}
    }
    calc._load_all_user_scores = AsyncMock(return_value=calc._user_scores_cache)
    calc._load_all_reviews = AsyncMock(return_value=calc._reviews_cache)

    updated = await calc._refresh_review_disparity_cache(batch_size=100)

    assert updated == 0
    # Only the existing-cache read runs; no write/commit needed.
    assert len(db.execute_calls) == 1
    assert db.commit_calls == 0


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
async def test_get_journalist_reviews_runtime_corrects_stale_score_for_travis_northup_highguard():
    game = Game(id=99, title="Highguard", release_date=date(2026, 2, 20))
    outlet = Outlet(id=8, name="IGN")
    review = Review(
        id=77,
        journalist_id=42,
        game_id=99,
        outlet_id=8,
        score_raw="70",
        score_scale="10",
        score_normalized=Decimal("100.00"),
        cached_steam_user_score=Decimal("65.00"),
        cached_metacritic_user_score=Decimal("70.00"),
        published_at=_utc(2026, 2, 23),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=42),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, game, outlet)]),
        ]
    )

    resp = await get_journalist_reviews.__wrapped__(
        request=SimpleNamespace(),
        journalist_id=42,
        page=1,
        per_page=20,
        db=db,
    )

    assert resp.total == 1
    assert resp.items[0].score_normalized == Decimal("70")


@pytest.mark.asyncio
async def test_get_journalist_reviews_includes_valid_zero_score_rows():
    game = Game(id=1, title="Zero Hero", release_date=date(2026, 2, 20))
    outlet = Outlet(id=2, name="Outlet")
    review = Review(
        id=10,
        journalist_id=3,
        game_id=1,
        outlet_id=2,
        score_raw="0",
        score_scale="10",
        score_normalized=Decimal("0.00"),
        published_at=_utc(2026, 2, 21),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=3),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, game, outlet)]),
        ]
    )

    resp = await get_journalist_reviews.__wrapped__(
        request=SimpleNamespace(),
        journalist_id=3,
        page=1,
        per_page=20,
        db=db,
    )

    assert resp.total == 1
    assert resp.items[0].score_normalized == Decimal("0")


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
        early_review_count=0,
        launch_window_review_count=1,
        late_review_count=0,
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
            FakeResult(scalar_one_or_none=latest_snapshot),
            FakeResult(all_rows=[outlet_row]),
            FakeResult(
                all_rows=[
                    SimpleNamespace(
                        outlet_id=pair_snapshot.outlet_id,
                        avg_disparity_combined=pair_snapshot.avg_disparity_combined,
                    )
                ]
            ),
        ]
    )

    resp = await get_journalist(journalist_id=2, db=db)

    assert resp.avg_disparity == Decimal("-1.15")
    assert resp.stats.overall_disparity_steam == Decimal("-7.03")
    assert resp.stats.overall_disparity_metacritic == Decimal("17.75")
    assert resp.stats.overall_disparity_combined == Decimal("-1.15")
    assert resp.outlet_breakdown[0].avg_disparity == Decimal("2.90")


@pytest.mark.asyncio
async def test_entity_stats_separate_disparity_std_dev_from_score_std_dev():
    db = FakeAsyncSession()
    calc = DisparityCalculator(db)
    calc._user_scores_cache = {
        10: {"steam_score": Decimal("60.00"), "metacritic_score": None},
        11: {"steam_score": Decimal("80.00"), "metacritic_score": None},
    }
    calc._reviews_by_journalist = {
        1: [
            (1, 10, 1, 2, Decimal("70.00")),
            (2, 11, 1, 2, Decimal("90.00")),
        ]
    }
    calc._reviews_by_outlet = {}
    calc._reviews_by_game = {}

    stats = calc._calculate_entity_disparity_from_cache("journalist", 1)

    assert stats is not None
    assert stats["std_deviation"] == Decimal("0")
    assert stats["score_std_dev"] == Decimal("14.14")
    assert stats["is_binary_profile"] is False


@pytest.mark.asyncio
async def test_generate_journalist_snapshots_persists_binary_and_score_std_dev():
    db = FakeAsyncSession(
        results=[
            FakeResult(all_rows=[(7, _utc(2026, 2, 23))]),
            FakeResult(),
        ]
    )
    calc = DisparityCalculator(db)
    calc.ensure_detail_disparity_caches = AsyncMock(return_value=None)
    calc._reviews_cache = [
        (1, 1, 7, 3, Decimal("0.00")),
        (2, 2, 7, 3, Decimal("100.00")),
        (3, 3, 7, 3, Decimal("0.00")),
        (4, 4, 7, 3, Decimal("100.00")),
        (5, 5, 7, 3, Decimal("0.00")),
        (6, 6, 7, 3, Decimal("100.00")),
        (7, 7, 7, 3, Decimal("0.00")),
        (8, 8, 7, 3, Decimal("100.00")),
        (9, 9, 7, 3, Decimal("0.00")),
        (10, 10, 7, 3, Decimal("100.00")),
    ]
    calc._reviews_by_journalist = {7: calc._reviews_cache}
    calc._reviews_by_outlet = {3: calc._reviews_cache}
    calc._reviews_by_game = {row[1]: [row] for row in calc._reviews_cache}
    calc._user_scores_cache = {
        row[1]: {"steam_score": None, "metacritic_score": None}
        for row in calc._reviews_cache
    }

    count = await calc.generate_journalist_snapshots(date(2026, 2, 23))

    assert count == 1
    _stmt, params = db.execute_calls[1]
    assert isinstance(params, list)
    assert params[0]["id"] == 7
    assert params[0]["is_binary_reviewer"] is True
    assert params[0]["score_std_dev"] == Decimal("52.7")


@pytest.mark.asyncio
async def test_generate_outlet_snapshots_persists_binary_flag():
    db = FakeAsyncSession(
        results=[
            FakeResult(all_rows=[(3, _utc(2026, 2, 23))]),
            FakeResult(all_rows=[(3, 1)]),
            FakeResult(),
        ]
    )
    calc = DisparityCalculator(db)
    calc.ensure_detail_disparity_caches = AsyncMock(return_value=None)
    calc._reviews_cache = [
        (1, 1, 7, 3, Decimal("0.00")),
        (2, 2, 7, 3, Decimal("100.00")),
        (3, 3, 7, 3, Decimal("0.00")),
        (4, 4, 7, 3, Decimal("100.00")),
        (5, 5, 7, 3, Decimal("0.00")),
        (6, 6, 7, 3, Decimal("100.00")),
        (7, 7, 7, 3, Decimal("0.00")),
        (8, 8, 7, 3, Decimal("100.00")),
        (9, 9, 7, 3, Decimal("0.00")),
        (10, 10, 7, 3, Decimal("100.00")),
    ]
    calc._reviews_by_journalist = {7: calc._reviews_cache}
    calc._reviews_by_outlet = {3: calc._reviews_cache}
    calc._reviews_by_game = {row[1]: [row] for row in calc._reviews_cache}
    calc._user_scores_cache = {
        row[1]: {"steam_score": None, "metacritic_score": None}
        for row in calc._reviews_cache
    }

    count = await calc.generate_outlet_snapshots(date(2026, 2, 23))

    assert count == 1
    _stmt, params = db.execute_calls[2]
    assert isinstance(params, list)
    assert params[0]["id"] == 3
    assert params[0]["is_binary_scorer"] is True


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
        steam_current_players=56164,
        steam_current_players_sampled_at=now,
        steam_player_24h_peak=62830,
        steam_player_24h_low_observed=25110,
        steam_player_all_time_peak=88337,
        steam_player_all_time_peak_at=_utc(2026, 2, 13),
        steam_player_stats_synced_at=now,
        steam_achievement_count=58,
        steam_achievement_count_synced_at=now,
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
    assert not hasattr(resp, "steam_current_players")
    assert not hasattr(resp, "steam_current_players_sampled_at")
    assert resp.steam_player_24h_peak == 62830
    assert resp.steam_player_24h_low_observed == 25110
    assert resp.steam_player_all_time_peak == 88337
    assert resp.steam_achievement_count == 58


@pytest.mark.asyncio
async def test_get_game_steam_activity_returns_points_and_curated_markers():
    now = _utc(2026, 3, 16)
    game = Game(
        id=11,
        title="Marathon",
        steam_app_id=123,
        steam_player_24h_peak=62830,
        steam_player_24h_low_observed=25110,
        steam_player_all_time_peak=88337,
        steam_player_all_time_peak_at=_utc(2026, 3, 6),
        steam_player_stats_synced_at=now,
        steam_achievement_count=42,
        steam_achievement_count_synced_at=now,
    )
    snapshots = [
        SteamPlayerRangeSnapshot(
            game_id=11,
            sampled_at=datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc),
            players_24h_high=57000,
            players_24h_low=21000,
        ),
        SteamPlayerRangeSnapshot(
            game_id=11,
            sampled_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            players_24h_high=55000,
            players_24h_low=20000,
        ),
    ]

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalars_all=snapshots),
        ]
    )

    resp = await get_game_steam_activity(game_id=11, limit=10000, db=db)

    assert not hasattr(resp.summary, "steam_current_players")
    assert not hasattr(resp.summary, "steam_current_players_sampled_at")
    assert [point.observed_24h_high for point in resp.points] == [55000, 57000]
    assert [point.observed_24h_low for point in resp.points] == [20000, 21000]
    assert any(marker.marker_type == "first_tracked" for marker in resp.markers)
    assert any(marker.marker_type == "all_time_peak" for marker in resp.markers)


@pytest.mark.asyncio
async def test_build_disparity_timeline_from_reviews_uses_review_dates_and_cumulative_values():
    rows = [
        SimpleNamespace(
            timeline_date=date(2024, 6, 1),
            day_review_count=1,
            day_steam_sum=Decimal("10.00"),
            day_steam_count=1,
            day_metacritic_sum=Decimal("20.00"),
            day_metacritic_count=1,
            day_combined_sum=Decimal("15.00"),
            day_combined_count=1,
        ),
        SimpleNamespace(
            timeline_date=date(2024, 6, 3),
            day_review_count=2,
            day_steam_sum=Decimal("5.00"),
            day_steam_count=1,
            day_metacritic_sum=None,
            day_metacritic_count=0,
            day_combined_sum=Decimal("5.00"),
            day_combined_count=1,
        ),
    ]
    db = FakeAsyncSession(results=[FakeResult(all_rows=rows)])

    timeline = await build_disparity_timeline_from_reviews(
        db=db,
        entity_filter=(Review.game_id == 1),
        limit=10000,
    )

    assert [point.date for point in timeline] == [date(2024, 6, 1), date(2024, 6, 3)]
    assert [point.review_count for point in timeline] == [1, 3]
    assert timeline[0].avg_disparity_steam == Decimal("10.00")
    assert timeline[0].avg_disparity_metacritic == Decimal("20.00")
    assert timeline[0].avg_disparity_combined == Decimal("15.00")
    assert timeline[1].avg_disparity_steam == Decimal("7.50")
    assert timeline[1].avg_disparity_metacritic == Decimal("20.00")
    assert timeline[1].avg_disparity_combined == Decimal("10.00")


@pytest.mark.asyncio
async def test_build_disparity_timeline_from_reviews_respects_limit_from_end():
    rows = [
        SimpleNamespace(
            timeline_date=date(2024, 1, 1),
            day_review_count=1,
            day_steam_sum=Decimal("1.00"),
            day_steam_count=1,
            day_metacritic_sum=Decimal("1.00"),
            day_metacritic_count=1,
            day_combined_sum=Decimal("1.00"),
            day_combined_count=1,
        ),
        SimpleNamespace(
            timeline_date=date(2024, 1, 2),
            day_review_count=1,
            day_steam_sum=Decimal("2.00"),
            day_steam_count=1,
            day_metacritic_sum=Decimal("2.00"),
            day_metacritic_count=1,
            day_combined_sum=Decimal("2.00"),
            day_combined_count=1,
        ),
        SimpleNamespace(
            timeline_date=date(2024, 1, 3),
            day_review_count=1,
            day_steam_sum=Decimal("3.00"),
            day_steam_count=1,
            day_metacritic_sum=Decimal("3.00"),
            day_metacritic_count=1,
            day_combined_sum=Decimal("3.00"),
            day_combined_count=1,
        ),
    ]
    db = FakeAsyncSession(results=[FakeResult(all_rows=rows)])

    timeline = await build_disparity_timeline_from_reviews(
        db=db,
        entity_filter=(Review.game_id == 1),
        limit=2,
    )

    assert [point.date for point in timeline] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert [point.review_count for point in timeline] == [2, 3]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("history_fn", "patch_target", "entity_obj", "id_param"),
    [
        (get_game_history, "app.routers.games.build_disparity_timeline_from_reviews", Game(id=11, title="X"), "game_id"),
        (get_journalist_history, "app.routers.journalists.build_disparity_timeline_from_reviews", Journalist(id=12, name="J"), "journalist_id"),
        (get_outlet_history, "app.routers.outlets.build_disparity_timeline_from_reviews", Outlet(id=13, name="O"), "outlet_id"),
    ],
)
async def test_history_endpoints_prefer_review_timeline(
    monkeypatch: pytest.MonkeyPatch,
    history_fn,
    patch_target: str,
    entity_obj,
    id_param: str,
):
    expected_timeline = [
        ChartDisparitySnapshot(
            date=date(2023, 10, 1),
            avg_disparity_steam=Decimal("2.00"),
            avg_disparity_metacritic=Decimal("4.00"),
            avg_disparity_combined=Decimal("3.00"),
            review_count=10,
        )
    ]
    fake_builder = AsyncMock(return_value=expected_timeline)
    monkeypatch.setattr(patch_target, fake_builder)
    db = FakeAsyncSession(results=[FakeResult(scalar_one_or_none=entity_obj)])

    kwargs = {id_param: str(entity_obj.id), "limit": 50, "db": db}
    response = await history_fn(**kwargs)

    assert response == expected_timeline
    assert len(db.execute_calls) == 1
    fake_builder.assert_awaited_once()
    assert fake_builder.await_args.kwargs["limit"] == 50


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("history_fn", "patch_target", "entity_obj", "id_param", "entity_key"),
    [
        (get_game_history, "app.routers.games.build_disparity_timeline_from_reviews", Game(id=21, title="X"), "game_id", "game_id"),
        (get_journalist_history, "app.routers.journalists.build_disparity_timeline_from_reviews", Journalist(id=22, name="J"), "journalist_id", "journalist_id"),
        (get_outlet_history, "app.routers.outlets.build_disparity_timeline_from_reviews", Outlet(id=23, name="O"), "outlet_id", "outlet_id"),
    ],
)
async def test_history_endpoints_fallback_dedupes_snapshot_dates(
    monkeypatch: pytest.MonkeyPatch,
    history_fn,
    patch_target: str,
    entity_obj,
    id_param: str,
    entity_key: str,
):
    monkeypatch.setattr(patch_target, AsyncMock(return_value=[]))

    snapshot_latest = DisparitySnapshot(
        id=300,
        snapshot_date=date(2026, 2, 23),
        avg_disparity_combined=Decimal("9.00"),
        review_count=100,
        **{entity_key: entity_obj.id},
    )
    snapshot_duplicate_same_day = DisparitySnapshot(
        id=299,
        snapshot_date=date(2026, 2, 23),
        avg_disparity_combined=Decimal("8.00"),
        review_count=99,
        **{entity_key: entity_obj.id},
    )
    snapshot_prior_day = DisparitySnapshot(
        id=250,
        snapshot_date=date(2026, 2, 22),
        avg_disparity_combined=Decimal("7.00"),
        review_count=90,
        **{entity_key: entity_obj.id},
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=entity_obj),
            FakeResult(
                scalars_all=[
                    snapshot_latest,
                    snapshot_duplicate_same_day,
                    snapshot_prior_day,
                ]
            ),
        ]
    )

    kwargs = {id_param: str(entity_obj.id), "limit": 10, "db": db}
    response = await history_fn(**kwargs)

    assert [point.date for point in response] == [date(2026, 2, 22), date(2026, 2, 23)]
    assert [point.review_count for point in response] == [90, 100]
    assert response[-1].avg_disparity_combined == Decimal("9.00")

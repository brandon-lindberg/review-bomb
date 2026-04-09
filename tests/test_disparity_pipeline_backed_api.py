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
    GameSimilarityV3Neighbor,
    Journalist,
    JournalistOutletDisparitySnapshot,
    Outlet,
    Review,
    SteamPlayerRangeSnapshot,
    SteamPlayerSnapshot,
)
from app.routers.games import get_game, get_game_reviews, get_game_similar
from app.routers.games import get_game_history, get_game_steam_activity
from app.routers.journalists import get_journalist, get_journalist_history, get_journalist_reviews
from app.routers.outlets import get_outlet, get_outlet_history, get_outlet_reviews
from app.schemas.schemas import DisparitySnapshot as ChartDisparitySnapshot
from app.schemas.schemas import SteamPlayerPoint
from app.services.disparity import DisparityCalculator
from app.services.disparity_timeline import build_disparity_timeline_from_reviews
from app.services.player_scraper import ScraperSteamActivity


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
    assert resp.steam_current_players == 56164
    assert resp.steam_current_players_sampled_at == now
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
        release_date=date(2026, 3, 10),
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
            FakeResult(
                all_rows=[
                    (datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc), 53000),
                    (datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc), 54000),
                ]
            ),
        ]
    )

    resp = await get_game_steam_activity(game_id=11, limit=10000, db=db)

    assert resp.summary.steam_current_players is None
    assert resp.summary.steam_current_players_sampled_at is None
    assert resp.summary.steam_player_24h_peak == 57000
    assert resp.summary.steam_player_24h_low_observed == 21000
    assert resp.summary.steam_player_all_time_peak == 57000


@pytest.mark.asyncio
async def test_get_game_similar_returns_only_strict_taxonomy_matches(monkeypatch: pytest.MonkeyPatch):
    anchor = Game(
        id=1,
        public_id="anchor",
        title="Anchor Game",
        release_date=date(2026, 1, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_themes=["action-rpg"],
        taxonomy_modes=["single-player"],
    )
    strong_match = Game(
        id=2,
        public_id="strong",
        title="Strong Match",
        release_date=date(2026, 3, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_themes=["action-rpg"],
        taxonomy_modes=["single-player"],
        critic_review_count=40,
        avg_critic_score=Decimal("88.00"),
        steam_user_score=Decimal("90.00"),
        steam_sample_size=400,
    )
    mode_match = Game(
        id=3,
        public_id="mode",
        title="Mode Match",
        release_date=date(2025, 12, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_modes=["single-player"],
        critic_review_count=20,
        avg_critic_score=Decimal("81.00"),
        metacritic_user_score=Decimal("84.00"),
        metacritic_sample_size=40,
    )
    studio_only = Game(
        id=4,
        public_id="studio",
        title="Studio Only",
        release_date=date(2026, 2, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_studios=["shared-studio"],
        critic_review_count=22,
    )
    one_source_only = Game(
        id=5,
        public_id="onesource",
        title="One Source Only",
        release_date=date(2026, 2, 1),
        taxonomy_sources=["steam"],
        taxonomy_genres=["rpg"],
        taxonomy_themes=["action-rpg"],
        taxonomy_modes=["single-player"],
        critic_review_count=30,
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(scalars_all=[strong_match, mode_match, studio_only, one_source_only]),
            FakeResult(
                all_rows=[
                    SimpleNamespace(game_id=2, shared_outlets=2, shared_journalists=1),
                    SimpleNamespace(game_id=3, shared_outlets=0, shared_journalists=0),
                    SimpleNamespace(game_id=4, shared_outlets=1, shared_journalists=1),
                    SimpleNamespace(game_id=5, shared_outlets=1, shared_journalists=0),
                ]
            ),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=1, limit=4, db=db)

    assert [item.title for item in resp] == ["Strong Match", "Mode Match"]
    assert resp[0].match_reasons
    assert resp[0].similarity_score > resp[1].similarity_score


@pytest.mark.asyncio
async def test_get_game_similar_hides_section_when_fewer_than_two_matches(monkeypatch: pytest.MonkeyPatch):
    anchor = Game(
        id=10,
        public_id="anchor-two",
        title="Anchor Two",
        release_date=date(2026, 1, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["strategy"],
        taxonomy_themes=["turn-based"],
    )
    lone_match = Game(
        id=11,
        public_id="lone",
        title="Lone Match",
        release_date=date(2026, 1, 10),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["strategy"],
        taxonomy_themes=["turn-based"],
        critic_review_count=12,
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(scalars_all=[lone_match]),
            FakeResult(all_rows=[SimpleNamespace(game_id=11, shared_outlets=0, shared_journalists=0)]),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=10, limit=4, db=db)

    assert resp == []


@pytest.mark.asyncio
async def test_get_game_similar_returns_empty_for_hidden_v2_anchor_without_v1_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=12,
        public_id="hidden-anchor",
        title="Hidden Anchor",
        release_date=date(2026, 1, 1),
        taxonomy_v2_status="hidden",
        taxonomy_v2_version="taxonomy_v3_matrix_1",
        taxonomy_v2_fingerprint={"world_topology": ["open_world"]},
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=12, limit=4, db=db)

    assert resp == []


@pytest.mark.asyncio
async def test_get_game_similar_prefers_published_v3_neighbors_when_available(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=40,
        public_id="v3-anchor",
        title="Anchor V3",
        release_date=date(2026, 1, 1),
        similarity_v3_version="similarity_v3_pgvector_1",
        similarity_v3_status="computed",
    )
    candidate_one = Game(
        id=41,
        public_id="v3-one",
        title="Vector Match One",
        release_date=date(2026, 2, 1),
        critic_review_count=40,
        avg_critic_score=Decimal("89.00"),
        steam_user_score=Decimal("91.00"),
        steam_sample_size=500,
    )
    candidate_two = Game(
        id=42,
        public_id="v3-two",
        title="Vector Match Two",
        release_date=date(2026, 3, 1),
        critic_review_count=30,
        avg_critic_score=Decimal("84.00"),
        metacritic_user_score=Decimal("86.00"),
        metacritic_sample_size=100,
    )
    neighbor_one = GameSimilarityV3Neighbor(
        anchor_game_id=40,
        candidate_game_id=41,
        rank=1,
        final_score=Decimal("0.9123"),
        explanation_payload={"match_reasons": ["Shared world", "Shared traversal"], "confidence": "high"},
        similarity_version="similarity_v3_pgvector_1",
    )
    neighbor_two = GameSimilarityV3Neighbor(
        anchor_game_id=40,
        candidate_game_id=42,
        rank=2,
        final_score=Decimal("0.8444"),
        explanation_payload={"match_reasons": ["Shared setting"], "confidence": "medium"},
        similarity_version="similarity_v3_pgvector_1",
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(all_rows=[(neighbor_one, candidate_one), (neighbor_two, candidate_two)]),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=40, limit=4, db=db)

    assert [item.title for item in resp] == ["Vector Match One", "Vector Match Two"]
    assert resp[0].similarity_score == 912
    assert resp[0].match_reasons == ["Shared world", "Shared traversal"]


@pytest.mark.asyncio
async def test_get_game_similar_prefers_v2_archetype_matches_over_broad_v1_overlap(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=50,
        public_id="crimson",
        title="Crimson Desert",
        release_date=date(2026, 1, 1),
        taxonomy_studios=["pearl-abyss"],
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_secondary_archetypes=["western_narrative_rpg", "soulslike_action_rpg", "mmo_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "progression_model": ["quest_driven", "buildcraft", "gear_chase"],
            "traversal_verbs": ["horseback", "climbing"],
            "setting": ["high_fantasy"],
            "tone": ["serious", "heroic"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=30,
    )
    witcher_like = Game(
        id=51,
        public_id="witcher-like",
        title="Witcher-Like",
        release_date=date(2025, 5, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["horseback"],
            "setting": ["high_fantasy"],
            "tone": ["serious"],
            "mode_profile": ["single_player"],
            "narrative_structure": ["authored_branching"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=40,
        avg_critic_score=Decimal("91.00"),
    )
    elden_like = Game(
        id=52,
        public_id="elden-like",
        title="Elden-Like",
        release_date=date(2025, 6, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "combat_structure": ["boss_centric"],
            "combat_tempo": ["deliberate"],
            "progression_model": ["quest_driven", "gear_chase"],
            "setting": ["dark_fantasy"],
            "tone": ["bleak"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=45,
        avg_critic_score=Decimal("93.00"),
    )
    botw_like = Game(
        id=53,
        public_id="botw-like",
        title="BOTW-Like",
        release_date=date(2025, 4, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="action_adventure",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "progression_model": ["quest_driven"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=38,
        avg_critic_score=Decimal("92.00"),
    )
    horror_false_positive = Game(
        id=54,
        public_id="horror",
        title="Resident Evil Requiem",
        release_date=date(2026, 2, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="horror",
        taxonomy_v2_primary_archetype="action_horror",
        taxonomy_v2_fingerprint={
            "world_topology": ["linear"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["encounter_driven"],
            "setting": ["horror"],
            "tone": ["bleak", "grotesque"],
            "mode_profile": ["single_player"],
            "hard_exclusions": ["pure_survival_horror"],
            "soft_penalties": [],
        },
        critic_review_count=55,
        avg_critic_score=Decimal("90.00"),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(scalars_all=[witcher_like, elden_like, botw_like, horror_false_positive]),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=50, limit=4, db=db)

    assert [item.title for item in resp] == ["Elden-Like", "Witcher-Like", "BOTW-Like"]
    assert all("Shared genres" not in reason for item in resp for reason in item.match_reasons)
    assert all(item.title != "Resident Evil Requiem" for item in resp)


@pytest.mark.asyncio
async def test_get_game_similar_diversifies_v2_results_across_primary_archetypes(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=60,
        public_id="crimson-two",
        title="Crimson Desert",
        release_date=date(2026, 1, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_secondary_archetypes=["western_narrative_rpg", "soulslike_action_rpg", "mmo_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["quest_driven", "buildcraft", "skill_tree"],
            "traversal_verbs": ["horseback", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=30,
    )
    totk_like = Game(
        id=61,
        public_id="totk-like",
        title="TOTK-Like",
        release_date=date(2025, 5, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["gear_chase"],
            "traversal_verbs": ["gliding", "climbing"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=50,
        avg_critic_score=Decimal("96.00"),
    )
    botw_like = Game(
        id=62,
        public_id="botw-like",
        title="BOTW-Like",
        release_date=date(2025, 4, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["gear_chase"],
            "traversal_verbs": ["gliding"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=48,
        avg_critic_score=Decimal("94.00"),
    )
    forspoken_like = Game(
        id=63,
        public_id="forspoken-like",
        title="Forspoken-Like",
        release_date=date(2025, 3, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "magic"],
            "progression_model": ["buildcraft"],
            "traversal_verbs": ["parkour"],
            "setting": ["high_fantasy"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=47,
        avg_critic_score=Decimal("90.00"),
    )
    witcher_like = Game(
        id=64,
        public_id="witcher-like-two",
        title="Witcher-Like",
        release_date=date(2025, 2, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "narrative_structure": ["authored_branching"],
            "entity_interaction": ["dialogue_choice"],
            "rules_goals": ["complete_quests"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=46,
        avg_critic_score=Decimal("93.00"),
    )
    amalur_like = Game(
        id=67,
        public_id="amalur-like",
        title="Amalur-Like",
        release_date=date(2025, 2, 15),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "progression_model": ["quest_driven", "buildcraft", "skill_tree"],
            "setting": ["high_fantasy"],
            "narrative_structure": ["authored_branching"],
            "entity_interaction": ["dialogue_choice"],
            "rules_goals": ["complete_quests"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=18,
        avg_critic_score=Decimal("87.00"),
    )
    elden_like = Game(
        id=65,
        public_id="elden-like-two",
        title="Elden-Like",
        release_date=date(2025, 1, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft", "gear_chase"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=45,
        avg_critic_score=Decimal("95.00"),
    )
    black_desert_like = Game(
        id=66,
        public_id="black-desert-like",
        title="Black Desert-Like",
        release_date=date(2024, 12, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["buildcraft", "base_growth"],
            "setting": ["high_fantasy", "mythic"],
            "mode_profile": ["mmo"],
            "content_model": ["mmo_persistent"],
            "hard_exclusions": ["mmo_first"],
            "soft_penalties": [],
        },
        critic_review_count=44,
        avg_critic_score=Decimal("88.00"),
    )
    maneater_like = Game(
        id=68,
        public_id="maneater-like",
        title="Maneater-Like",
        release_date=date(2025, 1, 15),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "setting": ["modern"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=60,
        avg_critic_score=Decimal("84.00"),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(
                scalars_all=[
                    totk_like,
                    botw_like,
                    forspoken_like,
                    witcher_like,
                    amalur_like,
                    elden_like,
                    black_desert_like,
                    maneater_like,
                ]
            ),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=60, limit=5, db=db)

    titles = [item.title for item in resp]
    assert len(resp) == 5
    assert titles[0] == "TOTK-Like"
    assert "Witcher-Like" in titles
    assert "Elden-Like" in titles
    assert "Black Desert-Like" in titles
    assert "Amalur-Like" not in titles
    assert "Forspoken-Like" not in titles
    assert "Maneater-Like" not in titles


@pytest.mark.asyncio
async def test_get_game_similar_crimson_style_selector_prefers_western_mmo_and_second_same_lane(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=68,
        public_id="crimson-three",
        title="Crimson Desert",
        release_date=date(2026, 1, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_secondary_archetypes=["soulslike_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["quest_driven", "buildcraft", "gear_chase"],
            "traversal_verbs": ["horseback", "climbing"],
            "setting": ["high_fantasy"],
            "tone": ["serious", "heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=48,
        avg_critic_score=Decimal("89.00"),
    )
    totk_like = Game(
        id=69,
        public_id="totk-like-three",
        title="TOTK-Like",
        release_date=date(2023, 5, 12),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft", "skill_tree"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=72,
        avg_critic_score=Decimal("96.00"),
    )
    botw_like = Game(
        id=70,
        public_id="botw-like-three",
        title="BOTW-Like",
        release_date=date(2017, 3, 3),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=65,
        avg_critic_score=Decimal("95.00"),
    )
    elden_like = Game(
        id=71,
        public_id="elden-like-four",
        title="Elden-Like",
        release_date=date(2022, 2, 25),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["gear_chase", "buildcraft"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "tone": ["bleak"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=69,
        avg_critic_score=Decimal("95.00"),
    )
    black_desert_like = Game(
        id=72,
        public_id="black-desert-like-two",
        title="Black-Desert-Like",
        release_date=date(2016, 3, 3),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="mmo_action_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world", "persistent_shared_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "progression_model": ["gear_chase", "buildcraft"],
            "traversal_verbs": ["horseback"],
            "setting": ["high_fantasy"],
            "tone": ["serious"],
            "mode_profile": ["mmo"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        taxonomy_studios=["Pearl Abyss"],
        critic_review_count=38,
        avg_critic_score=Decimal("81.00"),
    )
    witcher_like = Game(
        id=73,
        public_id="witcher-like-two",
        title="Witcher-Like",
        release_date=date(2015, 5, 19),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee", "magic"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["horseback"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "tone": ["serious", "bleak"],
            "mode_profile": ["single_player"],
            "narrative_structure": ["authored_branching"],
            "rules_goals": ["complete_quests"],
            "entity_interaction": ["dialogue_choice"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=90,
        avg_critic_score=Decimal("94.00"),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(
                scalars_all=[totk_like, botw_like, elden_like, black_desert_like, witcher_like]
            ),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=68, limit=5, db=db)

    titles = [item.title for item in resp]
    assert titles == [
        "TOTK-Like",
        "Elden-Like",
        "Black-Desert-Like",
        "Witcher-Like",
        "BOTW-Like",
    ]


@pytest.mark.asyncio
async def test_get_game_similar_prefers_totk_expected_bridge_mix(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=69,
        public_id="totk-anchor",
        title="The Legend of Zelda: Tears of the Kingdom",
        release_date=date(2025, 5, 12),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_secondary_archetypes=["soulslike_action_rpg", "open_world_action_adventure"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric", "encounter_driven"],
            "progression_model": ["buildcraft", "skill_tree"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "entity_interaction": ["construction_placement"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=58,
        avg_critic_score=Decimal("96.00"),
    )
    botw_like = Game(
        id=70,
        public_id="botw-like-two",
        title="BOTW-Like",
        release_date=date(2017, 3, 3),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "world_density": ["handcrafted_discovery"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "combat_structure": ["encounter_driven"],
            "progression_model": ["buildcraft", "skill_tree"],
            "traversal_verbs": ["climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=52,
        avg_critic_score=Decimal("97.00"),
    )
    crimson_like = Game(
        id=71,
        public_id="crimson-like-two",
        title="Crimson-Like",
        release_date=date(2026, 1, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_secondary_archetypes=["western_narrative_rpg", "soulslike_action_rpg", "mmo_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["quest_driven", "buildcraft"],
            "traversal_verbs": ["horseback", "climbing", "gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=44,
        avg_critic_score=Decimal("93.00"),
    )
    elden_like = Game(
        id=72,
        public_id="elden-like-three",
        title="Elden-Like",
        release_date=date(2022, 2, 25),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["buildcraft", "gear_chase"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "dark_fantasy", "mythic"],
            "tone": ["bleak", "heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=61,
        avg_critic_score=Decimal("95.00"),
    )
    gow_like = Game(
        id=73,
        public_id="gow-like",
        title="God-of-War-Like",
        release_date=date(2022, 11, 9),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "combat_structure": ["boss_centric", "encounter_driven"],
            "progression_model": ["skill_tree", "buildcraft"],
            "setting": ["mythic", "high_fantasy"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=57,
        avg_critic_score=Decimal("94.00"),
    )
    pathless_like = Game(
        id=74,
        public_id="pathless-like",
        title="Pathless-Like",
        release_date=date(2020, 11, 12),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["ranged"],
            "progression_model": ["buildcraft"],
            "traversal_verbs": ["gliding"],
            "setting": ["high_fantasy", "mythic"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=62,
        avg_critic_score=Decimal("92.00"),
    )
    just_cause_like = Game(
        id=75,
        public_id="just-cause-like",
        title="Just-Cause-Like",
        release_date=date(2015, 12, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["shooter"],
            "combat_structure": ["encounter_driven"],
            "progression_model": ["buildcraft"],
            "setting": ["modern"],
            "tone": ["pulpy"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=54,
        avg_critic_score=Decimal("85.00"),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(scalars_all=[botw_like, crimson_like, elden_like, gow_like, pathless_like, just_cause_like]),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=69, limit=4, db=db)

    titles = [item.title for item in resp]
    assert titles == ["BOTW-Like", "Crimson-Like", "Elden-Like", "God-of-War-Like"]
    assert "Pathless-Like" not in titles
    assert "Just-Cause-Like" not in titles


@pytest.mark.asyncio
async def test_get_game_similar_prefers_soulslike_lineage_cluster_for_elden_ring_style_anchor(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=80,
        public_id="elden-anchor",
        title="Elden Ring",
        release_date=date(2022, 2, 25),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["gear_chase", "buildcraft"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "dark_fantasy", "mythic"],
            "tone": ["bleak"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        taxonomy_studios=["FromSoftware"],
        critic_review_count=72,
        avg_critic_score=Decimal("96.00"),
    )

    def souls_candidate(game_id: int, title: str, score: str, studios: list[str] | None = None) -> Game:
        return Game(
            id=game_id,
            public_id=title.lower().replace(" ", "-"),
            title=title,
            release_date=date(2019, 1, 1),
            taxonomy_v2_status="computed",
            taxonomy_v2_primary_archetype="soulslike_action_rpg",
            taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
            taxonomy_v2_fingerprint={
                "world_topology": ["open_world"],
                "perspective": ["third_person"],
                "combat_presence": ["dominant"],
                "combat_style": ["melee", "hybrid"],
                "combat_structure": ["boss_centric"],
                "progression_model": ["gear_chase", "buildcraft"],
                "challenge_model": ["soulslike"],
                "setting": ["high_fantasy", "dark_fantasy", "mythic"],
                "tone": ["bleak"],
                "mode_profile": ["single_player"],
                "rules_goals": ["defeat_bosses"],
                "hard_exclusions": [],
                "soft_penalties": [],
            },
            taxonomy_studios=studios or ["FromSoftware"],
            critic_review_count=60,
            avg_critic_score=Decimal(score),
        )

    dark_souls = souls_candidate(81, "Dark Souls Remastered", "90.00")
    dark_souls_iii = souls_candidate(82, "Dark Souls III", "92.00")
    bloodborne = souls_candidate(83, "Bloodborne", "95.00")
    dark_souls_ii = souls_candidate(84, "Dark Souls II", "87.00")
    sekiro = souls_candidate(85, "Sekiro", "94.00")
    witcher_like = Game(
        id=86,
        public_id="witcher-detour",
        title="Witcher Detour",
        release_date=date(2015, 5, 19),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="western_narrative_rpg",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["quest_driven", "buildcraft"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "tone": ["bleak"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=88,
        avg_critic_score=Decimal("93.00"),
    )
    sonic_like = Game(
        id=87,
        public_id="sonic-detour",
        title="Sonic Detour",
        release_date=date(2022, 11, 8),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_action_adventure",
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid"],
            "progression_model": ["skill_tree"],
            "traversal_verbs": ["parkour"],
            "setting": ["whimsical"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=64,
        avg_critic_score=Decimal("91.00"),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(
                scalars_all=[
                    dark_souls,
                    dark_souls_iii,
                    bloodborne,
                    dark_souls_ii,
                    sekiro,
                    witcher_like,
                    sonic_like,
                ]
            ),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=80, limit=5, db=db)

    titles = [item.title for item in resp]
    assert titles == [
        "Bloodborne",
        "Sekiro",
        "Dark Souls III",
        "Dark Souls Remastered",
        "Dark Souls II",
    ]
    assert "Witcher Detour" not in titles
    assert "Sonic Detour" not in titles


@pytest.mark.asyncio
async def test_get_game_similar_soulslike_selector_ignores_secondary_only_when_exact_lineage_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    anchor = Game(
        id=90,
        public_id="elden-anchor-two",
        title="Elden Ring",
        release_date=date(2022, 2, 25),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_family="rpg",
        taxonomy_v2_primary_archetype="soulslike_action_rpg",
        taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["melee", "hybrid"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["gear_chase", "buildcraft"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "dark_fantasy", "mythic"],
            "tone": ["bleak"],
            "mode_profile": ["single_player"],
            "rules_goals": ["defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        taxonomy_studios=["FromSoftware"],
        critic_review_count=72,
        avg_critic_score=Decimal("96.00"),
    )

    def exact_souls(game_id: int, title: str, score: str) -> Game:
        return Game(
            id=game_id,
            public_id=title.lower().replace(" ", "-"),
            title=title,
            release_date=date(2018, 1, 1),
            taxonomy_v2_status="computed",
            taxonomy_v2_primary_archetype="soulslike_action_rpg",
            taxonomy_v2_secondary_archetypes=["open_world_fantasy_action_rpg"],
            taxonomy_v2_fingerprint={
                "world_topology": ["open_world"],
                "perspective": ["third_person"],
                "combat_presence": ["dominant"],
                "combat_style": ["melee", "hybrid"],
                "combat_structure": ["boss_centric"],
                "progression_model": ["gear_chase", "buildcraft"],
                "challenge_model": ["soulslike"],
                "setting": ["high_fantasy", "dark_fantasy", "mythic"],
                "tone": ["bleak"],
                "mode_profile": ["single_player"],
                "rules_goals": ["defeat_bosses"],
                "hard_exclusions": [],
                "soft_penalties": [],
            },
            taxonomy_studios=["FromSoftware"],
            critic_review_count=58,
            avg_critic_score=Decimal(score),
        )

    bloodborne = exact_souls(91, "Bloodborne", "95.00")
    sekiro = exact_souls(92, "Sekiro", "94.00")
    dark_souls_iii = exact_souls(93, "Dark Souls III", "92.00")
    dark_souls = exact_souls(94, "Dark Souls Remastered", "90.00")
    dark_souls_ii = exact_souls(95, "Dark Souls II", "87.00")
    crimson_detour = Game(
        id=96,
        public_id="crimson-detour",
        title="Crimson Detour",
        release_date=date(2026, 1, 1),
        taxonomy_v2_status="computed",
        taxonomy_v2_primary_archetype="open_world_fantasy_action_rpg",
        taxonomy_v2_secondary_archetypes=["soulslike_action_rpg"],
        taxonomy_v2_fingerprint={
            "world_topology": ["open_world"],
            "perspective": ["third_person"],
            "combat_presence": ["dominant"],
            "combat_style": ["hybrid", "melee"],
            "combat_structure": ["boss_centric"],
            "progression_model": ["quest_driven", "gear_chase"],
            "challenge_model": ["soulslike"],
            "setting": ["high_fantasy", "dark_fantasy"],
            "tone": ["heroic"],
            "mode_profile": ["single_player"],
            "rules_goals": ["complete_quests", "defeat_bosses"],
            "hard_exclusions": [],
            "soft_penalties": [],
        },
        critic_review_count=84,
        avg_critic_score=Decimal("98.00"),
    )

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=anchor),
            FakeResult(
                scalars_all=[
                    bloodborne,
                    sekiro,
                    dark_souls_iii,
                    dark_souls,
                    dark_souls_ii,
                    crimson_detour,
                ]
            ),
        ]
    )

    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    resp = await get_game_similar(game_id=90, limit=5, db=db)

    titles = [item.title for item in resp]
    assert titles == [
        "Bloodborne",
        "Sekiro",
        "Dark Souls III",
        "Dark Souls Remastered",
        "Dark Souls II",
    ]
    assert "Crimson Detour" not in titles


@pytest.mark.asyncio
async def test_get_game_steam_activity_prefers_db_history_over_sparse_scraper(
    monkeypatch: pytest.MonkeyPatch,
):
    now = _utc(2026, 3, 16)
    first_sample = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
    last_sample = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
    game = Game(
        id=21,
        title="Marathon",
        steam_app_id=123,
        release_date=date(2026, 3, 10),
        steam_player_24h_peak=62830,
        steam_player_24h_low_observed=25110,
        steam_player_all_time_peak=88337,
        steam_player_all_time_peak_at=_utc(2026, 3, 6),
        steam_player_stats_synced_at=now,
    )
    snapshots = [
        SteamPlayerRangeSnapshot(
            game_id=21,
            sampled_at=last_sample,
            players_24h_high=57000,
            players_24h_low=21000,
        ),
        SteamPlayerRangeSnapshot(
            game_id=21,
            sampled_at=first_sample,
            players_24h_high=55000,
            players_24h_low=20000,
        ),
    ]
    sparse_scraper_activity = ScraperSteamActivity(
        points=[
            SteamPlayerPoint(
                sampled_at=last_sample,
                observed_24h_high=57000,
                observed_24h_low=21000,
                latest_players=54000,
            )
        ],
        storage_points=[
            SteamPlayerPoint(
                sampled_at=last_sample,
                observed_24h_high=57000,
                observed_24h_low=21000,
                latest_players=54000,
            )
        ],
        marker_source_points=[
            {
                "sampled_at": last_sample,
                "concurrent_players": 54000,
            }
        ],
        summary_updates={
            "steam_player_24h_peak": 57000,
            "steam_player_24h_low_observed": 21000,
            "steam_player_all_time_peak": 54000,
            "steam_player_all_time_peak_at": last_sample,
            "steam_player_stats_synced_at": last_sample,
        },
    )

    class FakePlayerScraperClient:
        is_configured = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def get_steam_activity(self, steam_app_id: int, *, limit: int, window: str = "1y"):
            return sparse_scraper_activity

    sync_mock = AsyncMock(
        return_value={
            "range_snapshots_upserted": 1,
            "player_snapshots_inserted": 1,
            "summary_updated": True,
        }
    )
    monkeypatch.setattr("app.routers.games.PlayerScraperClient", FakePlayerScraperClient)
    monkeypatch.setattr("app.routers.games.sync_scraper_activity_to_db", sync_mock)
    monkeypatch.setattr("app.routers.games.get_cached", AsyncMock(return_value=None))
    monkeypatch.setattr("app.routers.games.set_cached", AsyncMock(return_value=True))

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalars_all=snapshots),
            FakeResult(
                all_rows=[
                    (first_sample, 53000),
                    (last_sample, 54000),
                ]
            ),
        ]
    )

    resp = await get_game_steam_activity(game_id=21, limit=10000, db=db)

    sync_mock.assert_awaited_once()
    assert db.flush_calls == 1
    assert [point.observed_24h_high for point in resp.points] == [55000, 57000]
    assert [point.observed_24h_low for point in resp.points] == [20000, 21000]
    assert [point.latest_players for point in resp.points] == [53000, 54000]
    assert resp.summary.steam_player_all_time_peak == 57000
    assert resp.summary.steam_player_all_time_peak_at == last_sample
    assert resp.summary.steam_player_all_time_peak >= resp.summary.steam_player_24h_peak


@pytest.mark.asyncio
async def test_get_game_steam_activity_ignores_legacy_pre_release_range_points_without_trusted_snapshots():
    now = _utc(2026, 3, 19)
    game = Game(
        id=12,
        title="Dragonkin: The Banished",
        steam_app_id=456,
        release_date=date(2026, 3, 16),
        steam_player_24h_peak=641,
        steam_player_24h_low_observed=282,
        steam_player_all_time_peak=641,
        steam_player_all_time_peak_at=_utc(2026, 3, 19),
        steam_player_stats_synced_at=now,
    )
    legacy_range_snapshots = [
        SteamPlayerRangeSnapshot(
            game_id=12,
            sampled_at=datetime(2026, 2, 4, 0, 0, tzinfo=timezone.utc),
            players_24h_high=40,
            players_24h_low=20,
        ),
        SteamPlayerRangeSnapshot(
            game_id=12,
            sampled_at=datetime(2026, 3, 3, 0, 0, tzinfo=timezone.utc),
            players_24h_high=400,
            players_24h_low=100,
        ),
    ]

    db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalars_all=legacy_range_snapshots),
            FakeResult(all_rows=[]),
            FakeResult(scalars_all=[]),
        ]
    )

    resp = await get_game_steam_activity(game_id=12, limit=10000, db=db)

    assert resp.points == []
    assert resp.summary.steam_player_24h_peak is None
    assert resp.summary.steam_player_24h_low_observed is None
    assert resp.summary.steam_player_all_time_peak is None
    assert resp.summary.steam_player_all_time_peak_at is None
    assert not any(marker.marker_type == "first_tracked" for marker in resp.markers)


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

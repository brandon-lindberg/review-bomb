"""Response caching on the hot read endpoints.

These endpoints are the heaviest public DB/CPU paths (see 2026-07 CPU/memory
incidents): repeated identical requests must be served from cache without
touching the database while the TTL holds.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.models import Game, Journalist, Outlet, Review
from app.routers.games import get_game_reviews
from app.routers.outlets import get_outlet_reviews

_UNSET = object()


class FakeResult:
    def __init__(
        self,
        *,
        scalar_one_or_none: Any = _UNSET,
        scalar: Any = _UNSET,
        all_rows: Any = _UNSET,
    ):
        self._scalar_one_or_none = scalar_one_or_none
        self._scalar = scalar
        self._all_rows = all_rows

    def scalar_one_or_none(self):
        assert self._scalar_one_or_none is not _UNSET
        return self._scalar_one_or_none

    def scalar(self):
        assert self._scalar is not _UNSET
        return self._scalar

    def all(self):
        assert self._all_rows is not _UNSET
        return self._all_rows


class FakeAsyncSession:
    def __init__(self, results: list[Any] | None = None):
        self._results = list(results or [])
        self.execute_calls = 0

    async def execute(self, statement, params=None):
        self.execute_calls += 1
        if not self._results:
            raise AssertionError(
                "unexpected database query: this request should have been cache-served"
            )
        return self._results.pop(0)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


def _game_review_rows():
    game = Game(id=1, title="Example", release_date=date(2026, 2, 20))
    journalist = Journalist(id=2, name="Critic", image_url=None)
    outlet = Outlet(id=3, name="Outlet")
    review = Review(
        id=4,
        journalist_id=2,
        game_id=1,
        outlet_id=3,
        score_raw="8",
        score_scale="10",
        score_normalized=Decimal("80.00"),
        cached_disparity_steam=Decimal("10.00"),
        cached_disparity_metacritic=Decimal("-5.00"),
        published_at=_utc(2026, 2, 21),
    )
    return game, journalist, outlet, review


@pytest.mark.asyncio
async def test_game_reviews_second_identical_request_is_cache_served():
    game, journalist, outlet, review = _game_review_rows()

    first_db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, journalist, outlet)]),
        ]
    )
    first = await get_game_reviews.__wrapped__(
        request=SimpleNamespace(),
        game_id=1,
        page=1,
        per_page=20,
        review_timing=None,
        sort_order=None,
        db=first_db,
    )
    assert first.total == 1
    assert first_db.execute_calls == 3

    # An empty fake session raises on any query: the repeat request must be
    # answered entirely from the response cache.
    second = await get_game_reviews.__wrapped__(
        request=SimpleNamespace(),
        game_id=1,
        page=1,
        per_page=20,
        review_timing=None,
        sort_order=None,
        db=FakeAsyncSession(),
    )
    assert second.total == 1
    assert second.items[0].score_normalized == first.items[0].score_normalized
    assert second.items[0].journalist_name == "Critic"


@pytest.mark.asyncio
async def test_game_reviews_cache_varies_by_pagination_params():
    game, journalist, outlet, review = _game_review_rows()

    await get_game_reviews.__wrapped__(
        request=SimpleNamespace(),
        game_id=1,
        page=1,
        per_page=20,
        review_timing=None,
        sort_order=None,
        db=FakeAsyncSession(
            results=[
                FakeResult(scalar_one_or_none=game),
                FakeResult(scalar=1),
                FakeResult(all_rows=[(review, journalist, outlet)]),
            ]
        ),
    )

    # Different per_page must miss the cache and hit the database again.
    different_db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=game),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, journalist, outlet)]),
        ]
    )
    await get_game_reviews.__wrapped__(
        request=SimpleNamespace(),
        game_id=1,
        page=1,
        per_page=500,
        review_timing=None,
        sort_order=None,
        db=different_db,
    )
    assert different_db.execute_calls == 3


@pytest.mark.asyncio
async def test_outlet_reviews_second_identical_request_is_cache_served():
    game, journalist, _outlet, review = _game_review_rows()

    first_db = FakeAsyncSession(
        results=[
            FakeResult(scalar_one_or_none=3),
            FakeResult(scalar=1),
            FakeResult(all_rows=[(review, journalist, game)]),
        ]
    )
    first = await get_outlet_reviews.__wrapped__(
        request=SimpleNamespace(),
        outlet_id=3,
        page=1,
        per_page=20,
        db=first_db,
    )
    assert first.total == 1

    second = await get_outlet_reviews.__wrapped__(
        request=SimpleNamespace(),
        outlet_id=3,
        page=1,
        per_page=20,
        db=FakeAsyncSession(),
    )
    assert second.total == 1
    assert second.items[0].game_title == "Example"

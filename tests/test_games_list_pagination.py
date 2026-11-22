"""Pagination totals on the games list endpoint.

`GET /api/v1/games` used to carry its row count as a `count(*) OVER ()` on the
list query. A window function has to buffer and fully sort every matching row
before LIMIT applies, so asking for the home page's 5 newest games cost the same
as asking for all ~15k: measured at 1.8-8.6s cold against production, while the
three sibling panels on the same page answered in under a second.

The count now runs as its own statement behind its own cache entry. These tests
pin the two properties that make that worthwhile: the list query must not
re-acquire a window count, and the count must not be re-run per page or per sort
order.
"""

from typing import Any

import pytest

from app.models.models import Game
from app.routers.games import _count_games_matching, list_games

_UNSET = object()


class FakeScalars:
    def __init__(self, items: list[Any]):
        self._items = items

    def all(self):
        return self._items


class FakeResult:
    def __init__(self, *, scalar: Any = _UNSET, scalars_all: Any = _UNSET):
        self._scalar = scalar
        self._scalars_all = scalars_all

    def scalar(self):
        assert self._scalar is not _UNSET, "scalar() was not expected here"
        return self._scalar

    def scalars(self):
        assert self._scalars_all is not _UNSET, "scalars() was not expected here"
        return FakeScalars(self._scalars_all)

    def __iter__(self):
        return iter(())


class FakeAsyncSession:
    def __init__(self, results: list[Any] | None = None):
        self._results = list(results or [])
        self.statements: list[Any] = []

    async def execute(self, statement, params=None):
        self.statements.append(statement)
        if not self._results:
            return FakeResult(scalars_all=[])
        return self._results.pop(0)


def _list_args(*, page: int, per_page: int) -> dict[str, Any]:
    """Explicit values for every parameter.

    Calling the handler directly bypasses FastAPI, so any argument left out
    arrives as an unresolved ``Query`` object rather than its default.
    """
    return {
        "page": page,
        "per_page": per_page,
        "year": None,
        "search": None,
        "sort_by": "release_date",
        "sort_order": "desc",
    }


def _compiled(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": False}))


@pytest.mark.asyncio
async def test_list_query_carries_no_window_count():
    """The list statement must select rows only, so the planner can stop at LIMIT."""
    db = FakeAsyncSession(
        results=[
            FakeResult(scalars_all=[]),  # the list query
            FakeResult(scalar=15101),  # the count query
        ]
    )

    await list_games(**_list_args(page=1, per_page=5), db=db)

    list_sql = _compiled(db.statements[0])
    assert "OVER (" not in list_sql.upper(), list_sql
    assert "LIMIT" in list_sql.upper()

    count_sql = _compiled(db.statements[1])
    assert count_sql.upper().startswith("SELECT COUNT(")


@pytest.mark.asyncio
async def test_total_comes_from_the_count_query():
    db = FakeAsyncSession(
        results=[
            FakeResult(scalars_all=[]),
            FakeResult(scalar=15101),
        ]
    )

    response = await list_games(**_list_args(page=1, per_page=5), db=db)

    assert response.total == 15101
    assert response.total_pages == (15101 + 4) // 5


@pytest.mark.asyncio
async def test_empty_deep_page_still_reports_the_real_total():
    """The old code only counted on an empty page; the count is unconditional now."""
    db = FakeAsyncSession(
        results=[
            FakeResult(scalars_all=[]),
            FakeResult(scalar=15101),
        ]
    )

    response = await list_games(**_list_args(page=9000, per_page=5), db=db)

    assert response.total == 15101
    assert response.items == []


@pytest.mark.asyncio
async def test_count_is_shared_across_pages_and_sort_orders():
    """One cached count serves every page and both directions of every sort."""
    filters = [Game.critic_review_count >= 1]

    db = FakeAsyncSession(results=[FakeResult(scalar=15101)])
    first = await _count_games_matching(db, filters=filters, year=None, search=None)

    # No results queued: a second DB round trip would raise on scalar().
    warm = FakeAsyncSession()
    again = await _count_games_matching(warm, filters=filters, year=None, search=None)

    assert first == again == 15101
    assert warm.statements == []


@pytest.mark.asyncio
async def test_count_is_keyed_by_filters():
    """A year or search filter changes the population, so it must not reuse the count."""
    filters = [Game.critic_review_count >= 1]

    db = FakeAsyncSession(results=[FakeResult(scalar=15101)])
    await _count_games_matching(db, filters=filters, year=None, search=None)

    filtered = FakeAsyncSession(results=[FakeResult(scalar=412)])
    total_2016 = await _count_games_matching(
        filtered, filters=filters, year=2016, search=None
    )

    assert total_2016 == 412
    assert len(filtered.statements) == 1
    assert "EXTRACT" in _compiled(filtered.statements[0]).upper()


@pytest.mark.asyncio
async def test_count_applies_the_same_filters_as_the_list():
    db = FakeAsyncSession(results=[FakeResult(scalar=7)])

    await _count_games_matching(
        db,
        filters=[Game.critic_review_count >= 3],
        year=None,
        search="halo",
    )

    sql = _compiled(db.statements[0]).upper()
    assert "CRITIC_REVIEW_COUNT" in sql
    assert "LIKE" in sql
    assert "REGEXP_REPLACE" not in sql


@pytest.mark.asyncio
async def test_catalog_search_can_find_an_edition_before_scores_arrive():
    db = FakeAsyncSession(results=[FakeResult(scalars_all=[]), FakeResult(scalar=1)])
    args = _list_args(page=1, per_page=5)
    args["search"] = "Ocarina of Time Remake"
    await list_games(**args, db=db)

    for statement in db.statements:
        predicate = str(statement.whereclause)
        assert predicate == "games.opencritic_id = :opencritic_id_1"
        assert statement.whereclause.compile().params == {"opencritic_id_1": 21344}

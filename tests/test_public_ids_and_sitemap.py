from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.models import Game
from app.public_ids import parse_legacy_numeric_id, parse_slugged_identifier, resolve_entity_by_identifier
from app.routers.stats import get_sitemap_data


_UNSET = object()


class FakeResult:
    def __init__(self, *, scalar_one_or_none=_UNSET, all_rows=_UNSET):
        self._scalar_one_or_none = scalar_one_or_none
        self._all_rows = all_rows

    def scalar_one_or_none(self):
        if self._scalar_one_or_none is _UNSET:
            raise AssertionError("scalar_one_or_none() was not expected for this fake result")
        return self._scalar_one_or_none

    def all(self):
        if self._all_rows is _UNSET:
            raise AssertionError("all() was not expected for this fake result")
        return self._all_rows


class FakeAsyncSession:
    def __init__(self, results):
        self._results = list(results)
        self.execute_calls = []

    async def execute(self, statement, params=None):
        self.execute_calls.append((statement, params))
        result = self._results.pop(0)
        if callable(result):
            return result(statement, params)
        return result


def test_parse_legacy_numeric_id_accepts_positive_integers_only():
    assert parse_legacy_numeric_id("18971") == 18971
    assert parse_legacy_numeric_id("0") is None
    assert parse_legacy_numeric_id("abc123") is None


def test_parse_slugged_identifier_extracts_frontend_canonical_suffix():
    assert parse_slugged_identifier("starfield-terran-armada--708a3ae61db948c9a249b1ef98ee25a9") == "708a3ae61db948c9a249b1ef98ee25a9"
    assert parse_slugged_identifier("high-guard--18971") == "18971"
    assert parse_slugged_identifier("abc123") == "abc123"


@pytest.mark.asyncio
async def test_resolve_entity_by_identifier_keeps_bare_public_id_lookup():
    entity = SimpleNamespace(id=7, public_id="abc123")
    db = FakeAsyncSession([FakeResult(scalar_one_or_none=entity)])

    resolved = await resolve_entity_by_identifier(db, Game, "abc123")

    assert resolved is entity
    statement = str(db.execute_calls[0][0])
    assert "games.public_id" in statement
    assert " OR " not in statement


@pytest.mark.asyncio
async def test_resolve_entity_by_identifier_supports_slugged_public_id_lookup():
    entity = SimpleNamespace(id=8, public_id="708a3ae61db948c9a249b1ef98ee25a9")
    db = FakeAsyncSession([FakeResult(scalar_one_or_none=entity)])

    resolved = await resolve_entity_by_identifier(
        db,
        Game,
        "starfield-terran-armada--708a3ae61db948c9a249b1ef98ee25a9",
    )

    assert resolved is entity
    statement = str(db.execute_calls[0][0])
    assert "games.public_id" in statement
    assert " OR " not in statement


@pytest.mark.asyncio
async def test_resolve_entity_by_identifier_supports_numeric_legacy_lookup():
    db = FakeAsyncSession([FakeResult(scalar_one_or_none=18971)])

    resolved = await resolve_entity_by_identifier(db, Game, "18971")

    assert resolved.id == 18971
    assert resolved.public_id == "18971"
    statement = str(db.execute_calls[0][0])
    assert "games.public_id" in statement
    assert " OR " in statement
    assert "games.id" in statement


@pytest.mark.asyncio
async def test_get_sitemap_data_returns_entry_objects_and_legacy_arrays():
    db = FakeAsyncSession(
        [
            FakeResult(all_rows=[(1, "journa1", "Joe Terrible")]),
            FakeResult(all_rows=[(2, "outlet2", "Kotaku")]),
            FakeResult(all_rows=[(3, "game3", "High Guard")]),
        ]
    )

    payload = await get_sitemap_data(db)

    assert payload["journalist_public_ids"] == ["journa1"]
    assert payload["outlet_public_ids"] == ["outlet2"]
    assert payload["game_public_ids"] == ["game3"]

    assert payload["journalist_entries"] == [
        {"public_id": "journa1", "name": "Joe Terrible"}
    ]
    assert payload["outlet_entries"] == [
        {"public_id": "outlet2", "name": "Kotaku"}
    ]
    assert payload["game_entries"] == [
        {"public_id": "game3", "title": "High Guard"}
    ]

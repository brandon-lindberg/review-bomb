from __future__ import annotations

import os

os.environ["DEBUG"] = "false"

import pytest
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from app.models.models import Game
from app.routers.search import search
from app.services.title_search import compact_search_value, game_title_search_clause, text_search_clause


def test_compact_search_value_removes_punctuation_and_spacing():
    assert compact_search_value("baldurs gate") == "baldursgate"
    assert compact_search_value("Baldur's Gate 3") == "baldursgate3"
    assert compact_search_value("  Baldur’s   Gate  ") == "baldursgate"


def test_search_match_clause_matches_literal_and_compact_normalized_terms():
    clause = text_search_clause(Game.title, "baldurs gate")

    compiled = str(
        clause.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "lower(games.title) LIKE '%%baldurs gate%%'" in compiled
    assert "regexp_replace(lower(games.title), '[^a-z0-9]+', '', 'g')" in compiled
    assert "LIKE '%%baldursgate%%'" in compiled


@pytest.mark.parametrize("query", [
    "The Legend of Zelda Ocarina Time Remake",
    "Ocarina of Time (Remake)",
    "Ocarina of Time Switch 2",
])
def test_remake_alias_search_matches_the_exact_game(query):
    clause = game_title_search_clause(query)
    assert str(clause) == "games.opencritic_id = :opencritic_id_1"
    assert clause.compile().params == {"opencritic_id_1": 21344}


@pytest.mark.asyncio
async def test_search_ignores_whitespace_only_queries_without_database_calls():
    class FakeSession:
        execute_count = 0

        async def execute(self, _statement):
            self.execute_count += 1
            raise AssertionError("whitespace-only search should not query the database")

    db = FakeSession()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )

    result = await search(request=request, q="   ", limit=10, db=db)

    assert result.journalists == []
    assert result.outlets == []
    assert result.games == []
    assert db.execute_count == 0

"""Match stage queue: launching games first, console-only misses retried weekly.

The stage takes 300 games per run, newest-added first. Console exclusives never
get a Steam ID, so they were re-searched every run while their OpenCritic ID was
recent, filled the batch, and pushed games added months before launch (most big
releases) past the limit exactly when they became matchable.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

import app.services.game_matcher as game_matcher
from app.models.models import Game
from app.services.game_matcher import STEAM_SEARCH_FAILED, GameMatcher
from app.services.steam import SteamService
from app.services.sync_orchestrator import SyncOrchestrator

NOW = datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc)


def _compile(clause) -> str:
    return " ".join(
        str(
            clause.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    )


def _orchestrator(db=None) -> SyncOrchestrator:
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = db
    return orchestrator


def test_windowed_queue_puts_newly_matchable_games_first():
    query, _ = _orchestrator()._build_match_query(days=10, limit=300, now=NOW)
    sql = _compile(query)

    order_by = sql[sql.index("ORDER BY"):]
    assert order_by.startswith("ORDER BY CASE WHEN"), order_by
    assert "THEN 0 ELSE 1 END" in order_by
    assert order_by.index("END") < order_by.index("games.created_at DESC")
    assert sql.endswith("LIMIT 300")


def test_only_window_only_games_wait_for_the_weekly_retry():
    query, _ = _orchestrator()._build_match_query(days=10, limit=300, now=NOW)
    where = _compile(query)
    where = where[where.index("WHERE"):where.index("ORDER BY")]

    retry_due = (
        "(games.steam_match_last_attempted_at IS NULL OR "
        "games.steam_match_last_attempted_at < '2026-09-06 00:00:00+00:00')"
    )
    assert where.count("steam_match_last_attempted_at IS NULL") == 1
    # The retry gate is ANDed onto the OpenCritic ID window and nothing else,
    # so launches, new additions and pre-release games are searched every run.
    assert re.search(
        r"games\.opencritic_id >= \(SELECT max\(games\.opencritic_id\).*?\) - 2500 AND "
        + re.escape(retry_due),
        where,
    ), where


def test_unwindowed_match_keeps_its_original_selection():
    query, _ = _orchestrator()._build_match_query(days=None, limit=None, now=NOW)
    sql = _compile(query)

    assert "steam_match_last_attempted_at" not in sql
    assert "CASE" not in sql
    assert "ORDER BY games.release_date DESC NULLS LAST, games.id DESC" in sql


def test_loading_games_never_selects_the_match_attempt_column():
    # The web service can deploy the model before the pipeline migrates the
    # column in. If a plain Game load selected it, every game page would 500
    # until the next pipeline run.
    assert "steam_match_last_attempted_at" not in _compile(select(Game))


class _FakeResult:
    def __init__(self, games):
        self._games = games

    def scalars(self):
        return self

    def all(self):
        return self._games


class _FakeDb:
    def __init__(self, games):
        self._games = games

    async def execute(self, query):
        return _FakeResult(self._games)

    async def commit(self):
        return None


def _game(title):
    return SimpleNamespace(
        title=title,
        release_date=date(2026, 1, 1),
        opencritic_id=1,
        steam_app_id=None,
        metacritic_slug="already-set",
        steam_match_last_attempted_at=None,
    )


@pytest.mark.asyncio
async def test_match_attempt_is_recorded_unless_steam_never_answered(monkeypatch):
    outcomes = {
        "Console Exclusive": {"steam_app_id": None, "steam_match_reason": "no_search_results"},
        "Steam Outage": {"steam_app_id": None, "steam_match_reason": STEAM_SEARCH_FAILED},
        "Matcher Crash": RuntimeError("boom"),
    }

    class FakeMatcher:
        def __init__(self):
            self.steam_service = SimpleNamespace(aclose=self._aclose)

        async def _aclose(self):
            return None

        async def match_game(self, title, release_date=None, opencritic_id=None):
            outcome = outcomes[title]
            if isinstance(outcome, Exception):
                raise outcome
            return {**outcome, "metacritic_slug": "already-set"}

    monkeypatch.setattr(game_matcher, "GameMatcher", FakeMatcher)
    games = [_game(title) for title in outcomes]
    orchestrator = _orchestrator(_FakeDb(games))

    stats = await orchestrator.match_games_to_steam(limit=300, days=10)

    attempted = {game.title: game.steam_match_last_attempted_at for game in games}
    assert attempted["Console Exclusive"] is not None
    assert attempted["Steam Outage"] is None
    assert attempted["Matcher Crash"] is None
    assert stats["failed"] == 1


class _SearchSteam:
    def __init__(self, responses):
        self._responses = responses

    async def search_games_or_none(self, query):
        return self._responses.get(query, [])

    async def get_app_details(self, app_id):
        return None


@pytest.mark.asyncio
async def test_failed_steam_search_is_not_reported_as_a_miss():
    matcher = GameMatcher(steam_service=_SearchSteam({"Hollow Knight": None}))

    assert await matcher.find_steam_match("Hollow Knight") == (None, STEAM_SEARCH_FAILED)


@pytest.mark.asyncio
async def test_partial_search_failure_with_no_results_counts_as_failed():
    # One fallback query failed and the rest came back empty: Steam may have
    # had the game behind the failed query, so it is not a confirmed miss.
    matcher = GameMatcher(steam_service=_SearchSteam({"God of War: Sons of Sparta": None}))

    _, reason = await matcher.find_steam_match("God of War: Sons of Sparta")

    assert reason == STEAM_SEARCH_FAILED


@pytest.mark.asyncio
async def test_empty_steam_search_is_still_a_miss():
    matcher = GameMatcher(steam_service=_SearchSteam({}))

    assert await matcher.find_steam_match("Hollow Knight") == (None, "no_search_results")


@pytest.mark.asyncio
async def test_steam_search_distinguishes_failure_from_no_results():
    service = object.__new__(SteamService)
    responses = {"down": None, "empty": {"items": []}}

    async def fake_request(url, params=None, **kwargs):
        return responses[params["term"]]

    service._request = fake_request

    assert await service.search_games_or_none("down") is None
    assert await service.search_games_or_none("empty") == []
    # The existing list-returning API is unchanged for its other callers.
    assert await service.search_games("down") == []

from datetime import date

import pytest

from app.models.models import Game
from app.services.steam_catalog import (
    TrackedSteamGame,
    ensure_tracked_steam_games,
    load_tracked_steam_games,
)


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeAsyncSession:
    def __init__(self, results):
        self._results = list(results)
        self.executed = []
        self.added = []
        self.flush_count = 0

    async def execute(self, statement):
        self.executed.append(statement)
        return _FakeResult(self._results.pop(0) if self._results else None)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1


class _FakeSteamService:
    def __init__(self, app_details_by_id):
        self._app_details_by_id = dict(app_details_by_id)

    async def get_app_details(self, app_id: int):
        return self._app_details_by_id.get(app_id)


def test_load_tracked_steam_games_includes_pubg():
    tracked_games = load_tracked_steam_games()
    pubg = next(game for game in tracked_games if game.steam_app_id == 578080)

    assert pubg.title == "PUBG: BATTLEGROUNDS"
    assert "PLAYERUNKNOWN'S BATTLEGROUNDS" in pubg.aliases
    assert pubg.release_date == date(2017, 12, 21)


def test_load_tracked_steam_games_includes_supraworld_early_access():
    tracked_games = load_tracked_steam_games()
    supraworld = next(game for game in tracked_games if game.steam_app_id == 1869290)

    assert supraworld.title == "Supraworld"
    assert supraworld.release_date == date(2025, 8, 15)
    assert "early access" in (supraworld.reason or "").lower()


@pytest.mark.asyncio
async def test_ensure_tracked_steam_games_creates_curated_fallback_when_steam_is_unavailable():
    tracked_game = TrackedSteamGame(
        steam_app_id=578080,
        title="PUBG: BATTLEGROUNDS",
        aliases=("PLAYERUNKNOWN'S BATTLEGROUNDS",),
        release_date=date(2017, 12, 21),
    )
    session = _FakeAsyncSession([None, None])
    steam_service = _FakeSteamService({})

    stats = await ensure_tracked_steam_games(
        session,
        steam_service,
        tracked_games=[tracked_game],
    )

    assert stats == {
        "created": 1,
        "updated": 0,
        "fallback_used": 1,
    }
    assert len(session.added) == 1
    created_game = session.added[0]
    assert isinstance(created_game, Game)
    assert created_game.title == "PUBG: BATTLEGROUNDS"
    assert created_game.steam_app_id == 578080
    assert created_game.release_date == date(2017, 12, 21)
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_ensure_tracked_steam_games_reuses_alias_match_and_applies_steam_metadata():
    tracked_game = TrackedSteamGame(
        steam_app_id=578080,
        title="PUBG: BATTLEGROUNDS",
        aliases=("PLAYERUNKNOWN'S BATTLEGROUNDS",),
        release_date=date(2017, 12, 21),
    )
    existing_game = Game(
        title="PLAYERUNKNOWN'S BATTLEGROUNDS",
        steam_app_id=None,
        release_date=None,
        description=None,
        image_url=None,
    )
    session = _FakeAsyncSession([None, existing_game])
    steam_service = _FakeSteamService(
        {
            578080: {
                "name": "PLAYERUNKNOWN'S BATTLEGROUNDS",
                "short_description": "Land, loot, survive.",
                "detailed_description": "<p>Drop into a battle royale sandbox.</p>",
                "release_date": {
                    "coming_soon": False,
                    "date": "Dec 21, 2017",
                },
                "header_image": "https://cdn.example/pubg.jpg",
            }
        }
    )

    stats = await ensure_tracked_steam_games(
        session,
        steam_service,
        tracked_games=[tracked_game],
    )

    assert stats == {
        "created": 0,
        "updated": 1,
        "fallback_used": 0,
    }
    assert not session.added
    assert existing_game.title == "PUBG: BATTLEGROUNDS"
    assert existing_game.steam_app_id == 578080
    assert existing_game.release_date == date(2017, 12, 21)
    assert existing_game.description == "Land, loot, survive."
    assert existing_game.steam_short_description == "Land, loot, survive."
    assert existing_game.steam_detailed_description == "Drop into a battle royale sandbox."
    assert existing_game.image_url == "https://cdn.example/pubg.jpg"
    assert session.flush_count == 1

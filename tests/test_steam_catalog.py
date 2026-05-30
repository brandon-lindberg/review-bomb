from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.models import Game
from app.services.steam import SteamService
from app.services.steam_catalog import (
    TrackedSteamGame,
    _should_update_release_date,
    ensure_tracked_steam_games,
    load_tracked_steam_games,
    reconcile_stale_release_dates,
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


def test_should_update_release_date_blocks_past_to_future_without_signal():
    today = datetime.now(timezone.utc).date()
    existing = today - timedelta(days=30)
    candidate = today + timedelta(days=60)

    # Without an authoritative "still upcoming" signal we must not regress a
    # seemingly-released date to a future one (remaster/port placeholder guard).
    assert _should_update_release_date(existing, candidate) is False


def test_should_update_release_date_corrects_stale_past_when_coming_soon():
    today = datetime.now(timezone.utc).date()
    # Stale announced date that already passed; Steam still says coming_soon.
    existing = today - timedelta(days=30)
    candidate = today + timedelta(days=60)

    assert (
        _should_update_release_date(existing, candidate, source_coming_soon=True)
        is True
    )


def test_transform_app_details_surfaces_coming_soon_announced_date():
    data = {
        "name": "Mina the Hollower",
        "release_date": {"coming_soon": True, "date": "May 29, 2026"},
    }

    transformed = SteamService.transform_app_details(data, 1875580)

    # release_date keeps its "already released" meaning (None while upcoming)...
    assert transformed["release_date"] is None
    # ...but the concrete announced date + coming_soon flag are now available.
    assert transformed["release_coming_soon"] is True
    assert transformed["announced_release_date"] == date(2026, 5, 29)


class _FakeScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeReconcileSession:
    def __init__(self, games):
        self._games = list(games)
        self.flush_count = 0

    async def execute(self, statement):
        return _FakeScalarResult(self._games)

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_reconcile_corrects_delayed_game_with_stale_past_date():
    today = datetime.now(timezone.utc).date()
    announced = today + timedelta(days=60)

    game = Game(
        title="Mina the Hollower",
        steam_app_id=1875580,
        release_date=today - timedelta(days=30),
    )
    game.id = 42
    session = _FakeReconcileSession([game])
    steam_service = _FakeSteamService(
        {
            1875580: {
                "name": "Mina the Hollower",
                "release_date": {
                    "coming_soon": True,
                    "date": announced.strftime("%b %d, %Y"),
                },
            }
        }
    )

    stats = await reconcile_stale_release_dates(session, steam_service)

    assert stats["corrected"] == 1
    assert game.release_date == announced
    assert session.flush_count == 1
    assert stats["corrections"][0].game_id == 42


@pytest.mark.asyncio
async def test_reconcile_dry_run_does_not_mutate():
    today = datetime.now(timezone.utc).date()
    announced = today + timedelta(days=60)
    original = today - timedelta(days=30)

    game = Game(title="Mina the Hollower", steam_app_id=1875580, release_date=original)
    game.id = 7
    session = _FakeReconcileSession([game])
    steam_service = _FakeSteamService(
        {
            1875580: {
                "name": "Mina the Hollower",
                "release_date": {
                    "coming_soon": True,
                    "date": announced.strftime("%b %d, %Y"),
                },
            }
        }
    )

    stats = await reconcile_stale_release_dates(session, steam_service, dry_run=True)

    assert stats["corrected"] == 1
    assert game.release_date == original
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_reconcile_leaves_released_games_untouched():
    today = datetime.now(timezone.utc).date()

    game = Game(
        title="Released Game",
        steam_app_id=999,
        release_date=today - timedelta(days=30),
    )
    game.id = 1
    session = _FakeReconcileSession([game])
    # Steam reports the game as actually released -> no anomaly, no change.
    steam_service = _FakeSteamService(
        {
            999: {
                "name": "Released Game",
                "release_date": {"coming_soon": False, "date": "Jan 01, 2020"},
            }
        }
    )

    stats = await reconcile_stale_release_dates(session, steam_service)

    assert stats["corrected"] == 0
    assert game.release_date == today - timedelta(days=30)

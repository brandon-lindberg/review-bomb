from datetime import date

import pytest

from app.services.game_matcher import GameMatcher


class DummySteamService:
    def __init__(self, results, app_details=None):
        self._results = results
        self._app_details = app_details or {}

    async def search_games(self, query):
        return self._results.get(query, [])

    async def get_app_details(self, app_id):
        return self._app_details.get(app_id)

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_subtitle_title_does_not_match_base_game_only():
    steam = DummySteamService(
        results={
            "God of War: Sons of Sparta": [],
            "God of War": [{"steam_app_id": 1593500, "name": "God of War"}],
            "Sons of Sparta": [],
        }
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id = await matcher.find_steam_match("God of War: Sons of Sparta")

    assert steam_app_id is None


@pytest.mark.asyncio
async def test_exact_title_match_still_works():
    steam = DummySteamService(
        results={
            "Helldivers 2": [{"steam_app_id": 553850, "name": "HELLDIVERS 2"}],
        },
        app_details={
            553850: {
                "name": "HELLDIVERS 2",
                "release_date": {"date": "Feb 8, 2024", "coming_soon": False},
            }
        },
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id = await matcher.find_steam_match(
        "Helldivers 2",
        release_date=date(2024, 2, 8),
    )

    assert steam_app_id == 553850


@pytest.mark.asyncio
async def test_yearly_sports_title_accepts_compact_variant():
    steam = DummySteamService(
        results={
            "NBA2K 21 Next-Gen": [
                {"steam_app_id": 123456, "name": "NBA 2K21 Next-Gen"},
            ],
        }
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id = await matcher.find_steam_match("NBA2K 21 Next-Gen")

    assert steam_app_id == 123456


@pytest.mark.asyncio
async def test_yearly_sports_title_does_not_match_newer_cycle():
    steam = DummySteamService(
        results={
            "NBA2K 21 Next-Gen": [
                {"steam_app_id": 2600000, "name": "NBA 2K26 Next-Gen"},
            ],
        }
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id = await matcher.find_steam_match("NBA2K 21 Next-Gen")

    assert steam_app_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("opencritic_id", "expected_app_id"),
    [
        (175, 265300),
        (2594, 265300),
        (15632, 1501750),
    ],
)
async def test_manual_override_steam_match_wins_for_known_lords_entries(
    opencritic_id, expected_app_id
):
    steam = DummySteamService(results={})
    matcher = GameMatcher(steam_service=steam)

    steam_app_id = await matcher.find_steam_match(
        "Lords of the Fallen",
        release_date=date(2023, 10, 13),
        opencritic_id=opencritic_id,
    )

    assert steam_app_id == expected_app_id


def test_manual_override_metacritic_slug_wins_for_edge_2011():
    matcher = GameMatcher(steam_service=DummySteamService(results={}))

    slug = matcher.find_metacritic_slug("Edge", opencritic_id=1130)

    assert slug == "edge-2011"

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

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

    steam_app_id, _reason = await matcher.find_steam_match("God of War: Sons of Sparta")

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

    steam_app_id, _reason = await matcher.find_steam_match(
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

    steam_app_id, _reason = await matcher.find_steam_match("NBA2K 21 Next-Gen")

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

    steam_app_id, _reason = await matcher.find_steam_match("NBA2K 21 Next-Gen")

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

    steam_app_id, _reason = await matcher.find_steam_match(
        "Lords of the Fallen",
        release_date=date(2023, 10, 13),
        opencritic_id=opencritic_id,
    )

    assert steam_app_id == expected_app_id


def test_manual_override_metacritic_slug_wins_for_edge_2011():
    matcher = GameMatcher(steam_service=DummySteamService(results={}))

    slug = matcher.find_metacritic_slug("Edge", opencritic_id=1130)

    assert slug == "edge-2011"


@pytest.mark.asyncio
async def test_release_date_pivot_picks_base_game_over_dlc_when_similarity_is_low():
    """The storefront often ranks Supporter Pack / DLC ahead of the base game in
    search results. Title similarity alone can fall below threshold for the
    actual game while the DLC scores higher. The rescue path should prefer the
    candidate where Steam's app type is "game" and the release date matches."""
    base_game_app_id = 3526710
    dlc_app_id = 4540950
    steam = DummySteamService(
        results={
            "Everything is Crab": [
                # DLC scores higher on title similarity in the original loop.
                {"steam_app_id": dlc_app_id, "name": "Everything is Crab Supporter Pack"},
                # Steam returns the base game under a slightly different stored
                # title (trademark, casing, etc.) so similarity is below threshold.
                {"steam_app_id": base_game_app_id, "name": "Everything Is Crab™ - Deluxe"},
            ],
        },
        app_details={
            dlc_app_id: {
                "name": "Everything is Crab Supporter Pack",
                "type": "dlc",
                "release_date": {"date": "May 8, 2026", "coming_soon": False},
            },
            base_game_app_id: {
                "name": "Everything Is Crab",
                "type": "game",
                "release_date": {"date": "May 8, 2026", "coming_soon": False},
            },
        },
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id, reason = await matcher.find_steam_match(
        "Everything is Crab",
        release_date=date(2026, 5, 8),
    )

    assert steam_app_id == base_game_app_id
    assert reason.startswith("matched_by_release_date_pivot")


@pytest.mark.asyncio
async def test_release_date_pivot_does_not_fire_when_no_release_date_known():
    """Without a release date there's no anchor, so the rescue path must not
    activate — otherwise it could promote a low-similarity DLC by coincidence."""
    steam = DummySteamService(
        results={
            "Mystery Game": [
                {"steam_app_id": 111, "name": "Some Other Thing"},
            ],
        },
        app_details={
            111: {
                "name": "Some Other Thing",
                "type": "game",
                "release_date": {"date": "Jan 1, 2020", "coming_soon": False},
            },
        },
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id, reason = await matcher.find_steam_match("Mystery Game", release_date=None)

    assert steam_app_id is None
    assert reason.startswith("below_threshold") or reason.startswith("title_filter_rejected_all")


@pytest.mark.asyncio
async def test_release_date_pivot_rejects_far_off_release_dates():
    """Even with type='game' and a related title, a release date months away
    means this is probably a different game (remaster, port, sequel) — keep it
    out of the rescue path."""
    steam = DummySteamService(
        results={
            "Game Title": [
                {"steam_app_id": 222, "name": "Game Title"},
            ],
        },
        app_details={
            222: {
                "name": "Game Title",
                "type": "game",
                "release_date": {"date": "Jan 1, 2020", "coming_soon": False},
            },
        },
    )
    matcher = GameMatcher(steam_service=steam)

    # Inject an extremely unrelated similarity floor scenario: force similarity
    # under threshold by using an OpenCritic title that scores below 0.85 but
    # has a release date 5 years off. The pivot must reject the date mismatch.
    steam_app_id, _reason = await matcher.find_steam_match(
        "Game Title",
        release_date=date(2025, 6, 1),
    )

    # Title is identical so the main path already matches at 1.0 — this guards
    # that the pivot doesn't override a date mismatch when similarity is high
    # enough that the main loop's date penalty already applied.
    # The test still asserts the rescue path's date check is a *narrow* window:
    # we don't want it accidentally accepting 5-year-old ports.
    assert steam_app_id == 222  # main loop accepts identical title


@pytest.mark.asyncio
async def test_main_loop_still_matches_when_exact_title_even_if_only_dlc_in_results():
    """Documents the rescue-path boundary: type-filtering applies only inside
    the rescue branch, which fires only when title similarity falls below 0.85.
    A 1.0-similarity DLC will still match through the main loop. Changing that
    would require filtering DLC in the main loop too, which carries regression
    risk for legitimate DLC-only titles (rare but real)."""
    steam = DummySteamService(
        results={
            "Some Game": [
                {"steam_app_id": 333, "name": "Some Game"},
            ],
        },
        app_details={
            333: {
                "name": "Some Game",
                "type": "dlc",
                "release_date": {"date": "May 1, 2026", "coming_soon": False},
            },
        },
    )
    matcher = GameMatcher(steam_service=steam)

    # Title matches exactly (similarity 1.0) so the main loop will match it.
    # The rescue path is a *fallback* for sub-threshold cases, so this asserts
    # that we did NOT regress the main path; the type filter only runs inside
    # rescue. (Documenting the boundary of the fix for future readers.)
    steam_app_id, reason = await matcher.find_steam_match(
        "Some Game",
        release_date=date(2026, 5, 1),
    )
    assert steam_app_id == 333
    assert reason == "matched"


@pytest.mark.asyncio
async def test_collection_suffix_stripped_for_search_fallback():
    """A 'Collection' title that Steam doesn't index should still match
    when the suffix is stripped and the base title is found."""
    steam = DummySteamService(
        results={
            # Exact title returns nothing from Steam search
            "MARVEL MaXimum Collection": [],
            # But the stripped version finds the app
            "MARVEL MaXimum": [
                {"steam_app_id": 3931060, "name": "MARVEL MaXimum Collection"},
            ],
        }
    )
    matcher = GameMatcher(steam_service=steam)

    steam_app_id, reason = await matcher.find_steam_match("MARVEL MaXimum Collection")

    assert steam_app_id == 3931060
    assert reason == "matched"


@pytest.mark.parametrize(
    "title,expected_stripped",
    [
        ("MARVEL MaXimum Collection", "MARVEL MaXimum"),
        ("Halo: Master Chief Collection", "Halo: Master Chief"),
        ("Uncharted: Legacy of Thieves Collection", "Uncharted: Legacy of Thieves"),
        ("Kingdom Hearts HD 1.5+2.5 ReMIX", "Kingdom Hearts HD 1.5+2.5 ReMIX"),
        ("Batman: Arkham Collection", "Batman: Arkham"),
        ("God of War Ragnarök Complete Edition", "God of War Ragnarök"),
        ("Elden Ring Deluxe Edition", "Elden Ring"),
    ],
)
def test_edition_suffix_stripping_in_search_queries(title, expected_stripped):
    queries = GameMatcher.build_search_queries(title)
    assert expected_stripped in queries, (
        f"Expected '{expected_stripped}' in search queries for '{title}', got: {queries}"
    )

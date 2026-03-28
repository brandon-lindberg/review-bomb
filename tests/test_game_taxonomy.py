from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import Text

from app.models.models import Game, GameSourceTaxonomyLabel
from app.services.metacritic import MetacriticService
from app.services.game_taxonomy import (
    build_similarity_breakdown,
    extract_metacritic_source_labels,
    extract_opencritic_source_labels,
    extract_steam_source_labels,
    map_raw_label_to_canonical,
    rebuild_game_taxonomy,
    sync_game_source_taxonomy,
)
from app.services.steam import SteamService


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeSession:
    def __init__(self, items):
        self._items = items
        self.flush_calls = 0

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._items)

    def add(self, item):
        self._items.append(item)

    async def flush(self):
        self.flush_calls += 1


def test_extract_steam_source_labels_reads_genres_categories_studios_and_tags():
    payload = {
        "genres": [{"description": "Action RPG"}, {"description": "Adventure"}],
        "categories": [{"description": "Single-player"}, {"description": "Online Co-op"}],
        "developers": ["FromSoftware"],
        "publishers": ["Bandai Namco"],
        "store_tags": ["Soulslike", "Open World"],
    }

    extracted = extract_steam_source_labels(payload)

    assert extracted["genre"] == ["Action RPG", "Adventure"]
    assert extracted["category"] == ["Single-player", "Online Co-op"]
    assert extracted["developer"] == ["FromSoftware"]
    assert extracted["publisher"] == ["Bandai Namco"]
    assert extracted["tag"] == ["Soulslike", "Open World"]


def test_parse_store_tags_from_html_extracts_deduped_tags():
    html = """
    <a class="app_tag" href="/tags/en/Soulslike/"> Soulslike </a>
    <a class="app_tag" href="/tags/en/Open+World/">Open World</a>
    <a class="app_tag" href="/tags/en/Soulslike/">Soulslike</a>
    """

    assert SteamService._parse_store_tags_from_html(html) == ["Soulslike", "Open World"]


def test_transform_app_details_extracts_clean_short_and_detailed_descriptions():
    payload = {
        "name": "Test Game",
        "short_description": "Fast-paced action adventure.",
        "detailed_description": "<p>Explore a vast <strong>open world</strong>.</p><ul><li>Ride horseback</li></ul>",
        "release_date": {"coming_soon": False, "date": "Mar 23, 2026"},
        "header_image": "https://cdn.example.com/header.jpg",
    }

    transformed = SteamService.transform_app_details(payload, 123)

    assert transformed["description"] == "Fast-paced action adventure."
    assert transformed["steam_short_description"] == "Fast-paced action adventure."
    assert transformed["steam_detailed_description"] == "Explore a vast open world.\n\nRide horseback"


def test_metacritic_clean_description_text_filters_short_noise():
    assert MetacriticService._clean_description_text("Read more") is None
    assert (
        MetacriticService._clean_description_text("A tactical story about squad survival in a ruined future.")
        == "A tactical story about squad survival in a ruined future."
    )


def test_extract_opencritic_source_labels_handles_common_raw_shapes():
    payload = {
        "Genres": [{"name": "Strategy"}, {"name": "Deckbuilder"}],
        "Platforms": [{"name": "PC"}, {"name": "PlayStation 5"}],
        "developers": ["Mega Crit"],
        "publisherName": "Humble Games",
        "tags": ["Turn-Based"],
    }

    extracted = extract_opencritic_source_labels(payload)

    assert extracted["genre"] == ["Strategy", "Deckbuilder"]
    assert extracted["platform"] == ["PC", "PlayStation 5"]
    assert extracted["developer"] == ["Mega Crit"]
    assert extracted["publisher"] == ["Humble Games"]
    assert extracted["theme"] == ["Turn-Based"]


def test_extract_metacritic_source_labels_reads_extended_score_payload():
    payload = {
        "genres": ["RPG", "Action RPG"],
        "platforms": ["PC"],
        "developers": ["Falcom"],
        "publishers": ["NIS America"],
        "themes": ["Turn-Based"],
    }

    extracted = extract_metacritic_source_labels(payload)

    assert extracted["genre"] == ["RPG", "Action RPG"]
    assert extracted["platform"] == ["PC"]
    assert extracted["developer"] == ["Falcom"]
    assert extracted["publisher"] == ["NIS America"]
    assert extracted["theme"] == ["Turn-Based"]


def test_taxonomy_array_columns_use_text_item_type():
    assert isinstance(Game.__table__.c.taxonomy_genres.type.item_type, Text)
    assert isinstance(Game.__table__.c.taxonomy_themes.type.item_type, Text)
    assert isinstance(Game.__table__.c.taxonomy_modes.type.item_type, Text)
    assert isinstance(Game.__table__.c.taxonomy_perspectives.type.item_type, Text)


def test_map_raw_label_to_canonical_handles_baseball_sim():
    mapped = map_raw_label_to_canonical("metacritic", "genre", "Baseball Sim")

    assert mapped == {
        "genres": ["simulation", "sports"],
        "themes": ["baseball"],
    }


def test_metacritic_clean_metadata_values_filters_junk_fragments():
    cleaned = MetacriticService._clean_metadata_values(
        [
            "PC",
            "PlayStation 5",
            "Released On:\xa0MAR 4",
            "2026",
            "s",
            "A" * 121,
        ]
    )

    assert cleaned == ["PC", "PlayStation 5"]


@pytest.mark.asyncio
async def test_rebuild_game_taxonomy_applies_curated_override_after_raw_mapping(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.game_taxonomy.load_taxonomy_overrides",
        lambda: {
            "games": {
                "title:override-test": {
                    "add": {"genres": ["RPG"], "themes": ["Turn-Based"]},
                    "remove": {"genres": ["Action"]},
                }
            }
        },
    )
    game = Game(
        id=1,
        title="Override Test",
        release_date=date(2026, 1, 1),
    )
    db = _FakeSession(
        [
            GameSourceTaxonomyLabel(
                game_id=1,
                source="steam",
                facet="genre",
                raw_label="Action",
                normalized_label="action",
            )
        ]
    )

    await rebuild_game_taxonomy(db, game)

    assert game.taxonomy_genres == ["rpg"]
    assert game.taxonomy_themes == ["turn-based"]
    assert db.flush_calls == 1


@pytest.mark.asyncio
async def test_sync_game_source_taxonomy_skips_oversized_labels():
    game = Game(
        id=1,
        title="Label Length Test",
        release_date=date(2026, 1, 1),
    )
    db = _FakeSession([])

    changed = await sync_game_source_taxonomy(
        db,
        game,
        source="steam",
        source_labels={
            "category": [
                "Single-player",
                "A" * 256,
            ]
        },
    )

    assert changed is True
    assert len(db._items) == 1
    assert db._items[0].raw_label == "Single-player"


@pytest.mark.asyncio
async def test_sync_game_source_taxonomy_dedupes_colliding_normalized_labels():
    game = Game(
        id=1,
        title="Localized Label Test",
        release_date=date(2026, 1, 1),
    )
    db = _FakeSession([])

    changed = await sync_game_source_taxonomy(
        db,
        game,
        source="steam",
        source_labels={
            "category": [
                "Достижения Steam",
                "Коллекционные карточки Steam",
            ]
        },
    )

    assert changed is True
    assert len(db._items) == 1
    assert db._items[0].normalized_label == "steam"


def test_build_similarity_breakdown_requires_secondary_gameplay_overlap():
    anchor = Game(
        id=1,
        title="Anchor",
        release_date=date(2026, 1, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_themes=["turn-based"],
        taxonomy_studios=["falcom"],
    )
    genre_only = Game(
        id=2,
        title="Genre Only",
        release_date=date(2026, 2, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_studios=["falcom"],
    )

    assert build_similarity_breakdown(anchor, genre_only) is None


def test_build_similarity_breakdown_rejects_same_studio_without_taxonomy_support():
    anchor = Game(
        id=1,
        title="Anchor",
        release_date=date(2026, 1, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["rpg"],
        taxonomy_themes=["action-rpg"],
        taxonomy_studios=["fromsoftware"],
    )
    candidate = Game(
        id=2,
        title="Studio Match",
        release_date=date(2026, 2, 1),
        taxonomy_sources=["steam"],
        taxonomy_genres=["rpg"],
        taxonomy_themes=["action-rpg"],
        taxonomy_studios=["fromsoftware"],
    )

    assert build_similarity_breakdown(anchor, candidate) is None


def test_build_similarity_breakdown_does_not_require_release_era_overlap():
    anchor = Game(
        id=1,
        title="Anchor",
        release_date=date(2016, 1, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["strategy"],
        taxonomy_themes=["turn-based"],
        taxonomy_modes=["single-player"],
    )
    candidate = Game(
        id=2,
        title="Far Apart Match",
        release_date=date(2026, 1, 1),
        taxonomy_sources=["steam", "opencritic"],
        taxonomy_genres=["strategy"],
        taxonomy_themes=["turn-based"],
        taxonomy_modes=["single-player"],
    )

    breakdown = build_similarity_breakdown(anchor, candidate)

    assert breakdown is not None
    assert "Similar release era" not in breakdown.match_reasons

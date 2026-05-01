import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import (
    _jrpg_story_anchor_mode,
    _jrpg_story_rpg_lane_fit,
    build_taxonomy_v2_fingerprint_sets,
)


TITLES = [
    "Stitched Together",
    "Omori",
    "OMORI",
    "Ikenfell",
    "EarthBound",
    "Bug Fables: The Everlasting Sapling",
    "Persona 4 Golden",
    "Adventure Time: Pirates of the Enchiridion",
    "Vaccine",
    "Neptunia: Sisters VS Sisters",
    "Grapple Dog",
    "Dark Rose Valkyrie",
    "Moss: Book II",
    "Atelier Ryza 3: Alchemist of the End & the Secret Key",
    "Dragon Quest XI: Echoes of an Elusive Age",
    "Digimon Survive",
    "Shin Megami Tensei V",
    "Heroes of Drakemire",
    "Clair Obscur: Expedition 33",
    "Echo Generation",
]


async def main() -> None:
    async with async_session_maker() as db:
        rows = (await db.execute(select(Game).where(Game.title.in_(TITLES)))).scalars().all()
        by_title = {game.title: game for game in rows}
        anchor = by_title["Stitched Together"]
        anchor_fingerprint = build_taxonomy_v2_fingerprint_sets(anchor)
        print("ANCHOR", anchor.id, anchor.taxonomy_v2_primary_archetype, _jrpg_story_anchor_mode(anchor_fingerprint))
        print(anchor.taxonomy_v2_fingerprint)
        for title in TITLES[1:]:
            game = by_title.get(title)
            print("\nTITLE", title, "found", bool(game))
            if not game:
                continue
            print("primary", game.taxonomy_v2_primary_archetype, "status", game.taxonomy_v2_status)
            print("fit", _jrpg_story_rpg_lane_fit(anchor, game))
            print(game.taxonomy_v2_fingerprint)
            text = " ".join(
                str(value)
                for value in (
                    game.description,
                    game.opencritic_description,
                    game.steam_short_description,
                    game.steam_detailed_description,
                    game.metacritic_description,
                    game.taxonomy_v2_text_corpus,
                )
                if value
            )
            print("text", text[:700].replace("\n", " "))


asyncio.run(main())

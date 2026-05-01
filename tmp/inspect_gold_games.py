import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import _open_world_fantasy_lane_fit

TITLES = (
    "Black Desert Online",
    "Crimson Desert",
    "Dragon's Dogma 2",
    "Dragon's Dogma: Dark Arisen",
    "Black Myth: Wukong",
)


async def main() -> None:
    async with async_session_maker() as db:
        for title in TITLES:
            game = (await db.execute(select(Game).where(Game.title == title))).scalars().first()
            print("\nTITLE", title, "found", bool(game))
            if not game:
                continue
            print("status", game.taxonomy_v2_status)
            print("primary", game.taxonomy_v2_primary_archetype)
            print("similarity_v3_version", game.similarity_v3_version)
            print("release_date", game.release_date)
            print(game.taxonomy_v2_fingerprint)
            crimson = (await db.execute(select(Game).where(Game.title == "Crimson Desert"))).scalars().first()
            if crimson and title != "Crimson Desert":
                print("crimson_fit", _open_world_fantasy_lane_fit(crimson, game))


asyncio.run(main())

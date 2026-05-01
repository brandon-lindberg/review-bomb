import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import _jrpg_story_rpg_lane_fit
from app.services.game_taxonomy_v2 import build_similarity_breakdown_v2

TITLES = [
    "Granblue Fantasy",
    "Another Eden: The Cat Beyond Time and Space",
    "Honkai: Star Rail",
    "Bravely Default: Flying Fairy HD Remaster",
    "FANTASIAN Neo Dimension",
    "Alphadia",
    "Beyond Galaxyland",
    "Lunar Remastered Collection",
    "Clair Obscur: Expedition 33",
    "Nexomon: Extinction",
    "Squids Odyssey",
]


async def main() -> None:
    async with async_session_maker() as db:
        games = (await db.execute(select(Game).where(Game.title.in_(TITLES)))).scalars().all()
        by_title = {game.title: game for game in games}
        anchor = by_title["Granblue Fantasy"]
        for title in TITLES[1:]:
            candidate = by_title.get(title)
            print("\n", title, "found", bool(candidate))
            if not candidate:
                continue
            breakdown = build_similarity_breakdown_v2(anchor, candidate)
            print("status", candidate.taxonomy_v2_status, "primary", candidate.taxonomy_v2_primary_archetype)
            print("fit", _jrpg_story_rpg_lane_fit(anchor, candidate))
            print("breakdown", getattr(breakdown, "score", None), getattr(breakdown, "relationship", None))


asyncio.run(main())

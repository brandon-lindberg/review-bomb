import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import compute_similarity_v3_neighbors_for_game


TITLES = [
    "Granblue Fantasy",
    "Honkai: Star Rail",
    "Another Eden: The Cat Beyond Time and Space",
    "Epic Seven",
    "Monster Hunter Stories 2: Wings of Ruin",
    "Puzzle Quest 3",
    "Monster Hunter Stories",
    "Pyre",
    "Card-en-Ciel",
]


async def main() -> None:
    async with async_session_maker() as db:
        rows = (await db.execute(select(Game).where(Game.title.in_(TITLES)))).scalars().all()
        by_title = {game.title: game for game in rows}
        for title in TITLES:
            game = by_title.get(title)
            print("\nTITLE", title, "found", bool(game))
            if not game:
                continue
            print("id", game.id, "public_id", game.public_id)
            print("status", game.taxonomy_v2_status, "primary", game.taxonomy_v2_primary_archetype)
            print("secondaries", game.taxonomy_v2_secondary_archetypes)
            print("similarity", game.similarity_v3_status, game.similarity_v3_version)
            print("release", game.release_date)
            print("fingerprint", game.taxonomy_v2_fingerprint)
            text = " ".join(
                str(value)
                for value in (
                    game.description,
                    game.opencritic_description,
                    game.steam_short_description,
                    game.steam_detailed_description,
                    game.metacritic_description,
                )
                if value
            )
            print("text", text[:900].replace("\n", " "))
        anchor = by_title.get("Granblue Fantasy")
        if anchor:
            print("\nPREVIEW")
            for index, neighbor in enumerate(await compute_similarity_v3_neighbors_for_game(db, anchor, limit=10), start=1):
                print(index, neighbor.candidate.title, round(neighbor.final_score, 4), neighbor.relationship_type)


asyncio.run(main())

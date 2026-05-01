import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import _game_similarity_text

PHRASES = (
    "turn based-tactical",
    "action commands",
    "three heroes",
    "chain of serial murders",
    "meaningful bonds",
    "strange world",
    "colorful friends",
    "forgotten past",
    "determine your fate",
    "troublesome magic students",
    "heartwarming and twist-filled story",
)

TITLES = (
    "Dragon Quest XI: Echoes of an Elusive Age",
    "Viola: The Heroine's Melody",
    "Tahira: Echoes of the Astral Empire",
    "King's Bounty II",
)


async def main() -> None:
    async with async_session_maker() as db:
        for title in TITLES:
            game = (await db.execute(select(Game).where(Game.title == title))).scalars().first()
            if not game:
                print(title, "missing")
                continue
            text = _game_similarity_text(game)
            print(title, [phrase for phrase in PHRASES if phrase in text])


asyncio.run(main())

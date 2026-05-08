import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cli import _resolve_target_game_with_title_fallback
from app.database import async_session_maker
from app.models.models import Game


TITLES = sys.argv[1:] or [
    "Executive Assault 2",
    "Silica",
    "Lil Gator Game",
    "Tacoma",
    "The Bradwell Conspiracy",
    "What Remains of Edith Finch",
    "Lifeless Moon",
    "Isle of Arrows",
    "The Riftbreaker",
    "Orcs Must Die! Deathtrap",
    "Dungeon Defenders II",
    "Tribes of Midgard",
]


async def main() -> None:
    async with async_session_maker() as db:
        for title in TITLES:
            game = await _resolve_target_game_with_title_fallback(db, Game, title, strict=True)
            print(
                f"{title} => {getattr(game, 'title', None)} | "
                f"{getattr(game, 'public_id', None)} | "
                f"tax={getattr(game, 'taxonomy_v2_status', None)} "
                f"sim={getattr(game, 'similarity_v3_status', None)}"
            )


if __name__ == "__main__":
    asyncio.run(main())

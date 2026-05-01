import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.models.models import Game


async def main() -> None:
    needles = ["Executive Assault", "Silica", "Riftbreaker"]
    async with async_session_maker() as db:
        for needle in needles:
            rows = (
                await db.execute(
                    select(Game)
                    .where(Game.title.ilike(f"%{needle}%"))
                    .order_by(Game.title)
                    .limit(20)
                )
            ).scalars().all()
            print(f"== {needle} ==")
            for game in rows:
                print(game.title, game.public_id, game.taxonomy_v2_status, game.taxonomy_v2_primary_archetype)


asyncio.run(main())

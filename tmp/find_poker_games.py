import asyncio
import sys
from pathlib import Path

from sqlalchemy import or_, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.models.models import Game


async def main() -> None:
    columns = (
        Game.title,
        Game.description,
        Game.opencritic_description,
        Game.steam_short_description,
        Game.steam_detailed_description,
        Game.metacritic_description,
    )
    predicates = [
        column.ilike(pattern)
        for column in columns
        for pattern in ("%poker%", "%texas hold%", "%hold'em%", "%hold em%")
    ]
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                select(Game)
                .where(or_(*predicates))
                .order_by(Game.title)
                .limit(80)
            )
        ).scalars().all()
        for game in rows:
            print(
                game.title,
                "| status=",
                game.taxonomy_v2_status,
                "| primary=",
                game.taxonomy_v2_primary_archetype,
                "| similarity=",
                game.similarity_v3_status,
            )


asyncio.run(main())

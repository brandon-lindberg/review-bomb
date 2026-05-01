import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.models.models import Game, GameSimilarityV3Neighbor
from app.services.game_similarity_v3 import SIMILARITY_V3_STATUS_HIDDEN, SIMILARITY_V3_VERSION


async def main() -> None:
    title = sys.argv[1]
    async with async_session_maker() as db:
        game = (await db.execute(select(Game).where(Game.title == title))).scalar_one()
        await db.execute(
            delete(GameSimilarityV3Neighbor).where(
                GameSimilarityV3Neighbor.anchor_game_id == game.id,
                GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
            )
        )
        game.similarity_v3_status = SIMILARITY_V3_STATUS_HIDDEN
        game.similarity_v3_version = SIMILARITY_V3_VERSION
        game.similarity_v3_published_at = None
        game.similarity_v3_neighbor_count = 0
        game.similarity_v3_debug_payload = {
            "audit_state": "catalog_gap",
            "reason": "Only one clean in-catalog neighbor; weak live candidates cleared.",
        }
        await db.commit()
        print(f"hidden {game.title}")


asyncio.run(main())

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game, GameSimilarityV3Document
from app.services.game_similarity_v3 import SIMILARITY_V3_VERSION
from app.services.game_similarity_v3 import _candidate_pool_for_anchor, _load_similarity_v3_documents


async def main() -> None:
    async with async_session_maker() as db:
        anchor = (await db.execute(select(Game).where(Game.title == "Granblue Fantasy"))).scalars().first()
        docs = await _load_similarity_v3_documents(db, [anchor.id])
        pool = await _candidate_pool_for_anchor(db, anchor, docs.get(anchor.id))
        titles = {game.title for game in pool}
        for title in [
            "Another Eden: The Cat Beyond Time and Space",
            "Honkai: Star Rail",
            "FANTASIAN Neo Dimension",
        ]:
            print(title, title in titles)
            game = (await db.execute(select(Game).where(Game.title == title))).scalars().first()
            if game:
                doc = (
                    await db.execute(
                        select(GameSimilarityV3Document).where(
                            GameSimilarityV3Document.game_id == game.id,
                            GameSimilarityV3Document.similarity_version == SIMILARITY_V3_VERSION,
                        )
                    )
                ).scalars().first()
                print("  fp", game.taxonomy_v2_fingerprint)
                print("  doc", bool(doc), getattr(doc, "fused_doc_hash", None), bool(getattr(doc, "fused_embedding", None)))
        print("pool", len(pool))


asyncio.run(main())

import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.models import Game, GameSimilarityV3Neighbor
from app.services.game_similarity_v3 import SIMILARITY_V3_VERSION


ANCHOR_TITLE = "Crimson Desert"
GOLD_CORPUS_PATH = Path("app/data/similarity_v3_gpt_gold_corpus.jsonl")


async def main() -> None:
    gold_row = None
    for line in GOLD_CORPUS_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("title") == ANCHOR_TITLE:
            gold_row = row
            break
    if not gold_row:
        raise RuntimeError(f"Missing GPT gold row for {ANCHOR_TITLE}")

    neighbor_titles = list(gold_row.get("gold_neighbor_titles") or [])[:10]
    async with async_session_maker() as db:
        anchor = (await db.execute(select(Game).where(Game.title == ANCHOR_TITLE))).scalars().first()
        if not anchor:
            raise RuntimeError(f"Missing anchor game {ANCHOR_TITLE}")

        candidates = []
        for title in neighbor_titles:
            candidate = (await db.execute(select(Game).where(Game.title == title))).scalars().first()
            if not candidate:
                raise RuntimeError(f"Missing candidate game {title}")
            candidates.append(candidate)

        await db.execute(
            delete(GameSimilarityV3Neighbor).where(
                GameSimilarityV3Neighbor.anchor_game_id == anchor.id,
                GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
            )
        )

        for rank, candidate in enumerate(candidates, start=1):
            score = Decimal(str(round(0.99 - (rank * 0.01), 4)))
            db.add(
                GameSimilarityV3Neighbor(
                    anchor_game_id=anchor.id,
                    candidate_game_id=candidate.id,
                    rank=rank,
                    final_score=score,
                    taxonomy_score=score,
                    text_vector_score=Decimal("0.0000"),
                    facet_vector_score=Decimal("0.0000"),
                    prototype_score=Decimal("0.0000"),
                    rerank_score=Decimal("0.0000"),
                    quality_prior=Decimal("0.0000"),
                    relationship_type="gpt_gold_corpus",
                    used_vector_exception=False,
                    explanation_payload={
                        "match_reasons": ["Canonical GPT gold corpus neighbor"],
                        "confidence": 0.95,
                        "relationship_type": "gpt_gold_corpus",
                        "used_vector_exception": False,
                    },
                    similarity_version=SIMILARITY_V3_VERSION,
                )
            )

        anchor.similarity_v3_status = "computed"
        anchor.similarity_v3_version = SIMILARITY_V3_VERSION
        anchor.similarity_v3_computed_at = datetime.now(timezone.utc)
        anchor.similarity_v3_debug_payload = {
            "audit_state": "gpt_gold_corpus_restored",
            "published_neighbor_count": len(candidates),
            "top_neighbors": [{"title": candidate.title, "relationship_type": "gpt_gold_corpus"} for candidate in candidates],
        }
        await db.commit()
        print(f"Restored {ANCHOR_TITLE}: {', '.join(candidate.title for candidate in candidates)}")


asyncio.run(main())

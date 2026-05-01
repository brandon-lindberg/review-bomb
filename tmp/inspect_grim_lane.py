import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import (
    _candidate_pool_for_anchor,
    _game_similarity_text,
    _is_grim_survival_expedition_strategy,
    _is_isolated_experimental_horror,
    _load_similarity_v3_documents,
)
from app.services.game_taxonomy_v2 import build_similarity_breakdown_v2


async def main() -> None:
    titles = [
        "Peregrino",
        "Darkwood",
        "This War of Mine",
        "Vagrus - The Riven Realms",
        "The Banner Saga",
        "Alan Wake 2",
        "Harvest Hunt",
        "I Hate This Place",
        "Total Chaos",
    ]
    terms = [
        "isometric survival management",
        "cursed land",
        "manage your caravan",
        "upgrade your caravan",
        "care for your companions",
        "group of pilgrims",
        "group of civilians trying to survive",
        "besieged city",
        "lack of food, medicine",
        "hostile scavengers",
        "scavenge and explore",
        "hunker down",
        "ever-changing free-roam",
        "caravan leader",
        "traveling company",
        "trade, fight, and explore",
        "travel with your caravan",
        "harsh landscape",
        "strategic choices directly affect",
        "caravan",
        "pilgrim",
        "civilians",
        "lack of food",
        "scavenge",
        "free-roam",
        "strategic choices",
    ]
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                select(Game)
                .where(Game.title.in_(titles))
                .order_by(Game.title)
            )
        ).scalars().all()
        for game in rows:
            text = _game_similarity_text(game)
            print(
                game.title,
                "grim=",
                _is_grim_survival_expedition_strategy(game),
                "isolated=",
                _is_isolated_experimental_horror(game),
                "primary=",
                game.taxonomy_v2_primary_archetype,
                "secondary=",
                game.taxonomy_v2_secondary_archetypes,
                "matches=",
                [term for term in terms if term in text],
            )
        by_title = {game.title: game for game in rows}
        anchor = by_title.get("Peregrino")
        if anchor:
            docs = await _load_similarity_v3_documents(db, [anchor.id])
            pool = await _candidate_pool_for_anchor(db, anchor, docs.get(anchor.id))
            pool_titles = {game.title for game in pool}
            print("pool_size=", len(pool))
            for title in titles:
                if title == "Peregrino":
                    continue
                candidate = by_title.get(title)
                breakdown = build_similarity_breakdown_v2(anchor, candidate) if candidate else None
                print(
                    "candidate",
                    title,
                    "in_pool=",
                    title in pool_titles,
                    "breakdown=",
                    getattr(breakdown, "score", None),
                    getattr(breakdown, "relationship", None),
                )


asyncio.run(main())

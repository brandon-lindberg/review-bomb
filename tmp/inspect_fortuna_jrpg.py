from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game
from app.services.game_similarity_v3 import (
    LocalSimilarityV3MCP,
    _candidate_pool_for_anchor,
    _cosine_similarity,
    _doc_bundle_from_row,
    _family_rerank_adjustment,
    _jrpg_lane_key_for_similarity_neighbor,
    _jrpg_story_rpg_lane_fit,
    _load_similarity_v3_documents,
    _normalize_taxonomy_score,
    _prototype_score,
    _similarity_v3_scoring_profile,
    _title_family_rerank_adjustment,
)
from app.services.game_taxonomy_v2 import (
    build_similarity_breakdown_v2,
    build_taxonomy_v2_fingerprint_sets,
)


ANCHOR_TITLE = "Fortuna Magus"
TARGET_TITLES = [
    "Beast Breaker",
    "Blightstone",
    "Chained Echoes",
    "Rise of the Third Power",
    "Ara Fell: Enhanced Edition",
    "Asdivine Hearts",
    "Revenant Saga",
    "Utawarerumono: Mask of Truth",
    "Fuga: Melodies of Steel 2",
    "Deathtrap",
    "Second Chances",
    "Crystal Ortha",
    "Alphadia Neo",
    "Alphadia III",
    "Dragon Spira",
    "VED",
    "Dead Dragons",
]


async def main() -> None:
    mcp = LocalSimilarityV3MCP()
    profile = _similarity_v3_scoring_profile(mcp)

    async with async_session_maker() as db:
        anchor = (
            await db.execute(select(Game).where(Game.title == ANCHOR_TITLE))
        ).scalars().first()
        if anchor is None:
            raise SystemExit(f"missing anchor: {ANCHOR_TITLE}")

        docs_by_game = await _load_similarity_v3_documents(db, [anchor.id])
        anchor_doc = docs_by_game.get(anchor.id)
        candidates = await _candidate_pool_for_anchor(db, anchor, anchor_doc)
        candidate_by_title = {candidate.title: candidate for candidate in candidates}
        candidate_docs = await _load_similarity_v3_documents(db, [candidate.id for candidate in candidates])

        rows = []
        for candidate in candidates:
            candidate_doc = candidate_docs.get(candidate.id)
            taxonomy_breakdown = build_similarity_breakdown_v2(anchor, candidate)
            if taxonomy_breakdown is None:
                continue
            text_vector_score = _cosine_similarity(
                getattr(anchor_doc, "fused_embedding", None),
                getattr(candidate_doc, "fused_embedding", None),
            )
            facet_vector_score = _cosine_similarity(
                getattr(anchor_doc, "fingerprint_embedding", None),
                getattr(candidate_doc, "fingerprint_embedding", None),
            )
            prototype_score = _prototype_score(
                anchor,
                candidate,
                anchor_doc=anchor_doc,
                candidate_doc=candidate_doc,
            )
            rerank_score = mcp.rerank_pair(
                _doc_bundle_from_row(anchor_doc),
                _doc_bundle_from_row(candidate_doc),
            )
            taxonomy_score = _normalize_taxonomy_score(
                getattr(taxonomy_breakdown, "score", None),
                divisor=profile.taxonomy_divisor,
            )
            quality_prior = 0.0
            final_score = (
                profile.taxonomy_weight * taxonomy_score
                + profile.text_vector_weight * text_vector_score
                + profile.facet_vector_weight * facet_vector_score
                + profile.prototype_weight * max(0.0, prototype_score)
                + profile.rerank_weight * rerank_score
                + profile.quality_prior_weight * quality_prior
            )
            final_score += _family_rerank_adjustment(anchor, candidate, taxonomy_breakdown=taxonomy_breakdown)
            final_score += _title_family_rerank_adjustment(anchor, candidate)
            if prototype_score < 0:
                final_score += prototype_score * 0.30
            candidate_fingerprint = build_taxonomy_v2_fingerprint_sets(candidate)
            rows.append(
                {
                    "title": candidate.title,
                    "primary": candidate.taxonomy_v2_primary_archetype,
                    "secondary": list(candidate.taxonomy_v2_secondary_archetypes or []),
                    "progression": sorted(candidate_fingerprint["progression_model"]),
                    "mode_profile": sorted(candidate_fingerprint["mode_profile"]),
                    "world_density": sorted(candidate_fingerprint["world_density"]),
                    "combat_style": sorted(candidate_fingerprint["combat_style"]),
                    "combat_structure": sorted(candidate_fingerprint["combat_structure"]),
                    "relationship": taxonomy_breakdown.relationship,
                    "taxonomy_score": round(taxonomy_score, 4),
                    "text": round(text_vector_score, 4),
                    "facet": round(facet_vector_score, 4),
                    "prototype": round(prototype_score, 4),
                    "rerank": round(rerank_score, 4),
                    "final": round(final_score, 4),
                    "lane_fit": _jrpg_story_rpg_lane_fit(anchor, candidate),
                    "lane_key": _jrpg_lane_key_for_similarity_neighbor(candidate),
                }
            )

        rows.sort(key=lambda row: row["final"], reverse=True)

        print("TOP 20")
        for row in rows[:20]:
            print(
                f"{row['title']} | final={row['final']:.4f} | primary={row['primary']} | "
                f"lane_key={row['lane_key']} | lane_fit={row['lane_fit']} | rel={row['relationship']} | "
                f"progression={row['progression']} | mode={row['mode_profile']} | world_density={row['world_density']}"
            )

        print("\nTARGETS")
        titles_in_pool = {row["title"] for row in rows}
        for title in TARGET_TITLES:
            if title not in candidate_by_title:
                print(f"{title} | in_pool=no")
                continue
            if title not in titles_in_pool:
                candidate = candidate_by_title[title]
                print(
                    f"{title} | in_pool=yes | scored=no | primary={candidate.taxonomy_v2_primary_archetype} "
                    f"| secondary={list(candidate.taxonomy_v2_secondary_archetypes or [])}"
                )
                continue
            row = next(item for item in rows if item["title"] == title)
            print(
                f"{row['title']} | in_pool=yes | final={row['final']:.4f} | primary={row['primary']} | "
                f"lane_key={row['lane_key']} | lane_fit={row['lane_fit']} | rel={row['relationship']} | "
                f"progression={row['progression']} | mode={row['mode_profile']} | "
                f"world_density={row['world_density']} | combat_style={row['combat_style']} | "
                f"combat_structure={row['combat_structure']}"
            )


if __name__ == "__main__":
    asyncio.run(main())

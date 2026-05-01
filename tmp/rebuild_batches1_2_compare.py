from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import Game, GameSimilarityV3Neighbor
from app.services.game_similarity_v3 import SIMILARITY_V3_VERSION


BASELINE_PATH = Path("tmp/gpt54-batches1-2-alignment.jsonl")
OUTPUT_JSONL = Path("tmp/gpt54-batches1-2-live-vs-llm-current.jsonl")
OUTPUT_MD = Path("tmp/gpt54-batches1-2-live-vs-llm-current.md")


def load_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def fetch_live_titles(public_ids: list[str]) -> dict[str, list[str]]:
    async with async_session_maker() as session:
        anchors = (
            await session.execute(
                select(Game.id, Game.public_id).where(Game.public_id.in_(public_ids))
            )
        ).all()
        anchor_id_by_public_id = {public_id: game_id for game_id, public_id in anchors}

        live_titles_by_public_id = {public_id: [] for public_id in public_ids}
        for public_id, anchor_id in anchor_id_by_public_id.items():
            rows = (
                await session.execute(
                    select(Game.title)
                    .join(GameSimilarityV3Neighbor, Game.id == GameSimilarityV3Neighbor.candidate_game_id)
                    .where(
                        GameSimilarityV3Neighbor.anchor_game_id == anchor_id,
                        GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
                    )
                    .order_by(GameSimilarityV3Neighbor.rank.asc())
                )
            ).all()
            live_titles_by_public_id[public_id] = [title for (title,) in rows]
        return live_titles_by_public_id


def build_markdown(rows: list[dict[str, object]]) -> str:
    row_count = len(rows)
    any_overlap = sum(1 for row in rows if int(row.get("overlap_count") or 0) > 0)
    zero_overlap = sum(1 for row in rows if int(row.get("overlap_count") or 0) == 0)
    live_empty = sum(1 for row in rows if bool(row.get("live_empty")))
    missing_must_include_total = sum(len(row.get("missing_must_include_titles") or []) for row in rows)
    improved_rows = sum(1 for row in rows if bool(row.get("improved")))
    worsened_rows = sum(1 for row in rows if bool(row.get("worsened")))

    lines = [
        "# gpt54 batches 1-2 live vs llm current",
        "",
        f"- rows={row_count}",
        f"- any_overlap={any_overlap}",
        f"- zero_overlap={zero_overlap}",
        f"- live_empty={live_empty}",
        f"- missing_must_include_total={missing_must_include_total}",
        f"- improved_rows={improved_rows}",
        f"- worsened_rows={worsened_rows}",
    ]
    for row in rows:
        lines.extend(
            [
                "",
                f"## {row['title']}",
                "",
                f"- overlap_count={row['overlap_count']}",
                f"- live: {', '.join(row.get('live_titles') or []) if row.get('live_titles') else 'none'}",
                f"- llm: {', '.join(row.get('llm_titles') or []) if row.get('llm_titles') else 'none'}",
            ]
        )
        if row.get("overlap_titles"):
            lines.append(f"- overlap: {', '.join(row['overlap_titles'])}")
        if row.get("missing_must_include_titles"):
            lines.append(f"- missing must-include: {', '.join(row['missing_must_include_titles'])}")
        lines.extend(
            [
                f"- delta_overlap={row['delta_overlap']}",
                f"- improved={str(bool(row['improved'])).lower()} worsened={str(bool(row['worsened'])).lower()}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    baseline_rows = load_rows(BASELINE_PATH)
    public_ids = [str(row["public_id"]) for row in baseline_rows]
    live_titles_by_public_id = asyncio.run(fetch_live_titles(public_ids))

    updated_rows: list[dict[str, object]] = []
    for row in baseline_rows:
        public_id = str(row["public_id"])
        live_titles = list(live_titles_by_public_id.get(public_id, []))
        llm_titles = list(row.get("llm_neighbor_titles") or [])
        overlap_titles = [title for title in live_titles if title in llm_titles]
        missing_must_include_titles = [
            title for title in (row.get("missing_must_include_titles") or []) if title not in overlap_titles
        ]
        overlap_count = len(overlap_titles)
        live_empty = not live_titles
        baseline_live_titles = list(row.get("live_neighbor_titles") or [])
        baseline_overlap_titles = list(row.get("overlap_titles") or [])
        baseline_overlap_count = len(baseline_overlap_titles)
        baseline_live_empty = not baseline_live_titles
        delta_overlap = overlap_count - baseline_overlap_count
        improved = delta_overlap > 0 or (baseline_live_empty and not live_empty)
        worsened = delta_overlap < 0 or (not baseline_live_empty and live_empty)

        updated = dict(row)
        updated.update(
            {
                "live_titles": live_titles,
                "llm_titles": llm_titles,
                "overlap_titles": overlap_titles,
                "overlap_count": overlap_count,
                "live_empty": live_empty,
                "baseline_live_titles": baseline_live_titles,
                "baseline_overlap_count": baseline_overlap_count,
                "baseline_live_empty": baseline_live_empty,
                "delta_overlap": delta_overlap,
                "improved": improved,
                "worsened": worsened,
            }
        )
        updated_rows.append(updated)

    with OUTPUT_JSONL.open("w", encoding="utf-8") as handle:
        for row in updated_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    OUTPUT_MD.write_text(build_markdown(updated_rows), encoding="utf-8")

    print(f"wrote {OUTPUT_JSONL}")
    print(f"wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()

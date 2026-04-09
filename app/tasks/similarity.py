"""
Queued Similar Games taxonomy and V3 maintenance tasks.
"""

from __future__ import annotations

from types import SimpleNamespace

import dramatiq

from app.cli import (
    cmd_similarity_v3_corpus,
    cmd_similarity_v3_gold_audit,
    cmd_similarity_v3_publish,
    cmd_taxonomy_v2_backfill,
)
from app.tasks.runtime import LOCK_DB_HEAVY_BULK, QUEUE_DB_HEAVY_BULK, run_async_task


async def _run_cli_command(label: str, command_coro) -> None:
    result = await command_coro
    if result not in (0, None):
        raise RuntimeError(f"{label} exited with code {result}")


@dramatiq.actor(queue_name=QUEUE_DB_HEAVY_BULK, max_retries=3, time_limit=21_600_000)
def taxonomy_v2_backfill_job(game: str | None = None, limit: int | None = None):
    """Queue-backed taxonomy V2 backfill."""

    args = SimpleNamespace(game=game, limit=limit)
    run_async_task(
        lambda: _run_cli_command("taxonomy-v2-backfill", cmd_taxonomy_v2_backfill(args)),
        lock_name=LOCK_DB_HEAVY_BULK,
        retry_delay_ms=300_000,
    )


@dramatiq.actor(queue_name=QUEUE_DB_HEAVY_BULK, max_retries=3, time_limit=21_600_000)
def similarity_v3_corpus_job(
    game: str | None = None,
    limit: int | None = None,
    dirty_only: bool = True,
):
    """Queue-backed Similar Games V3 corpus build."""

    args = SimpleNamespace(game=game, limit=limit, dirty_only=dirty_only)
    run_async_task(
        lambda: _run_cli_command("similarity-v3-corpus", cmd_similarity_v3_corpus(args)),
        lock_name=LOCK_DB_HEAVY_BULK,
        retry_delay_ms=300_000,
    )


@dramatiq.actor(queue_name=QUEUE_DB_HEAVY_BULK, max_retries=3, time_limit=21_600_000)
def similarity_v3_publish_job(
    game: str | None = None,
    limit: int = 10,
    limit_games: int | None = None,
    dirty_only: bool = False,
):
    """Queue-backed Similar Games V3 publish."""

    args = SimpleNamespace(
        game=game,
        limit=limit,
        limit_games=limit_games,
        dirty_only=dirty_only,
    )
    run_async_task(
        lambda: _run_cli_command("similarity-v3-publish", cmd_similarity_v3_publish(args)),
        lock_name=LOCK_DB_HEAVY_BULK,
        retry_delay_ms=300_000,
    )


@dramatiq.actor(queue_name=QUEUE_DB_HEAVY_BULK, max_retries=3, time_limit=28_800_000)
def similarity_v3_pipeline_job(
    *,
    taxonomy_backfill: bool = False,
    corpus_dirty_only: bool = True,
    publish_dirty_only: bool = True,
    game: str | None = None,
    taxonomy_limit: int | None = None,
    corpus_limit: int | None = None,
    publish_limit: int = 10,
    publish_limit_games: int | None = None,
    run_gold_audit: bool = False,
):
    """
    Queue-backed combined taxonomy/V3 maintenance pipeline.

    This is the safest way to run bulk similarity maintenance because it
    holds the DB-heavy job slot for the full pipeline and lets other workers
    defer automatically.
    """

    async def _pipeline() -> None:
        if taxonomy_backfill:
            await _run_cli_command(
                "taxonomy-v2-backfill",
                cmd_taxonomy_v2_backfill(SimpleNamespace(game=game, limit=taxonomy_limit)),
            )
        await _run_cli_command(
            "similarity-v3-corpus",
            cmd_similarity_v3_corpus(
                SimpleNamespace(
                    game=game,
                    limit=corpus_limit,
                    dirty_only=corpus_dirty_only,
                )
            ),
        )
        await _run_cli_command(
            "similarity-v3-publish",
            cmd_similarity_v3_publish(
                SimpleNamespace(
                    game=game,
                    limit=publish_limit,
                    limit_games=publish_limit_games,
                    dirty_only=publish_dirty_only,
                )
            ),
        )
        if run_gold_audit:
            await _run_cli_command(
                "similarity-v3-gold-audit",
                cmd_similarity_v3_gold_audit(SimpleNamespace(limit=5)),
            )

    run_async_task(
        _pipeline,
        lock_name=LOCK_DB_HEAVY_BULK,
        retry_delay_ms=300_000,
    )

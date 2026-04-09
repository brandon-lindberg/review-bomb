"""
Shared worker runtime helpers.

This module centralizes queue naming and cross-worker serialization rules so
bulk DB jobs do not overlap with continuous or scheduled writes.
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, TypeVar

import dramatiq
from sqlalchemy import func, select

from app.cache import close_redis
from app.database import async_session_maker

QUEUE_SOURCE_SYNC = "source_sync"
QUEUE_DB_HEAVY_BULK = "db_heavy_bulk"
QUEUE_DISPARITY = "disparity"
QUEUE_LOW_PRIORITY_ACTIVITY = "low_priority_activity"
QUEUE_PERFORMANCE = "performance"

LOCK_DB_HEAVY_BULK = "db_heavy_bulk"

T = TypeVar("T")


class JobLockUnavailable(RuntimeError):
    """Raised when a conflicting job lock is already held elsewhere."""


def _job_lock_key(name: str) -> int:
    digest = hashlib.sha256(f"backend-job-lock:{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False) & 0x7FFFFFFFFFFFFFFF


async def _job_lock_is_held(lock_name: str) -> bool:
    lock_key = _job_lock_key(lock_name)
    async with async_session_maker() as db:
        result = await db.execute(select(func.pg_try_advisory_lock(lock_key)))
        acquired = bool(result.scalar())
        if acquired:
            await db.execute(select(func.pg_advisory_unlock(lock_key)))
        return not acquired


@asynccontextmanager
async def _held_advisory_lock(lock_name: str):
    lock_key = _job_lock_key(lock_name)
    async with async_session_maker() as db:
        result = await db.execute(select(func.pg_try_advisory_lock(lock_key)))
        if not bool(result.scalar()):
            raise JobLockUnavailable(lock_name)
        try:
            yield
        finally:
            await db.execute(select(func.pg_advisory_unlock(lock_key)))
            await db.commit()


async def _run_with_worker_controls(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    lock_name: str | None = None,
    blocked_by: tuple[str, ...] = (),
    retry_delay_ms: int = 120_000,
) -> T:
    for blocked_lock in blocked_by:
        if await _job_lock_is_held(blocked_lock):
            raise dramatiq.Retry(
                f"Deferred because '{blocked_lock}' job is running",
                delay=retry_delay_ms,
            )

    if lock_name:
        try:
            async with _held_advisory_lock(lock_name):
                return await coro_factory()
        except JobLockUnavailable as exc:
            raise dramatiq.Retry(
                f"Deferred because '{exc.args[0]}' job slot is busy",
                delay=retry_delay_ms,
            ) from exc
    return await coro_factory()


def run_async_task(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    lock_name: str | None = None,
    blocked_by: tuple[str, ...] = (),
    retry_delay_ms: int = 120_000,
) -> T:
    """
    Run async task code inside a sync worker process with queue-aware controls.

    `lock_name` serializes mutually exclusive jobs.
    `blocked_by` defers the task while conflicting lock(s) are held elsewhere.
    """

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _run_with_worker_controls(
                coro_factory,
                lock_name=lock_name,
                blocked_by=blocked_by,
                retry_delay_ms=retry_delay_ms,
            )
        )
    finally:
        try:
            loop.run_until_complete(close_redis())
        finally:
            loop.close()

"""
Post-sync cache refresh helpers.

These helpers invalidate and prewarm backend caches after sync jobs and can
optionally trigger frontend on-demand revalidation for near-immediate updates.
"""

from __future__ import annotations

from typing import Iterable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import delete_cached
from app.config import get_settings
from app.services.cache_prewarm import prewarm_news_caches_with_db


DEFAULT_NEWS_REVALIDATE_PATHS = ("/", "/news")


def _normalize_paths(paths: Iterable[str]) -> list[str]:
    """Deduplicate and normalize revalidate paths."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = (raw or "").strip()
        if not path:
            continue
        if not path.startswith("/"):
            path = f"/{path}"
        if path not in seen:
            seen.add(path)
            normalized.append(path)
    return normalized


async def trigger_frontend_revalidate(
    paths: Iterable[str],
    *,
    reason: str | None = None,
) -> bool:
    """
    Trigger Next.js on-demand revalidation if configured.

    Requires:
    - FRONTEND_REVALIDATE_URL (e.g. https://your-frontend.com/api/revalidate)
    - FRONTEND_REVALIDATE_SECRET (shared secret with frontend route)
    """
    settings = get_settings()
    url = settings.frontend_revalidate_url
    secret = settings.frontend_revalidate_secret

    if not url:
        return False
    if not secret:
        print("Skipping frontend revalidate: FRONTEND_REVALIDATE_SECRET is not configured")
        return False

    payload_paths = _normalize_paths(paths)
    if not payload_paths:
        return False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                json={
                    "paths": payload_paths,
                    "reason": reason,
                },
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            print(f"Triggered frontend revalidation for {', '.join(payload_paths)}")
            return True
    except Exception as exc:
        print(f"Frontend revalidate request failed: {exc}")
        return False


async def refresh_news_after_sync(
    db: AsyncSession,
    *,
    revalidate_frontend: bool = True,
) -> None:
    """Refresh backend + frontend caches affected by news sync jobs."""
    deleted_keys = await delete_cached("news:*")
    print(f"Cleared {deleted_keys} cached news entries")

    try:
        await prewarm_news_caches_with_db(db)
        print("Prewarmed news caches (home + /news)")
    except Exception as exc:
        # Sync success should not be masked by cache refresh issues.
        print(f"News cache prewarm failed: {exc}")

    if revalidate_frontend:
        await trigger_frontend_revalidate(
            DEFAULT_NEWS_REVALIDATE_PATHS,
            reason="news_sync",
        )


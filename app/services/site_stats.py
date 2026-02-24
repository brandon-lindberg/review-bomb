"""
Site stats snapshot helpers.

Stores precomputed site-wide stats in SyncState so `/api/v1/stats` can return a
persisted snapshot instead of recomputing expensive aggregates on every request.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_cached, set_cached, CACHE_TTL_SHORT
from app.models.models import Journalist, Outlet, Review, SyncState
from app.schemas.schemas import SiteStats

SITE_STATS_SYNC_STATE_KEY = "site_stats_snapshot:v1"
SITE_STATS_CACHE_KEY = "stats:site:v3"


async def compute_site_stats_snapshot(db: AsyncSession) -> SiteStats:
    """Compute site-wide statistics from source tables."""
    journalist_count = await db.execute(
        select(func.count()).select_from(Journalist).where(Journalist.avg_disparity.isnot(None))
    )
    total_journalists = journalist_count.scalar() or 0

    outlet_count = await db.execute(
        select(func.count()).select_from(Outlet).where(Outlet.avg_disparity.isnot(None))
    )
    total_outlets = outlet_count.scalar() or 0

    games_with_reviews = (
        select(Review.game_id)
        .where(Review.score_normalized.isnot(None), Review.score_normalized > 0)
        .distinct()
        .subquery()
    )
    game_count = await db.execute(select(func.count()).select_from(games_with_reviews))
    total_games = game_count.scalar() or 0

    review_count = await db.execute(
        select(func.count()).select_from(Review).where(
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
        )
    )
    total_reviews = review_count.scalar() or 0

    avg_disparity_result = await db.execute(
        select(func.avg(Journalist.avg_disparity)).where(Journalist.avg_disparity.isnot(None))
    )
    avg_disparity = avg_disparity_result.scalar()
    if avg_disparity is not None:
        avg_disparity = Decimal(str(round(float(avg_disparity), 2)))

    return SiteStats(
        total_journalists=total_journalists,
        total_outlets=total_outlets,
        total_games=total_games,
        total_reviews=total_reviews,
        avg_disparity_site=avg_disparity,
        last_updated=datetime.now(timezone.utc),
    )


async def get_stored_site_stats_snapshot(db: AsyncSession) -> Optional[SiteStats]:
    """Load the stored site stats snapshot (cache first, SyncState fallback)."""
    cached = await get_cached(SITE_STATS_CACHE_KEY)
    if cached:
        return SiteStats(**json.loads(cached))

    result = await db.execute(
        select(SyncState.value).where(SyncState.key == SITE_STATS_SYNC_STATE_KEY)
    )
    value = result.scalar_one_or_none()
    if not value:
        return None

    snapshot = SiteStats(**json.loads(value))
    await set_cached(
        SITE_STATS_CACHE_KEY,
        json.dumps(snapshot.model_dump(mode="json")),
        CACHE_TTL_SHORT,
    )
    return snapshot


async def store_site_stats_snapshot(
    db: AsyncSession,
    snapshot: SiteStats,
    *,
    commit: bool = True,
) -> None:
    """Persist a site stats snapshot into SyncState and update cache."""
    payload = json.dumps(snapshot.model_dump(mode="json"))
    stmt = insert(SyncState).values(key=SITE_STATS_SYNC_STATE_KEY, value=payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "value": stmt.excluded.value,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    if commit:
        await db.commit()
    await set_cached(SITE_STATS_CACHE_KEY, payload, CACHE_TTL_SHORT)


async def refresh_site_stats_snapshot(db: AsyncSession, *, commit: bool = True) -> SiteStats:
    """Recompute and persist the site stats snapshot."""
    snapshot = await compute_site_stats_snapshot(db)
    await store_site_stats_snapshot(db, snapshot, commit=commit)
    return snapshot


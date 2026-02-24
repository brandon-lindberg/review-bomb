"""
Core cache prewarming routines.

Prewarms the API/cache paths that dominate first user-facing page loads.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.routers import games, journalists, news, stats
from app.services.site_stats import refresh_site_stats_snapshot

# Call undecorated functions when invoking route handlers directly for prewarm.
_news_list_fn = getattr(news.list_news, "__wrapped__", news.list_news)
_news_sources_fn = getattr(news.list_sources, "__wrapped__", news.list_sources)


async def prewarm_core_caches_with_db(
    db: AsyncSession,
    *,
    top_journalist_details: int = 10,
) -> None:
    """Prewarm home + journalists list + top journalist detail caches using an existing DB session."""
    print("Prewarming core API caches...")

    # 1) Persist and cache site-wide stats snapshot.
    await refresh_site_stats_snapshot(db, commit=False)

    # 2) Home page dependencies.
    await stats.get_recent_reviews(limit=5, db=db)
    await games.list_games(
        page=1,
        per_page=5,
        year=None,
        search=None,
        sort_by="release_date",
        sort_order="desc",
        db=db,
    )
    await _news_list_fn(request=None, page=1, per_page=5, source=None, search=None, db=db)
    await _news_sources_fn(request=None, db=db)

    # 3) Journalists list (default page).
    journalist_list = await journalists.list_journalists(
        page=1,
        per_page=20,
        search=None,
        sort_by="latest_review",
        sort_order="desc",
        db=db,
    )

    # 4) Top journalist detail caches (by the warmed default list).
    for item in journalist_list.items[:top_journalist_details]:
        try:
            await journalists.get_journalist(item.id, db=db)
        except Exception as exc:
            # Continue warming the rest; one bad journalist should not fail the job.
            print(f"Cache prewarm warning (journalist {item.id}): {exc}")

    await db.commit()
    print("Core API cache prewarm complete.")


async def prewarm_core_caches(*, top_journalist_details: int = 10) -> None:
    """Prewarm core API caches with a fresh DB session."""
    async with async_session_maker() as db:
        await prewarm_core_caches_with_db(db, top_journalist_details=top_journalist_details)

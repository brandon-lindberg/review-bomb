"""
API endpoints for gaming news articles.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_cached, set_cached, cache_key, CACHE_TTL_MEDIUM
from app.database import get_db
from app.models.models import NewsArticle
from app.schemas.schemas import PaginatedResponse, NewsArticleSummary

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("", response_model=PaginatedResponse[NewsArticleSummary])
@limiter.limit("30/minute")
async def list_news(
    request: Request,
    page: int = Query(1, ge=1, le=15),
    per_page: int = Query(20, ge=1, le=50),
    source: Optional[str] = Query(None, max_length=100),
    search: Optional[str] = Query(None, max_length=200),
    db: AsyncSession = Depends(get_db),
):
    """List recent gaming news articles with pagination."""
    # Check cache
    key = cache_key("news", page=page, per_page=per_page, source=source, search=search)
    cached = await get_cached(f"news:{key}")
    if cached:
        return PaginatedResponse[NewsArticleSummary](**json.loads(cached))

    # Build query
    query = select(NewsArticle)
    count_query = select(func.count()).select_from(NewsArticle)

    if source:
        query = query.where(NewsArticle.source_name == source)
        count_query = count_query.where(NewsArticle.source_name == source)

    if search:
        search_filter = or_(
            NewsArticle.title.ilike(f"%{search}%"),
            NewsArticle.description.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    query = query.order_by(desc(NewsArticle.published_at).nulls_last())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    articles = result.scalars().all()

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    response = PaginatedResponse(
        items=[NewsArticleSummary.model_validate(a) for a in articles],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )

    # Cache for 5 minutes
    await set_cached(
        f"news:{key}",
        response.model_dump_json(),
        expire_seconds=CACHE_TTL_MEDIUM,
    )

    return response


@router.get("/sources", response_model=list[str])
@limiter.limit("30/minute")
async def list_sources(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List available news sources."""
    cached = await get_cached("news:sources")
    if cached:
        return json.loads(cached)

    result = await db.execute(
        select(NewsArticle.source_name)
        .distinct()
        .order_by(NewsArticle.source_name)
    )
    sources = [row[0] for row in result.all()]

    await set_cached("news:sources", json.dumps(sources), expire_seconds=CACHE_TTL_MEDIUM)

    return sources

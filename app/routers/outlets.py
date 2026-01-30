"""Outlets API endpoints."""

from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Outlet, Review, Journalist, Game, DisparitySnapshot
from app.schemas.schemas import (
    OutletSummary,
    OutletDetail,
    OutletWithStats,
    JournalistSummary,
    ReviewWithJournalist,
    PaginatedResponse,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[OutletWithStats])
async def list_outlets(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort_by: str = Query("disparity", regex="^(disparity|name|review_count)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all outlets with pagination and sorting."""
    # Subquery for review and journalist counts
    stats_subq = (
        select(
            Review.outlet_id,
            func.count(Review.id).label("review_count"),
            func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
        )
        .where(Review.outlet_id.isnot(None))
        .group_by(Review.outlet_id)
        .subquery()
    )

    # Get latest disparity snapshot for each outlet
    disparity_subq = (
        select(
            DisparitySnapshot.outlet_id,
            DisparitySnapshot.avg_disparity_combined,
        )
        .where(DisparitySnapshot.outlet_id.isnot(None))
        .distinct(DisparitySnapshot.outlet_id)
        .order_by(DisparitySnapshot.outlet_id, desc(DisparitySnapshot.snapshot_date))
        .subquery()
    )

    query = (
        select(
            Outlet,
            func.coalesce(stats_subq.c.review_count, 0).label("review_count"),
            func.coalesce(stats_subq.c.journalist_count, 0).label("journalist_count"),
            disparity_subq.c.avg_disparity_combined.label("avg_disparity"),
        )
        .outerjoin(stats_subq, Outlet.id == stats_subq.c.outlet_id)
        .outerjoin(disparity_subq, Outlet.id == disparity_subq.c.outlet_id)
    )

    # Apply sorting
    if sort_by == "disparity":
        order_col = disparity_subq.c.avg_disparity_combined
    elif sort_by == "name":
        order_col = Outlet.name
    else:  # review_count
        order_col = stats_subq.c.review_count

    if sort_order == "desc":
        query = query.order_by(desc(order_col).nulls_last())
    else:
        query = query.order_by(asc(order_col).nulls_last())

    # Get total count
    count_query = select(func.count()).select_from(Outlet)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = [
        OutletWithStats(
            id=row[0].id,
            name=row[0].name,
            website_url=row[0].website_url,
            logo_url=row[0].logo_url,
            opencritic_id=row[0].opencritic_id,
            journalist_count=row[2],
            review_count=row[1],
            avg_disparity=row[3],
        )
        for row in rows
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{outlet_id}", response_model=OutletWithStats)
async def get_outlet(
    outlet_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get outlet detail with stats."""
    result = await db.execute(
        select(Outlet).where(Outlet.id == outlet_id)
    )
    outlet = result.scalar_one_or_none()

    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Get stats
    stats_query = select(
        func.count(Review.id).label("review_count"),
        func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
    ).where(Review.outlet_id == outlet_id)

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    # Get latest disparity
    disparity_query = (
        select(DisparitySnapshot.avg_disparity_combined)
        .where(DisparitySnapshot.outlet_id == outlet_id)
        .order_by(desc(DisparitySnapshot.snapshot_date))
        .limit(1)
    )
    disparity_result = await db.execute(disparity_query)
    avg_disparity = disparity_result.scalar_one_or_none()

    return OutletWithStats(
        id=outlet.id,
        name=outlet.name,
        website_url=outlet.website_url,
        logo_url=outlet.logo_url,
        opencritic_id=outlet.opencritic_id,
        journalist_count=stats_row.journalist_count or 0,
        review_count=stats_row.review_count or 0,
        avg_disparity=avg_disparity,
    )


@router.get("/{outlet_id}/journalists", response_model=PaginatedResponse[JournalistSummary])
async def get_outlet_journalists(
    outlet_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get journalists who have written for this outlet."""
    # Verify outlet exists
    outlet_result = await db.execute(
        select(Outlet.id).where(Outlet.id == outlet_id)
    )
    if not outlet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Subquery for journalists at this outlet with review count
    journalist_stats_subq = (
        select(
            Review.journalist_id,
            func.count(Review.id).label("review_count"),
        )
        .where(Review.outlet_id == outlet_id)
        .group_by(Review.journalist_id)
        .subquery()
    )

    # Get total count of unique journalists
    count_query = (
        select(func.count(func.distinct(Review.journalist_id)))
        .where(Review.outlet_id == outlet_id)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get journalists
    query = (
        select(Journalist, journalist_stats_subq.c.review_count)
        .join(journalist_stats_subq, Journalist.id == journalist_stats_subq.c.journalist_id)
        .order_by(desc(journalist_stats_subq.c.review_count))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = [
        JournalistSummary(
            id=row[0].id,
            name=row[0].name,
            image_url=row[0].image_url,
            bio=row[0].bio,
            opencritic_id=row[0].opencritic_id,
            review_count=row[1],
            avg_disparity=None,  # Would need per-outlet disparity
        )
        for row in rows
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{outlet_id}/reviews", response_model=PaginatedResponse[ReviewWithJournalist])
async def get_outlet_reviews(
    outlet_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get all reviews from this outlet."""
    # Verify outlet exists
    outlet_result = await db.execute(
        select(Outlet.id).where(Outlet.id == outlet_id)
    )
    if not outlet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(Review.outlet_id == outlet_id)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reviews
    query = (
        select(Review, Journalist, Game)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .join(Game, Review.game_id == Game.id)
        .where(Review.outlet_id == outlet_id)
        .order_by(desc(Review.published_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = [
        ReviewWithJournalist(
            id=row[0].id,
            journalist_id=row[0].journalist_id,
            game_id=row[0].game_id,
            outlet_id=row[0].outlet_id,
            score_raw=row[0].score_raw,
            score_scale=row[0].score_scale,
            score_normalized=row[0].score_normalized,
            review_url=row[0].review_url,
            snippet=row[0].snippet,
            published_at=row[0].published_at,
            journalist_name=row[1].name,
            journalist_image_url=row[1].image_url,
            outlet_name=None,  # We already know the outlet
            disparity_steam=None,
            disparity_metacritic=None,
        )
        for row in rows
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )

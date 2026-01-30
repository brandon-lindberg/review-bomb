"""Journalists API endpoints."""

from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.models import Journalist, Review, Outlet, Game, UserScore, DisparitySnapshot
from app.schemas.schemas import (
    JournalistSummary,
    JournalistDetail,
    JournalistStats,
    JournalistOutletBreakdown,
    ReviewWithDisparity,
    PaginatedResponse,
    DisparitySnapshot as DisparitySnapshotSchema,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[JournalistSummary])
async def list_journalists(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    sort_by: str = Query("disparity", regex="^(disparity|name|review_count)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all journalists with pagination and sorting."""
    # Build base query with review count and avg disparity
    subq = (
        select(
            Review.journalist_id,
            func.count(Review.id).label("review_count"),
        )
        .group_by(Review.journalist_id)
        .subquery()
    )

    # Get latest disparity snapshot for each journalist
    disparity_subq = (
        select(
            DisparitySnapshot.journalist_id,
            DisparitySnapshot.avg_disparity_combined,
        )
        .where(DisparitySnapshot.journalist_id.isnot(None))
        .distinct(DisparitySnapshot.journalist_id)
        .order_by(DisparitySnapshot.journalist_id, desc(DisparitySnapshot.snapshot_date))
        .subquery()
    )

    query = (
        select(
            Journalist,
            func.coalesce(subq.c.review_count, 0).label("review_count"),
            disparity_subq.c.avg_disparity_combined.label("avg_disparity"),
        )
        .outerjoin(subq, Journalist.id == subq.c.journalist_id)
        .outerjoin(disparity_subq, Journalist.id == disparity_subq.c.journalist_id)
    )

    # Apply sorting
    if sort_by == "disparity":
        order_col = disparity_subq.c.avg_disparity_combined
    elif sort_by == "name":
        order_col = Journalist.name
    else:  # review_count
        order_col = subq.c.review_count

    if sort_order == "desc":
        query = query.order_by(desc(order_col).nulls_last())
    else:
        query = query.order_by(asc(order_col).nulls_last())

    # Get total count
    count_query = select(func.count()).select_from(Journalist)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        journalist = row[0]
        review_count = row[1]
        avg_disparity = row[2]

        items.append(
            JournalistSummary(
                id=journalist.id,
                name=journalist.name,
                image_url=journalist.image_url,
                bio=journalist.bio,
                opencritic_id=journalist.opencritic_id,
                review_count=review_count,
                avg_disparity=avg_disparity,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{journalist_id}", response_model=JournalistDetail)
async def get_journalist(
    journalist_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get journalist detail with stats and outlet breakdown."""
    # Get journalist
    result = await db.execute(
        select(Journalist).where(Journalist.id == journalist_id)
    )
    journalist = result.scalar_one_or_none()

    if not journalist:
        raise HTTPException(status_code=404, detail="Journalist not found")

    # Get review stats
    stats_query = select(
        func.count(Review.id).label("total_reviews"),
        func.avg(Review.score_normalized).label("avg_score_given"),
    ).where(Review.journalist_id == journalist_id)

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    # Get latest disparity snapshot
    disparity_query = (
        select(DisparitySnapshot)
        .where(DisparitySnapshot.journalist_id == journalist_id)
        .order_by(desc(DisparitySnapshot.snapshot_date))
        .limit(1)
    )
    disparity_result = await db.execute(disparity_query)
    disparity = disparity_result.scalar_one_or_none()

    # Get outlet breakdown
    outlet_breakdown_query = (
        select(
            Outlet.id.label("outlet_id"),
            Outlet.name.label("outlet_name"),
            func.count(Review.id).label("review_count"),
            func.min(Review.published_at).label("date_range_start"),
            func.max(Review.published_at).label("date_range_end"),
        )
        .join(Review, Review.outlet_id == Outlet.id)
        .where(Review.journalist_id == journalist_id)
        .group_by(Outlet.id, Outlet.name)
        .order_by(desc(func.count(Review.id)))
    )
    outlet_result = await db.execute(outlet_breakdown_query)
    outlet_rows = outlet_result.all()

    outlet_breakdown = [
        JournalistOutletBreakdown(
            outlet_id=row.outlet_id,
            outlet_name=row.outlet_name,
            review_count=row.review_count,
            avg_disparity=None,  # Would need per-outlet disparity calculation
            date_range_start=row.date_range_start.date() if row.date_range_start else None,
            date_range_end=row.date_range_end.date() if row.date_range_end else None,
        )
        for row in outlet_rows
    ]

    stats = JournalistStats(
        total_reviews=stats_row.total_reviews or 0,
        avg_score_given=Decimal(str(round(stats_row.avg_score_given, 2))) if stats_row.avg_score_given else None,
        avg_disparity_steam=disparity.avg_disparity_steam if disparity else None,
        avg_disparity_metacritic=disparity.avg_disparity_metacritic if disparity else None,
        avg_disparity_combined=disparity.avg_disparity_combined if disparity else None,
        std_deviation=disparity.std_deviation if disparity else None,
        alignment_rating=None,  # Calculate based on disparity threshold
    )

    return JournalistDetail(
        id=journalist.id,
        name=journalist.name,
        image_url=journalist.image_url,
        bio=journalist.bio,
        opencritic_id=journalist.opencritic_id,
        review_count=stats_row.total_reviews or 0,
        avg_disparity=disparity.avg_disparity_combined if disparity else None,
        stats=stats,
        outlet_breakdown=outlet_breakdown,
        created_at=journalist.created_at,
        updated_at=journalist.updated_at,
    )


@router.get("/{journalist_id}/reviews", response_model=PaginatedResponse[ReviewWithDisparity])
async def get_journalist_reviews(
    journalist_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated reviews for a journalist, newest first."""
    # Verify journalist exists
    journalist_result = await db.execute(
        select(Journalist.id).where(Journalist.id == journalist_id)
    )
    if not journalist_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Journalist not found")

    # Get total count
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(Review.journalist_id == journalist_id)
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reviews with game and outlet info
    query = (
        select(Review, Game, Outlet)
        .join(Game, Review.game_id == Game.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(Review.journalist_id == journalist_id)
        .order_by(desc(Review.published_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    # Get user scores for the games
    game_ids = [row[1].id for row in rows]
    user_scores_query = (
        select(UserScore)
        .where(UserScore.game_id.in_(game_ids))
        .order_by(desc(UserScore.scraped_at))
    )
    user_scores_result = await db.execute(user_scores_query)
    user_scores = user_scores_result.scalars().all()

    # Build lookup for latest user scores by game and source
    user_score_lookup: dict = {}
    for us in user_scores:
        key = (us.game_id, us.source.value)
        if key not in user_score_lookup:
            user_score_lookup[key] = us

    items = []
    for review, game, outlet in rows:
        steam_score = user_score_lookup.get((game.id, "steam"))
        metacritic_score = user_score_lookup.get((game.id, "metacritic"))

        steam_user_score = steam_score.score if steam_score else None
        metacritic_user_score = metacritic_score.score if metacritic_score else None

        disparity_steam = None
        disparity_metacritic = None

        if steam_user_score:
            disparity_steam = review.score_normalized - steam_user_score
        if metacritic_user_score:
            disparity_metacritic = review.score_normalized - metacritic_user_score

        items.append(
            ReviewWithDisparity(
                id=review.id,
                journalist_id=review.journalist_id,
                game_id=review.game_id,
                outlet_id=review.outlet_id,
                score_raw=review.score_raw,
                score_scale=review.score_scale,
                score_normalized=review.score_normalized,
                review_url=review.review_url,
                snippet=review.snippet,
                published_at=review.published_at,
                game_title=game.title,
                outlet_name=outlet.name if outlet else None,
                steam_user_score=steam_user_score,
                metacritic_user_score=metacritic_user_score,
                disparity_steam=disparity_steam,
                disparity_metacritic=disparity_metacritic,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{journalist_id}/history", response_model=list[DisparitySnapshotSchema])
async def get_journalist_history(
    journalist_id: int,
    limit: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get historical disparity data for charts."""
    # Verify journalist exists
    journalist_result = await db.execute(
        select(Journalist.id).where(Journalist.id == journalist_id)
    )
    if not journalist_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Journalist not found")

    query = (
        select(DisparitySnapshot)
        .where(DisparitySnapshot.journalist_id == journalist_id)
        .order_by(desc(DisparitySnapshot.snapshot_date))
        .limit(limit)
    )

    result = await db.execute(query)
    snapshots = result.scalars().all()

    return [
        DisparitySnapshotSchema(
            date=s.snapshot_date,
            avg_disparity_steam=s.avg_disparity_steam,
            avg_disparity_metacritic=s.avg_disparity_metacritic,
            avg_disparity_combined=s.avg_disparity_combined,
            review_count=s.review_count,
        )
        for s in reversed(snapshots)  # Return in chronological order
    ]

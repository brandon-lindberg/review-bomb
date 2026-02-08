"""Outlets API endpoints."""

from datetime import datetime
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
    DisparitySnapshot as DisparitySnapshotSchema,
)

router = APIRouter()

# Anti-gaming constants
LAUNCH_WINDOW_DAYS = 60
# Minimum user reviews required for disparity calculation (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20


def calculate_review_timing(review_date, game_release_date) -> str:
    """
    Calculate review timing category.

    Returns:
        "early" - Review published before game release
        "launch_window" - Review published within 60 days of release
        "late" - Review published more than 60 days after release
        "unknown" - Cannot determine (missing dates)
    """
    if not review_date or not game_release_date:
        return "unknown"

    days_after_release = (review_date - game_release_date).days

    if days_after_release < 0:
        return "early"
    elif days_after_release <= LAUNCH_WINDOW_DAYS:
        return "launch_window"
    else:
        return "late"


@router.get("", response_model=PaginatedResponse[OutletWithStats])
async def list_outlets(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    sort_by: str = Query("latest_review", regex="^(disparity|name|review_count|latest_review)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all outlets with pagination, sorting, and search."""
    # Subquery for review and journalist counts (only scored reviews)
    today = datetime.utcnow()
    stats_subq = (
        select(
            Review.outlet_id,
            func.count(Review.id).label("review_count"),
            func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
            func.avg(Review.score_normalized).label("avg_score"),
            func.max(Review.published_at).label("latest_review_date"),
        )
        .where(
            Review.outlet_id.isnot(None),
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
            Review.published_at <= today,  # Exclude future dates (bad data)
        )
        .group_by(Review.outlet_id)
        .subquery()
    )

    # Get latest disparity snapshot for each outlet
    disparity_subq = (
        select(
            DisparitySnapshot.outlet_id,
            DisparitySnapshot.avg_disparity_steam,
            DisparitySnapshot.avg_disparity_metacritic,
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
            stats_subq.c.avg_score.label("avg_score"),
            disparity_subq.c.avg_disparity_steam.label("avg_disparity_steam"),
            disparity_subq.c.avg_disparity_metacritic.label("avg_disparity_metacritic"),
            disparity_subq.c.avg_disparity_combined.label("avg_disparity"),
            stats_subq.c.latest_review_date.label("latest_review_date"),
        )
        .join(stats_subq, Outlet.id == stats_subq.c.outlet_id)  # INNER JOIN - only outlets with scored reviews
        .outerjoin(disparity_subq, Outlet.id == disparity_subq.c.outlet_id)
    )

    # Filter by search term if provided
    if search:
        query = query.where(Outlet.name.ilike(f"%{search}%"))

    # Apply sorting
    if sort_by == "disparity":
        order_col = disparity_subq.c.avg_disparity_combined
    elif sort_by == "name":
        order_col = Outlet.name
    elif sort_by == "latest_review":
        order_col = stats_subq.c.latest_review_date
    else:  # review_count
        order_col = stats_subq.c.review_count

    if sort_order == "desc":
        query = query.order_by(desc(order_col).nulls_last())
    else:
        query = query.order_by(asc(order_col).nulls_last())

    # Get total count (only outlets with scored reviews)
    count_query = (
        select(func.count(Outlet.id.distinct()))
        .select_from(Outlet)
        .join(stats_subq, Outlet.id == stats_subq.c.outlet_id)
    )
    if search:
        count_query = count_query.where(Outlet.name.ilike(f"%{search}%"))
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
            avg_score=row[3],
            avg_disparity_steam=row[4],
            avg_disparity_metacritic=row[5],
            avg_disparity=row[6],
            avg_disparity_combined=row[6],
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

    # Get stats (only scored reviews) including average score
    stats_query = select(
        func.count(Review.id).label("review_count"),
        func.count(func.distinct(Review.journalist_id)).label("journalist_count"),
        func.avg(Review.score_normalized).label("avg_score"),
        func.min(Review.score_normalized).label("min_score"),
        func.max(Review.score_normalized).label("max_score"),
        func.stddev(Review.score_normalized).label("score_std_dev"),
    ).where(
        Review.outlet_id == outlet_id,
        Review.score_normalized.isnot(None),  # Only scored reviews
        Review.score_normalized > 0,  # Exclude unscored (0) reviews
    )

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    # Get latest disparity snapshot with all disparity fields
    disparity_query = (
        select(
            DisparitySnapshot.avg_disparity_steam,
            DisparitySnapshot.avg_disparity_metacritic,
            DisparitySnapshot.avg_disparity_combined,
        )
        .where(DisparitySnapshot.outlet_id == outlet_id)
        .order_by(desc(DisparitySnapshot.snapshot_date))
        .limit(1)
    )
    disparity_result = await db.execute(disparity_query)
    disparity_row = disparity_result.one_or_none()

    avg_disparity_steam = None
    avg_disparity_metacritic = None
    avg_disparity_combined = None
    if disparity_row:
        avg_disparity_steam = disparity_row.avg_disparity_steam
        avg_disparity_metacritic = disparity_row.avg_disparity_metacritic
        avg_disparity_combined = disparity_row.avg_disparity_combined

    return OutletWithStats(
        id=outlet.id,
        name=outlet.name,
        website_url=outlet.website_url,
        logo_url=outlet.logo_url,
        opencritic_id=outlet.opencritic_id,
        journalist_count=stats_row.journalist_count or 0,
        review_count=stats_row.review_count or 0,
        avg_disparity=avg_disparity_combined,
        avg_disparity_steam=avg_disparity_steam,
        avg_disparity_metacritic=avg_disparity_metacritic,
        avg_disparity_combined=avg_disparity_combined,
        avg_score=stats_row.avg_score,
        # Transparency metrics - scoring patterns
        min_score_given=Decimal(str(round(stats_row.min_score, 2))) if stats_row.min_score else None,
        max_score_given=Decimal(str(round(stats_row.max_score, 2))) if stats_row.max_score else None,
        score_std_deviation=Decimal(str(round(stats_row.score_std_dev, 2))) if stats_row.score_std_dev else None,
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

    # Subquery for journalists at this outlet with review count (only scored reviews)
    journalist_stats_subq = (
        select(
            Review.journalist_id,
            func.count(Review.id).label("review_count"),
        )
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .group_by(Review.journalist_id)
        .subquery()
    )

    # Get total count of unique journalists (from scored reviews)
    count_query = (
        select(func.count(func.distinct(Review.journalist_id)))
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
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
    from app.models.models import UserScore

    # Verify outlet exists
    outlet_result = await db.execute(
        select(Outlet.id).where(Outlet.id == outlet_id)
    )
    if not outlet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Get total count (only scored reviews)
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reviews (only scored reviews)
    query = (
        select(Review, Journalist, Game)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .join(Game, Review.game_id == Game.id)
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .order_by(desc(Review.published_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    # Get user scores for all games in the result set for disparity calculation
    game_ids = list(set(row[2].id for row in rows))
    user_scores = {}
    if game_ids:
        # Get latest Steam scores with sample size
        steam_subq = (
            select(
                UserScore.game_id,
                UserScore.score,
                UserScore.sample_size,
                func.row_number().over(
                    partition_by=UserScore.game_id,
                    order_by=desc(UserScore.scraped_at)
                ).label("rn")
            )
            .where(UserScore.game_id.in_(game_ids), UserScore.source == "STEAM")
            .subquery()
        )
        steam_query = select(
            steam_subq.c.game_id,
            steam_subq.c.score,
            steam_subq.c.sample_size
        ).where(steam_subq.c.rn == 1)
        steam_result = await db.execute(steam_query)
        for gid, score, sample_size in steam_result.all():
            if gid not in user_scores:
                user_scores[gid] = {}
            user_scores[gid]["steam"] = {"score": score, "sample_size": sample_size}

        # Get latest Metacritic scores with sample size
        mc_subq = (
            select(
                UserScore.game_id,
                UserScore.score,
                UserScore.sample_size,
                func.row_number().over(
                    partition_by=UserScore.game_id,
                    order_by=desc(UserScore.scraped_at)
                ).label("rn")
            )
            .where(UserScore.game_id.in_(game_ids), UserScore.source == "METACRITIC")
            .subquery()
        )
        mc_query = select(
            mc_subq.c.game_id,
            mc_subq.c.score,
            mc_subq.c.sample_size
        ).where(mc_subq.c.rn == 1)
        mc_result = await db.execute(mc_query)
        for gid, score, sample_size in mc_result.all():
            if gid not in user_scores:
                user_scores[gid] = {}
            user_scores[gid]["metacritic"] = {"score": score, "sample_size": sample_size}

    items = []
    for review, journalist, game in rows:
        game_user_scores = user_scores.get(game.id, {})
        steam_data = game_user_scores.get("steam")
        metacritic_data = game_user_scores.get("metacritic")

        disparity_steam = None
        disparity_metacritic = None
        # Only calculate disparity if sample size meets minimum threshold (per source)
        # Steam always provides sample_size, so we require it
        if steam_data and steam_data["sample_size"] and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS:
            disparity_steam = review.score_normalized - steam_data["score"]
        # Metacritic doesn't always expose sample_size - if score exists, allow it through
        if metacritic_data and metacritic_data["score"] and (
            metacritic_data["sample_size"] is None or metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS
        ):
            disparity_metacritic = review.score_normalized - metacritic_data["score"]

        # Calculate review timing (early/launch_window/late)
        review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
        review_timing = calculate_review_timing(review_date, game.release_date)

        items.append(
            ReviewWithJournalist(
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
                journalist_name=journalist.name,
                journalist_image_url=journalist.image_url,
                outlet_name=None,  # We already know the outlet
                game_title=game.title,
                game_release_date=game.release_date,
                disparity_steam=disparity_steam,
                disparity_metacritic=disparity_metacritic,
                is_launch_window=review_timing == "launch_window",  # Backward compatibility
                review_timing=review_timing,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{outlet_id}/history", response_model=list[DisparitySnapshotSchema])
async def get_outlet_history(
    outlet_id: int,
    limit: int = Query(10000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get historical disparity data for charts. Returns full timeline."""
    # Verify outlet exists
    outlet_result = await db.execute(
        select(Outlet.id).where(Outlet.id == outlet_id)
    )
    if not outlet_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Outlet not found")

    query = (
        select(DisparitySnapshot)
        .where(DisparitySnapshot.outlet_id == outlet_id)
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

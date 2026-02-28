"""Outlets API endpoints."""

from datetime import datetime
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc, case, and_, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.models import Outlet, Review, Journalist, Game, DisparitySnapshot
from app.public_ids import resolve_entity_by_identifier
from app.schemas.schemas import (
    OutletSummary,
    OutletDetail,
    OutletWithStats,
    JournalistSummary,
    ReviewWithJournalist,
    PaginatedResponse,
    DisparitySnapshot as DisparitySnapshotSchema,
)
from app.services.review_score_correction import corrected_normalized_score

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Anti-gaming constants
LAUNCH_WINDOW_DAYS = 60
# Leaderboard-style minimums for disparity sorting in the outlets list
MIN_REVIEWS_FOR_DISPARITY_SORT = 10
MIN_SCORE_STD_DEV_FOR_DISPARITY_SORT = 10


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
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    sort_by: str = Query("latest_review", regex="^(disparity|name|review_count|latest_review)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all outlets with pagination, sorting, and search (uses denormalized columns)."""
    # Use denormalized columns for fast queries.
    # For disparity sorting, enforce leaderboard anti-gaming thresholds.
    filters = [
        Outlet.review_count_scored.isnot(None),
        Outlet.review_count_scored >= MIN_REVIEWS_FOR_DISPARITY_SORT,
    ]
    if sort_by == "disparity":
        filters.extend([
            Outlet.avg_disparity.isnot(None),
            Outlet.review_count_scored >= MIN_REVIEWS_FOR_DISPARITY_SORT,
            func.coalesce(Outlet.score_std_dev, 0) >= MIN_SCORE_STD_DEV_FOR_DISPARITY_SORT,
        ])

    query = select(
        Outlet,
        func.count().over().label("total_count"),
    ).where(*filters)

    # Filter by search term if provided
    if search:
        query = query.where(Outlet.name.ilike(f"%{search}%"))

    # Apply sorting using denormalized columns
    if sort_by == "disparity":
        order_col = func.abs(Outlet.avg_disparity)
    elif sort_by == "name":
        order_col = Outlet.name
    elif sort_by == "latest_review":
        order_col = Outlet.last_review_at
    else:  # review_count
        order_col = Outlet.review_count_scored

    if sort_by == "disparity":
        if sort_order == "desc":
            query = query.order_by(
                desc(order_col).nulls_last(),
                desc(Outlet.review_count_scored).nulls_last(),
                asc(Outlet.id),
            )
        else:
            query = query.order_by(
                asc(order_col).nulls_last(),
                desc(Outlet.review_count_scored).nulls_last(),
                asc(Outlet.id),
            )
    else:
        if sort_order == "desc":
            query = query.order_by(desc(order_col).nulls_last())
        else:
            query = query.order_by(asc(order_col).nulls_last())

    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()
    outlets = [row[0] for row in rows]
    total = rows[0].total_count if rows else 0

    if not rows and page > 1:
        count_query = select(func.count()).select_from(Outlet).where(*filters)
        if search:
            count_query = count_query.where(Outlet.name.ilike(f"%{search}%"))
        total = (await db.execute(count_query)).scalar() or 0

    items = [
        OutletWithStats(
            id=outlet.id,
            public_id=outlet.public_id or str(outlet.id),
            name=outlet.name,
            website_url=outlet.website_url,
            logo_url=outlet.logo_url,
            opencritic_id=outlet.opencritic_id,
            is_binary_scorer=bool(outlet.is_binary_scorer),
            journalist_count=outlet.journalist_count or 0,
            review_count=outlet.review_count_scored or 0,
            avg_score=None,  # Not stored denormalized, not critical for list view
            avg_disparity_steam=None,  # Only combined is stored
            avg_disparity_metacritic=None,  # Only combined is stored
            avg_disparity=outlet.avg_disparity,
            avg_disparity_combined=outlet.avg_disparity,
        )
        for outlet in outlets
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
    outlet_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get outlet detail using denormalized columns - fast!"""
    outlet = await resolve_entity_by_identifier(db, Outlet, str(outlet_id))
    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")
    outlet_id = outlet.id

    # Get score and timing metrics in one aggregate query.
    review_date_expr = cast(Review.published_at, Date)
    days_after_release_expr = review_date_expr - Game.release_date

    metrics_query = select(
        func.avg(Review.score_normalized).label("avg_score"),
        func.min(Review.score_normalized).label("min_score"),
        func.max(Review.score_normalized).label("max_score"),
        func.sum(
            case(
                (
                    and_(
                        review_date_expr.isnot(None),
                        Game.release_date.isnot(None),
                        days_after_release_expr < 0,
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("early_review_count"),
        func.sum(
            case(
                (
                    and_(
                        review_date_expr.isnot(None),
                        Game.release_date.isnot(None),
                        days_after_release_expr >= 0,
                        days_after_release_expr <= LAUNCH_WINDOW_DAYS,
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("launch_window_review_count"),
        func.sum(
            case(
                (
                    and_(
                        review_date_expr.isnot(None),
                        Game.release_date.isnot(None),
                        days_after_release_expr > LAUNCH_WINDOW_DAYS,
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("late_review_count"),
    ).select_from(Review).join(
        Game, Review.game_id == Game.id
    ).where(
        Review.outlet_id == outlet_id,
        Review.score_normalized.isnot(None),
    )
    metrics_row = (await db.execute(metrics_query)).one()

    # Per-source disparities come from the latest precomputed outlet snapshot.
    # This avoids expensive per-request recomputation across all outlet games.
    snapshot = (
        await db.execute(
            select(DisparitySnapshot)
            .where(DisparitySnapshot.outlet_id == outlet_id)
            .order_by(desc(DisparitySnapshot.snapshot_date), desc(DisparitySnapshot.id))
            .limit(1)
        )
    ).scalar_one_or_none()

    avg_disparity_steam = snapshot.avg_disparity_steam if snapshot else None
    avg_disparity_metacritic = snapshot.avg_disparity_metacritic if snapshot else None
    calculated_avg_disparity_combined = snapshot.avg_disparity_combined if snapshot else None

    # Keep outlet detail aligned with outlets list/leaderboards:
    # prefer the canonical denormalized combined value, then snapshot fallback.
    display_avg_disparity_combined = (
        outlet.avg_disparity
        if outlet.avg_disparity is not None
        else calculated_avg_disparity_combined
    )

    return OutletWithStats(
        id=outlet.id,
        public_id=outlet.public_id or str(outlet.id),
        name=outlet.name,
        website_url=outlet.website_url,
        logo_url=outlet.logo_url,
        opencritic_id=outlet.opencritic_id,
        is_binary_scorer=bool(outlet.is_binary_scorer),
        journalist_count=outlet.journalist_count or 0,
        review_count=outlet.review_count_scored or 0,
        avg_disparity=outlet.avg_disparity,
        avg_disparity_steam=avg_disparity_steam,
        avg_disparity_metacritic=avg_disparity_metacritic,
        avg_disparity_combined=display_avg_disparity_combined,
        avg_score=metrics_row.avg_score,
        early_review_count=int(metrics_row.early_review_count or 0),
        launch_window_review_count=int(metrics_row.launch_window_review_count or 0),
        late_review_count=int(metrics_row.late_review_count or 0),
        min_score_given=Decimal(str(round(metrics_row.min_score, 2))) if metrics_row.min_score else None,
        max_score_given=Decimal(str(round(metrics_row.max_score, 2))) if metrics_row.max_score else None,
        score_std_deviation=outlet.score_std_dev,
    )


@router.get("/{outlet_id}/journalists", response_model=PaginatedResponse[JournalistSummary])
async def get_outlet_journalists(
    outlet_id: str,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get journalists who have written for this outlet."""
    outlet = await resolve_entity_by_identifier(db, Outlet, str(outlet_id))
    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")
    outlet_id = outlet.id

    # Subquery for journalists at this outlet with review count (only scored reviews)
    journalist_stats_subq = (
        select(
            Review.journalist_id,
            func.count(Review.id).label("review_count"),
        )
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
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
            public_id=row[0].public_id or str(row[0].id),
            name=row[0].name,
            image_url=row[0].image_url,
            bio=row[0].bio,
            opencritic_id=row[0].opencritic_id,
            is_binary_reviewer=bool(row[0].is_binary_reviewer),
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
@limiter.limit("60/minute")
async def get_outlet_reviews(
    request: Request,
    outlet_id: str,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get all reviews from this outlet."""
    outlet = await resolve_entity_by_identifier(db, Outlet, str(outlet_id))
    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")
    outlet_id = outlet.id

    # Get total count (only scored reviews, including 0)
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reviews (only scored reviews, including 0)
    query = (
        select(Review, Journalist, Game)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .join(Game, Review.game_id == Game.id)
        .where(
            Review.outlet_id == outlet_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
        )
        .order_by(desc(Review.published_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    corrected_count = 0
    for review, journalist, game in rows:
        corrected_score, was_corrected = corrected_normalized_score(
            score_raw=review.score_raw,
            score_scale=review.score_scale,
            stored_score_normalized=review.score_normalized,
        )
        if was_corrected:
            corrected_count += 1

        disparity_steam = review.cached_disparity_steam
        disparity_metacritic = review.cached_disparity_metacritic

        # Calculate review timing (early/launch_window/late)
        review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
        review_timing = calculate_review_timing(review_date, game.release_date)

        items.append(
            ReviewWithJournalist(
                id=review.id,
                journalist_id=review.journalist_id,
                journalist_public_id=journalist.public_id or str(journalist.id),
                game_id=review.game_id,
                game_public_id=game.public_id or str(game.id),
                outlet_id=review.outlet_id,
                outlet_public_id=outlet.public_id or str(outlet.id),
                score_raw=review.score_raw,
                score_scale=review.score_scale,
                score_normalized=corrected_score,
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

    if corrected_count:
        print(
            f"Runtime score corrections (outlet_id={outlet_id}): "
            f"{corrected_count}/{len(rows)}"
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
    outlet_id: str,
    limit: int = Query(10000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get historical disparity data for charts. Returns full timeline."""
    outlet = await resolve_entity_by_identifier(db, Outlet, str(outlet_id))
    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")
    outlet_id = outlet.id

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

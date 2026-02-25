"""Journalists API endpoints."""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc, case, and_
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.models import (
    Journalist,
    Review,
    Outlet,
    Game,
    DisparitySnapshot,
    JournalistOutletDisparitySnapshot,
)
from app.schemas.schemas import (
    JournalistSummary,
    JournalistLatestReview,
    JournalistDetail,
    JournalistStats,
    JournalistOutletBreakdown,
    ReviewWithDisparity,
    PaginatedResponse,
    DisparitySnapshot as DisparitySnapshotSchema,
)
from app.cache import get_cached, set_cached, cache_key, CACHE_TTL_MEDIUM

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Anti-gaming constants
LAUNCH_WINDOW_DAYS = 60  # Reviews within 60 days of game release count for launch window disparity
# Leaderboard-style minimums for disparity sorting in the journalists list
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


@router.get("", response_model=PaginatedResponse[JournalistSummary])
async def list_journalists(
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    sort_by: str = Query("latest_review", regex="^(disparity|name|review_count|latest_review)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all journalists with pagination, sorting, and search (uses denormalized columns)."""
    key_hash = cache_key(
        "journalists:list:v3",
        page=page,
        per_page=per_page,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    cached = await get_cached(f"journalists:list:{key_hash}")
    if cached:
        return PaginatedResponse[JournalistSummary](**json.loads(cached))

    now = datetime.now(timezone.utc)

    # For disparity sorting, enforce leaderboard anti-gaming thresholds.
    # For non-disparity sorts, include all journalists with at least one scored review.
    filters = [
        Journalist.review_count_scored.isnot(None),
        Journalist.review_count_scored > 0,
    ]
    if sort_by == "disparity":
        filters.extend([
            Journalist.review_count_scored >= MIN_REVIEWS_FOR_DISPARITY_SORT,
            func.coalesce(Journalist.score_std_dev, 0) >= MIN_SCORE_STD_DEV_FOR_DISPARITY_SORT,
        ])

    journalists: list[Journalist] = []
    total = 0

    if sort_by == "disparity":
        # Use denormalized disparity for both ordering and display so filter order
        # always matches the badge values shown in the list.
        query = (
            select(
                Journalist,
                func.count().over().label("total_count"),
            )
            .where(
                *filters,
                Journalist.avg_disparity.isnot(None),
            )
        )
        if search:
            query = query.where(Journalist.name.ilike(f"%{search}%"))

        abs_disparity_col = func.abs(Journalist.avg_disparity)
        if sort_order == "desc":
            query = query.order_by(
                desc(abs_disparity_col).nulls_last(),
                desc(Journalist.review_count_scored).nulls_last(),
                asc(Journalist.id),
            )
        else:
            query = query.order_by(
                asc(abs_disparity_col).nulls_last(),
                desc(Journalist.review_count_scored).nulls_last(),
                asc(Journalist.id),
            )

        query = query.offset((page - 1) * per_page).limit(per_page)
        rows = (await db.execute(query)).all()
        journalists = [row[0] for row in rows]
        total = rows[0].total_count if rows else 0

        if not rows and page > 1:
            count_query = (
                select(func.count())
                .select_from(Journalist)
                .where(
                    *filters,
                    Journalist.avg_disparity.isnot(None),
                )
            )
            if search:
                count_query = count_query.where(Journalist.name.ilike(f"%{search}%"))
            total = (await db.execute(count_query)).scalar() or 0
    else:
        query = select(
            Journalist,
            func.count().over().label("total_count"),
        ).where(*filters)
        if sort_by == "latest_review":
            query = query.where(
                Journalist.last_review_at.isnot(None),
                Journalist.last_review_at <= now,
            )

        if search:
            query = query.where(Journalist.name.ilike(f"%{search}%"))

        if sort_by == "name":
            order_col = Journalist.name
        elif sort_by == "latest_review":
            order_col = Journalist.last_review_at
        else:  # review_count
            order_col = Journalist.review_count_scored

        if sort_order == "desc":
            query = query.order_by(desc(order_col).nulls_last())
        else:
            query = query.order_by(asc(order_col).nulls_last())

        query = query.offset((page - 1) * per_page).limit(per_page)
        rows = (await db.execute(query)).all()
        journalists = [row[0] for row in rows]
        total = rows[0].total_count if rows else 0

        if not rows and page > 1:
            count_query = select(func.count()).select_from(Journalist).where(*filters)
            if sort_by == "latest_review":
                count_query = count_query.where(
                    Journalist.last_review_at.isnot(None),
                    Journalist.last_review_at <= now,
                )
            if search:
                count_query = count_query.where(Journalist.name.ilike(f"%{search}%"))
            total = (await db.execute(count_query)).scalar() or 0

    # Load one latest scored review per journalist for the current page.
    latest_review_lookup: dict[int, JournalistLatestReview] = {}
    journalist_ids = [journalist.id for journalist in journalists]

    if journalist_ids:
        ranked_reviews = (
            select(
                Review.id.label("review_id"),
                Review.journalist_id.label("journalist_id"),
                Review.game_id.label("game_id"),
                Review.outlet_id.label("outlet_id"),
                Review.snippet.label("snippet"),
                Review.score_normalized.label("score_normalized"),
                Review.published_at.label("published_at"),
                func.row_number().over(
                    partition_by=Review.journalist_id,
                    order_by=(Review.published_at.desc(), Review.id.desc()),
                ).label("rn"),
            )
            .where(
                Review.journalist_id.in_(journalist_ids),
                Review.score_normalized.isnot(None),
                Review.score_normalized > 0,
                Review.published_at.isnot(None),
                Review.published_at <= now,
            )
            .subquery()
        )

        latest_reviews_query = (
            select(
                ranked_reviews.c.journalist_id,
                ranked_reviews.c.review_id,
                ranked_reviews.c.game_id,
                ranked_reviews.c.snippet,
                ranked_reviews.c.score_normalized,
                ranked_reviews.c.published_at,
                Game.title.label("game_title"),
                Game.release_date.label("game_release_date"),
                Outlet.name.label("outlet_name"),
            )
            .join(Game, ranked_reviews.c.game_id == Game.id)
            .outerjoin(Outlet, ranked_reviews.c.outlet_id == Outlet.id)
            .where(ranked_reviews.c.rn == 1)
        )
        latest_reviews_result = await db.execute(latest_reviews_query)

        for row in latest_reviews_result:
            review_date = row.published_at.date() if row.published_at and hasattr(row.published_at, 'date') else row.published_at
            latest_review_lookup[row.journalist_id] = JournalistLatestReview(
                review_id=row.review_id,
                game_id=row.game_id,
                game_title=row.game_title,
                game_release_date=row.game_release_date,
                outlet_name=row.outlet_name,
                snippet=row.snippet,
                score_normalized=row.score_normalized,
                published_at=row.published_at,
                review_timing=calculate_review_timing(review_date, row.game_release_date),
            )

    items = []
    for journalist in journalists:
        items.append(
            JournalistSummary(
                id=journalist.id,
                name=journalist.name,
                image_url=journalist.image_url,
                bio=journalist.bio,
                opencritic_id=journalist.opencritic_id,
                review_count=journalist.review_count_scored or 0,
                avg_disparity=journalist.avg_disparity,
                latest_review=latest_review_lookup.get(journalist.id),
            )
        )

    response = PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )

    await set_cached(
        f"journalists:list:{key_hash}",
        json.dumps(response.model_dump(mode="json")),
        CACHE_TTL_MEDIUM,
    )
    return response


@router.get("/{journalist_id}", response_model=JournalistDetail)
async def get_journalist(
    journalist_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get journalist detail with stats and outlet breakdown."""
    cached = await get_cached(f"journalists:detail:v1:{journalist_id}")
    if cached:
        return JournalistDetail(**json.loads(cached))

    # Get journalist
    result = await db.execute(
        select(Journalist).where(Journalist.id == journalist_id)
    )
    journalist = result.scalar_one_or_none()

    if not journalist:
        raise HTTPException(status_code=404, detail="Journalist not found")

    # Get review stats and timing counts in a single aggregate query.
    stats_query = select(
        func.count(Review.id).label("total_reviews"),
        func.avg(Review.score_normalized).label("avg_score_given"),
        func.min(Review.score_normalized).label("min_score_given"),
        func.max(Review.score_normalized).label("max_score_given"),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            Review.published_at.isnot(None),
                            Game.release_date.isnot(None),
                            Review.published_at < Game.release_date,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("early_review_count"),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            Review.published_at.isnot(None),
                            Game.release_date.isnot(None),
                            Review.published_at >= Game.release_date,
                            Review.published_at <= Game.release_date + timedelta(days=LAUNCH_WINDOW_DAYS),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("launch_window_review_count"),
        func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            Review.published_at.isnot(None),
                            Game.release_date.isnot(None),
                            Review.published_at > Game.release_date + timedelta(days=LAUNCH_WINDOW_DAYS),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("late_review_count"),
    ).select_from(Review).join(Game, Review.game_id == Game.id).where(
        Review.journalist_id == journalist_id,
        Review.score_normalized.isnot(None),  # Only scored reviews
        Review.score_normalized > 0,  # Exclude 0 (indicates unscored/text-only review)
    )

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()
    early_review_count = int(stats_row.early_review_count or 0)
    launch_window_review_count = int(stats_row.launch_window_review_count or 0)
    late_review_count = int(stats_row.late_review_count or 0)

    # Canonical disparity values for display come from the disparity pipeline (snapshots/
    # denormalized columns), not route-time recalculation. This avoids formula drift and
    # keeps journalist detail aligned with leaderboards/lists.
    latest_snapshot = (
        await db.execute(
            select(DisparitySnapshot)
            .where(DisparitySnapshot.journalist_id == journalist_id)
            .order_by(desc(DisparitySnapshot.snapshot_date), desc(DisparitySnapshot.id))
            .limit(1)
        )
    ).scalar_one_or_none()

    pipeline_disparity_steam = (
        latest_snapshot.avg_disparity_steam
        if latest_snapshot and latest_snapshot.avg_disparity_steam is not None
        else None
    )
    pipeline_disparity_metacritic = (
        latest_snapshot.avg_disparity_metacritic
        if latest_snapshot and latest_snapshot.avg_disparity_metacritic is not None
        else None
    )
    pipeline_disparity_combined = (
        journalist.avg_disparity
        if journalist.avg_disparity is not None
        else (
            latest_snapshot.avg_disparity_combined
            if latest_snapshot and latest_snapshot.avg_disparity_combined is not None
            else None
        )
    )
    # Get outlet breakdown metadata and attach pipeline-cached journalist+outlet disparity.
    outlet_breakdown_query = (
        select(
            Outlet.id.label("outlet_id"),
            Outlet.name.label("outlet_name"),
            func.count(Review.id).label("review_count"),
            func.min(Review.published_at).label("date_range_start"),
            func.max(Review.published_at).label("date_range_end"),
        )
        .join(Review, Review.outlet_id == Outlet.id)
        .where(
            Review.journalist_id == journalist_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .group_by(Outlet.id, Outlet.name)
        .order_by(desc(func.count(Review.id)))
    )
    outlet_result = await db.execute(outlet_breakdown_query)
    outlet_rows = outlet_result.all()
    latest_outlet_snapshots = (
        select(
            JournalistOutletDisparitySnapshot.outlet_id.label("outlet_id"),
            JournalistOutletDisparitySnapshot.avg_disparity_combined.label("avg_disparity_combined"),
            func.row_number().over(
                partition_by=JournalistOutletDisparitySnapshot.outlet_id,
                order_by=(
                    JournalistOutletDisparitySnapshot.snapshot_date.desc(),
                    JournalistOutletDisparitySnapshot.id.desc(),
                ),
            ).label("rn"),
        )
        .where(JournalistOutletDisparitySnapshot.journalist_id == journalist_id)
        .subquery()
    )
    outlet_snapshot_rows = (
        await db.execute(
            select(
                latest_outlet_snapshots.c.outlet_id,
                latest_outlet_snapshots.c.avg_disparity_combined,
            ).where(latest_outlet_snapshots.c.rn == 1)
        )
    ).all()
    outlet_disparity_lookup: dict[int, Optional[Decimal]] = {}
    for snapshot in outlet_snapshot_rows:
        outlet_disparity_lookup[snapshot.outlet_id] = snapshot.avg_disparity_combined

    outlet_breakdown = [
        JournalistOutletBreakdown(
            outlet_id=row.outlet_id,
            outlet_name=row.outlet_name,
            review_count=row.review_count,
            avg_disparity=outlet_disparity_lookup.get(row.outlet_id),
            date_range_start=row.date_range_start.date() if row.date_range_start else None,
            date_range_end=row.date_range_end.date() if row.date_range_end else None,
        )
        for row in outlet_rows
    ]

    pipeline_std_deviation = (
        latest_snapshot.std_deviation
        if latest_snapshot and latest_snapshot.std_deviation is not None
        else None
    )

    # Use denormalized score std dev computed by the disparity pipeline/snapshot refresh.
    score_std_deviation = journalist.score_std_dev

    stats = JournalistStats(
        total_reviews=stats_row.total_reviews or 0,
        avg_score_given=Decimal(str(round(stats_row.avg_score_given, 2))) if stats_row.avg_score_given else None,
        # Use canonical pipeline disparity values for consistency across all entity types.
        avg_disparity_steam=pipeline_disparity_steam,
        avg_disparity_metacritic=pipeline_disparity_metacritic,
        avg_disparity_combined=pipeline_disparity_combined,
        overall_disparity_steam=pipeline_disparity_steam,
        overall_disparity_metacritic=pipeline_disparity_metacritic,
        overall_disparity_combined=pipeline_disparity_combined,
        std_deviation=pipeline_std_deviation,
        alignment_rating=None,  # Calculate based on disparity threshold
        # Transparency metrics - timing
        early_review_count=early_review_count,
        launch_window_review_count=launch_window_review_count,
        late_review_count=late_review_count,
        # Transparency metrics - scoring patterns
        min_score_given=Decimal(str(round(stats_row.min_score_given, 2))) if stats_row.min_score_given else None,
        max_score_given=Decimal(str(round(stats_row.max_score_given, 2))) if stats_row.max_score_given else None,
        score_std_deviation=score_std_deviation,
    )

    response = JournalistDetail(
        id=journalist.id,
        name=journalist.name,
        image_url=journalist.image_url,
        bio=journalist.bio,
        opencritic_id=journalist.opencritic_id,
        review_count=stats_row.total_reviews or 0,
        avg_disparity=journalist.avg_disparity if journalist.avg_disparity is not None else pipeline_disparity_combined,
        stats=stats,
        outlet_breakdown=outlet_breakdown,
        created_at=journalist.created_at,
        updated_at=journalist.updated_at,
    )

    await set_cached(
        f"journalists:detail:v1:{journalist_id}",
        json.dumps(response.model_dump(mode="json")),
        CACHE_TTL_MEDIUM,
    )
    return response


@router.get("/{journalist_id}/reviews", response_model=PaginatedResponse[ReviewWithDisparity])
@limiter.limit("60/minute")
async def get_journalist_reviews(
    request: Request,
    journalist_id: int,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated reviews for a journalist, newest first."""
    # Verify journalist exists
    journalist_result = await db.execute(
        select(Journalist.id).where(Journalist.id == journalist_id)
    )
    if not journalist_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Journalist not found")

    # Get total count (only reviews with actual scores, exclude 0 = unscored)
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(
            Review.journalist_id == journalist_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get reviews with game and outlet info (only reviews with actual scores)
    query = (
        select(Review, Game, Outlet)
        .join(Game, Review.game_id == Game.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(
            Review.journalist_id == journalist_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
        )
        .order_by(desc(Review.published_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    for review, game, outlet in rows:
        steam_user_score = review.cached_steam_user_score
        metacritic_user_score = review.cached_metacritic_user_score
        disparity_steam = review.cached_disparity_steam
        disparity_metacritic = review.cached_disparity_metacritic

        # Calculate review timing (early/launch_window/late)
        review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
        review_timing = calculate_review_timing(review_date, game.release_date)

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
                game_release_date=game.release_date,
                outlet_name=outlet.name if outlet else None,
                steam_user_score=steam_user_score,
                metacritic_user_score=metacritic_user_score,
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


@router.get("/{journalist_id}/history", response_model=list[DisparitySnapshotSchema])
async def get_journalist_history(
    journalist_id: int,
    limit: int = Query(10000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get historical disparity data for charts from pipeline snapshots."""
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
        for s in reversed(snapshots)
    ]

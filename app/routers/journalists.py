"""Journalists API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc
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
    latest_review_subquery = None
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
                desc(Journalist.avg_disparity).nulls_last(),
                asc(Journalist.id),
            )
        else:
            query = query.order_by(
                asc(abs_disparity_col).nulls_last(),
                asc(Journalist.avg_disparity).nulls_last(),
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
        if sort_by == "latest_review":
            # Use same recency criteria as home /stats/recent-reviews endpoint.
            latest_review_subquery = (
                select(
                    Review.journalist_id.label("journalist_id"),
                    func.max(Review.published_at).label("latest_review_at"),
                )
                .where(
                    Review.score_normalized.isnot(None),
                    Review.score_normalized > 0,
                    Review.published_at.isnot(None),
                    Review.published_at <= now,
                )
                .group_by(Review.journalist_id)
                .subquery()
            )
            query = (
                select(
                    Journalist,
                    func.count().over().label("total_count"),
                )
                .join(latest_review_subquery, latest_review_subquery.c.journalist_id == Journalist.id)
                .where(*filters)
            )
        else:
            query = select(
                Journalist,
                func.count().over().label("total_count"),
            ).where(*filters)

        if search:
            query = query.where(Journalist.name.ilike(f"%{search}%"))

        if sort_by == "name":
            order_col = Journalist.name
        elif sort_by == "latest_review":
            order_col = latest_review_subquery.c.latest_review_at
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
            if sort_by == "latest_review":
                count_query = (
                    select(func.count())
                    .select_from(Journalist)
                    .join(latest_review_subquery, latest_review_subquery.c.journalist_id == Journalist.id)
                    .where(*filters)
                )
            else:
                count_query = select(func.count()).select_from(Journalist).where(*filters)
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

    # Get review stats (only properly scored reviews - exclude 0 which means "no score")
    stats_query = select(
        func.count(Review.id).label("total_reviews"),
        func.avg(Review.score_normalized).label("avg_score_given"),
        func.min(Review.score_normalized).label("min_score_given"),
        func.max(Review.score_normalized).label("max_score_given"),
    ).where(
        Review.journalist_id == journalist_id,
        Review.score_normalized.isnot(None),  # Only scored reviews
        Review.score_normalized > 0,  # Exclude 0 (indicates unscored/text-only review)
    )

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.one()

    # Get all scored reviews with their games to calculate disparity dynamically
    # Exclude score_normalized = 0 which indicates an unscored/text-only review
    reviews_query = (
        select(Review, Game)
        .join(Game, Review.game_id == Game.id)
        .where(
            Review.journalist_id == journalist_id,
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,  # Exclude unscored reviews
        )
    )
    reviews_result = await db.execute(reviews_query)
    review_rows = reviews_result.all()

    # Calculate review timing transparency metrics only (no live disparity math).
    early_review_count = 0
    launch_window_review_count = 0
    late_review_count = 0

    for review, game in review_rows:
        review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
        timing = calculate_review_timing(review_date, game.release_date)

        if timing == "early":
            early_review_count += 1
        elif timing == "launch_window":
            launch_window_review_count += 1
        elif timing == "late":
            late_review_count += 1

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
    outlet_snapshot_rows = (
        await db.execute(
            select(JournalistOutletDisparitySnapshot)
            .where(JournalistOutletDisparitySnapshot.journalist_id == journalist_id)
            .order_by(
                desc(JournalistOutletDisparitySnapshot.snapshot_date),
                desc(JournalistOutletDisparitySnapshot.id),
            )
        )
    ).scalars().all()
    outlet_disparity_lookup: dict[int, Optional[Decimal]] = {}
    for snapshot in outlet_snapshot_rows:
        if snapshot.outlet_id not in outlet_disparity_lookup:
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

    # Calculate score std deviation (variance in scores given)
    score_std_deviation = None
    if len(review_rows) > 1:
        from statistics import stdev
        scores = [float(review.score_normalized) for review, _ in review_rows]
        score_std_deviation = Decimal(str(round(stdev(scores), 2)))

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

    return JournalistDetail(
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

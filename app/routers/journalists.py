"""Journalists API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from decimal import Decimal
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.models import Journalist, Review, Outlet, Game, UserScore
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
# Minimum user reviews required for a game to count in disparity (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20
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


def _average(values: list[float]) -> Optional[Decimal]:
    """Return Decimal average rounded to 2 decimals."""
    if not values:
        return None
    return Decimal(str(round(sum(values) / len(values), 2)))


def _combine_source_averages(
    steam_avg: Optional[Decimal],
    metacritic_avg: Optional[Decimal],
) -> Optional[Decimal]:
    """Average available source averages."""
    combined_values = [v for v in [steam_avg, metacritic_avg] if v is not None]
    if not combined_values:
        return None
    return Decimal(
        str(round(sum(float(v) for v in combined_values) / len(combined_values), 2))
    )


async def _calculate_display_disparities_for_journalists(
    db: AsyncSession,
    journalist_ids: list[int],
) -> dict[int, Optional[Decimal]]:
    """
    Calculate the list-page disparity metric using the same rules as journalist detail.

    Primary metric: launch-window combined disparity.
    Fallback metric: overall combined disparity when no launch-window data exists.
    """
    if not journalist_ids:
        return {}

    review_rows_result = await db.execute(
        select(
            Review.journalist_id,
            Review.game_id,
            Review.score_normalized,
            Review.published_at,
            Game.release_date,
        )
        .join(Game, Review.game_id == Game.id)
        .where(
            Review.journalist_id.in_(journalist_ids),
            Review.score_normalized.isnot(None),
            Review.score_normalized > 0,
        )
    )
    review_rows = review_rows_result.all()
    if not review_rows:
        return {}

    game_ids = list({row.game_id for row in review_rows})
    user_score_lookup: dict[tuple[int, str], dict[str, Optional[Decimal]]] = {}
    if game_ids:
        user_scores_result = await db.execute(
            select(UserScore)
            .where(UserScore.game_id.in_(game_ids))
            .order_by(desc(UserScore.scraped_at))
        )
        for us in user_scores_result.scalars().all():
            key = (us.game_id, us.source.value)
            if key not in user_score_lookup:
                user_score_lookup[key] = {
                    "score": us.score,
                    "sample_size": us.sample_size,
                }

    launch_steam: dict[int, list[float]] = defaultdict(list)
    launch_mc: dict[int, list[float]] = defaultdict(list)
    overall_steam: dict[int, list[float]] = defaultdict(list)
    overall_mc: dict[int, list[float]] = defaultdict(list)

    for row in review_rows:
        journalist_id = row.journalist_id
        steam_data = user_score_lookup.get((row.game_id, "steam"))
        metacritic_data = user_score_lookup.get((row.game_id, "metacritic"))

        review_date = row.published_at.date() if row.published_at and hasattr(row.published_at, "date") else row.published_at
        timing = calculate_review_timing(review_date, row.release_date)
        is_launch_window = timing == "launch_window"

        if steam_data and steam_data["sample_size"] and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS:
            disparity = float(row.score_normalized - steam_data["score"])
            overall_steam[journalist_id].append(disparity)
            if is_launch_window:
                launch_steam[journalist_id].append(disparity)

        if metacritic_data and metacritic_data["score"] and (
            metacritic_data["sample_size"] is None
            or metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS
        ):
            disparity = float(row.score_normalized - metacritic_data["score"])
            overall_mc[journalist_id].append(disparity)
            if is_launch_window:
                launch_mc[journalist_id].append(disparity)

    disparities: dict[int, Optional[Decimal]] = {}
    for journalist_id in journalist_ids:
        launch_steam_avg = _average(launch_steam.get(journalist_id, []))
        launch_mc_avg = _average(launch_mc.get(journalist_id, []))
        launch_combined = _combine_source_averages(launch_steam_avg, launch_mc_avg)

        overall_steam_avg = _average(overall_steam.get(journalist_id, []))
        overall_mc_avg = _average(overall_mc.get(journalist_id, []))
        overall_combined = _combine_source_averages(overall_steam_avg, overall_mc_avg)

        disparities[journalist_id] = launch_combined if launch_combined is not None else overall_combined

    return disparities


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
            Journalist.avg_disparity.isnot(None),
            Journalist.review_count_scored >= MIN_REVIEWS_FOR_DISPARITY_SORT,
            func.coalesce(Journalist.score_std_dev, 0) >= MIN_SCORE_STD_DEV_FOR_DISPARITY_SORT,
        ])
    latest_review_subquery = None
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
            select(Journalist)
            .join(latest_review_subquery, latest_review_subquery.c.journalist_id == Journalist.id)
            .where(*filters)
        )
    else:
        query = select(Journalist).where(*filters)

    # Filter by search term if provided
    if search:
        query = query.where(Journalist.name.ilike(f"%{search}%"))

    # Apply sorting using denormalized columns
    if sort_by == "disparity":
        order_col = Journalist.avg_disparity
    elif sort_by == "name":
        order_col = Journalist.name
    elif sort_by == "latest_review":
        order_col = latest_review_subquery.c.latest_review_at
    else:  # review_count
        order_col = Journalist.review_count_scored

    if sort_order == "desc":
        query = query.order_by(desc(order_col).nulls_last())
    else:
        query = query.order_by(asc(order_col).nulls_last())

    # Get total count
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
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    journalists = result.scalars().all()

    # Load one latest scored review per journalist for the current page.
    latest_review_lookup: dict[int, JournalistLatestReview] = {}
    journalist_ids = [journalist.id for journalist in journalists]
    display_disparity_lookup: dict[int, Optional[Decimal]] = {}
    if journalist_ids:
        display_disparity_lookup = await _calculate_display_disparities_for_journalists(
            db,
            journalist_ids,
        )

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
                avg_disparity=display_disparity_lookup.get(journalist.id, journalist.avg_disparity),
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

    # Get user scores for all games (including sample_size for filtering)
    game_ids = list(set(row[1].id for row in review_rows)) if review_rows else []
    user_score_lookup: dict = {}  # (game_id, source) -> {score, sample_size}
    if game_ids:
        user_scores_query = (
            select(UserScore)
            .where(UserScore.game_id.in_(game_ids))
            .order_by(desc(UserScore.scraped_at))
        )
        user_scores_result = await db.execute(user_scores_query)
        user_scores = user_scores_result.scalars().all()
        for us in user_scores:
            key = (us.game_id, us.source.value)
            if key not in user_score_lookup:
                user_score_lookup[key] = {
                    "score": us.score,
                    "sample_size": us.sample_size,
                }

    # Calculate disparity with launch window and user review minimum filters
    # Launch window: reviews within 60 days of game release
    # User review minimum: games must have 50+ user reviews

    launch_window_steam_disparities = []
    launch_window_metacritic_disparities = []
    overall_steam_disparities = []
    overall_metacritic_disparities = []

    early_review_count = 0
    launch_window_review_count = 0
    late_review_count = 0

    for review, game in review_rows:
        steam_data = user_score_lookup.get((game.id, "steam"))
        metacritic_data = user_score_lookup.get((game.id, "metacritic"))

        # Calculate review timing
        review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
        timing = calculate_review_timing(review_date, game.release_date)

        if timing == "early":
            early_review_count += 1
        elif timing == "launch_window":
            launch_window_review_count += 1
        elif timing == "late":
            late_review_count += 1

        is_launch_window = timing == "launch_window"

        # Calculate Steam disparity (only if meets minimum threshold)
        if steam_data and steam_data["sample_size"] and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS:
            disparity = float(review.score_normalized - steam_data["score"])
            overall_steam_disparities.append(disparity)
            if is_launch_window:
                launch_window_steam_disparities.append(disparity)

        # Calculate Metacritic disparity (only if meets minimum threshold or sample_size unknown)
        if metacritic_data and metacritic_data["score"] and (
            metacritic_data["sample_size"] is None or metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS
        ):
            disparity = float(review.score_normalized - metacritic_data["score"])
            overall_metacritic_disparities.append(disparity)
            if is_launch_window:
                launch_window_metacritic_disparities.append(disparity)

    # Calculate launch window averages (primary metric)
    avg_disparity_steam = Decimal(str(round(sum(launch_window_steam_disparities) / len(launch_window_steam_disparities), 2))) if launch_window_steam_disparities else None
    avg_disparity_metacritic = Decimal(str(round(sum(launch_window_metacritic_disparities) / len(launch_window_metacritic_disparities), 2))) if launch_window_metacritic_disparities else None

    combined_values = [v for v in [avg_disparity_steam, avg_disparity_metacritic] if v is not None]
    avg_disparity_combined = Decimal(str(round(sum(float(v) for v in combined_values) / len(combined_values), 2))) if combined_values else None

    # Calculate overall averages (secondary metric, includes late reviews)
    overall_disparity_steam = Decimal(str(round(sum(overall_steam_disparities) / len(overall_steam_disparities), 2))) if overall_steam_disparities else None
    overall_disparity_metacritic = Decimal(str(round(sum(overall_metacritic_disparities) / len(overall_metacritic_disparities), 2))) if overall_metacritic_disparities else None

    overall_combined_values = [v for v in [overall_disparity_steam, overall_disparity_metacritic] if v is not None]
    overall_disparity_combined = Decimal(str(round(sum(float(v) for v in overall_combined_values) / len(overall_combined_values), 2))) if overall_combined_values else None

    # Get outlet breakdown with per-outlet disparity (using launch window only)
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

    # Calculate per-outlet disparity (using launch window reviews and 50+ user review filter)
    # Uses same approach as outlet detail page: separate Steam/Metacritic lists, then combine averages
    outlet_breakdown = []
    for row in outlet_rows:
        outlet_steam_disparities = []
        outlet_metacritic_disparities = []
        for review, game in review_rows:
            if review.outlet_id == row.outlet_id:
                # Check launch window
                review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
                timing = calculate_review_timing(review_date, game.release_date)

                if timing != "launch_window":
                    continue

                steam_data = user_score_lookup.get((game.id, "steam"))
                metacritic_data = user_score_lookup.get((game.id, "metacritic"))

                if steam_data and steam_data["sample_size"] and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS:
                    outlet_steam_disparities.append(float(review.score_normalized - steam_data["score"]))

                if metacritic_data and metacritic_data["score"] and (
                    metacritic_data["sample_size"] is None or metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS
                ):
                    outlet_metacritic_disparities.append(float(review.score_normalized - metacritic_data["score"]))

        outlet_avg_steam = Decimal(str(round(sum(outlet_steam_disparities) / len(outlet_steam_disparities), 2))) if outlet_steam_disparities else None
        outlet_avg_metacritic = Decimal(str(round(sum(outlet_metacritic_disparities) / len(outlet_metacritic_disparities), 2))) if outlet_metacritic_disparities else None
        outlet_combined = [v for v in [outlet_avg_steam, outlet_avg_metacritic] if v is not None]
        outlet_avg_disparity = Decimal(str(round(sum(float(v) for v in outlet_combined) / len(outlet_combined), 2))) if outlet_combined else None

        outlet_breakdown.append(
            JournalistOutletBreakdown(
                outlet_id=row.outlet_id,
                outlet_name=row.outlet_name,
                review_count=row.review_count,
                avg_disparity=outlet_avg_disparity,
                date_range_start=row.date_range_start.date() if row.date_range_start else None,
                date_range_end=row.date_range_end.date() if row.date_range_end else None,
            )
        )

    # Calculate std deviation (from launch window disparities)
    all_launch_disparities = launch_window_steam_disparities + launch_window_metacritic_disparities
    std_deviation = None
    if len(all_launch_disparities) > 1:
        from statistics import stdev
        std_deviation = Decimal(str(round(stdev(all_launch_disparities), 2)))

    # Calculate score std deviation (variance in scores given)
    score_std_deviation = None
    if len(review_rows) > 1:
        from statistics import stdev
        scores = [float(review.score_normalized) for review, _ in review_rows]
        score_std_deviation = Decimal(str(round(stdev(scores), 2)))

    stats = JournalistStats(
        total_reviews=stats_row.total_reviews or 0,
        avg_score_given=Decimal(str(round(stats_row.avg_score_given, 2))) if stats_row.avg_score_given else None,
        # Launch window disparity (primary - for rankings/leaderboards)
        avg_disparity_steam=avg_disparity_steam,
        avg_disparity_metacritic=avg_disparity_metacritic,
        avg_disparity_combined=avg_disparity_combined,
        # Overall disparity (secondary - includes late reviews)
        overall_disparity_steam=overall_disparity_steam,
        overall_disparity_metacritic=overall_disparity_metacritic,
        overall_disparity_combined=overall_disparity_combined,
        std_deviation=std_deviation,
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
        avg_disparity=avg_disparity_combined,  # Use launch window for headline metric
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
        steam_score_obj = user_score_lookup.get((game.id, "steam"))
        metacritic_score_obj = user_score_lookup.get((game.id, "metacritic"))

        # Only use scores if they meet the minimum sample size requirement (per source)
        # Steam always provides sample_size, so we require it
        steam_user_score = steam_score_obj.score if steam_score_obj and (steam_score_obj.sample_size or 0) >= MIN_STEAM_USER_REVIEWS else None
        # Metacritic doesn't always expose sample_size - if score exists, allow it through
        # (Metacritic only displays user scores when there are enough ratings)
        metacritic_user_score = metacritic_score_obj.score if metacritic_score_obj and metacritic_score_obj.score and (
            metacritic_score_obj.sample_size is None or metacritic_score_obj.sample_size >= MIN_METACRITIC_USER_REVIEWS
        ) else None

        disparity_steam = None
        disparity_metacritic = None

        if steam_user_score:
            disparity_steam = review.score_normalized - steam_user_score
        if metacritic_user_score:
            disparity_metacritic = review.score_normalized - metacritic_user_score

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
    """
    Get historical disparity data for charts.

    Returns cumulative disparity calculated at each review date,
    showing how the journalist's disparity evolved over time.

    Only includes launch window reviews (within 60 days of game release)
    and games with 50+ user reviews.
    
    Returns full career timeline (no practical limit).
    """
    # Verify journalist exists
    journalist_result = await db.execute(
        select(Journalist.id).where(Journalist.id == journalist_id)
    )
    if not journalist_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Journalist not found")

    # Get all reviews with actual scores, ordered by date
    query = (
        select(Review, Game)
        .join(Game, Review.game_id == Game.id)
        .where(
            Review.journalist_id == journalist_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
            Review.published_at.isnot(None),  # Only reviews with dates
        )
        .order_by(Review.published_at)
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return []

    # Get user scores for all games (including sample_size for filtering)
    game_ids = list(set(row[1].id for row in rows))
    user_scores_query = (
        select(UserScore)
        .where(UserScore.game_id.in_(game_ids))
        .order_by(desc(UserScore.scraped_at))
    )
    user_scores_result = await db.execute(user_scores_query)
    user_scores = user_scores_result.scalars().all()

    # Build lookup for latest user scores with sample size
    user_score_lookup: dict = {}
    for us in user_scores:
        key = (us.game_id, us.source.value)
        if key not in user_score_lookup:
            user_score_lookup[key] = {
                "score": us.score,
                "sample_size": us.sample_size,
            }

    # Calculate cumulative disparity at each review date
    # Only include launch window reviews with 50+ user reviews
    steam_sum = Decimal("0")
    steam_count = 0
    metacritic_sum = Decimal("0")
    metacritic_count = 0

    history = []
    last_date = None

    for review, game in rows:
        review_date = review.published_at.date() if review.published_at else None
        if not review_date:
            continue

        # Calculate review timing
        timing = calculate_review_timing(review_date, game.release_date)

        # Skip non-launch-window reviews for history chart (early and late reviews excluded)
        if timing != "launch_window":
            continue

        steam_data = user_score_lookup.get((game.id, "steam"))
        metacritic_data = user_score_lookup.get((game.id, "metacritic"))

        # Calculate this review's disparity (only if meets minimum threshold)
        if steam_data and steam_data["sample_size"] and steam_data["sample_size"] >= MIN_STEAM_USER_REVIEWS:
            steam_sum += review.score_normalized - steam_data["score"]
            steam_count += 1
        if metacritic_data and metacritic_data["score"] and (
            metacritic_data["sample_size"] is None or metacritic_data["sample_size"] >= MIN_METACRITIC_USER_REVIEWS
        ):
            metacritic_sum += review.score_normalized - metacritic_data["score"]
            metacritic_count += 1

        # Only add a data point if we have valid disparities and date changed
        if steam_count == 0 and metacritic_count == 0:
            continue

        if review_date != last_date:
            avg_steam = Decimal(str(round(float(steam_sum) / steam_count, 2))) if steam_count > 0 else None
            avg_metacritic = Decimal(str(round(float(metacritic_sum) / metacritic_count, 2))) if metacritic_count > 0 else None

            combined_count = 0
            combined_sum = Decimal("0")
            if avg_steam is not None:
                combined_sum += avg_steam
                combined_count += 1
            if avg_metacritic is not None:
                combined_sum += avg_metacritic
                combined_count += 1
            avg_combined = Decimal(str(round(float(combined_sum) / combined_count, 2))) if combined_count > 0 else None

            history.append(
                DisparitySnapshotSchema(
                    date=review_date,
                    avg_disparity_steam=avg_steam,
                    avg_disparity_metacritic=avg_metacritic,
                    avg_disparity_combined=avg_combined,
                    review_count=steam_count + metacritic_count,
                )
            )
            last_date = review_date
        else:
            # Update the last entry if same date (multiple reviews on same day)
            if history:
                avg_steam = Decimal(str(round(float(steam_sum) / steam_count, 2))) if steam_count > 0 else None
                avg_metacritic = Decimal(str(round(float(metacritic_sum) / metacritic_count, 2))) if metacritic_count > 0 else None

                combined_count = 0
                combined_sum = Decimal("0")
                if avg_steam is not None:
                    combined_sum += avg_steam
                    combined_count += 1
                if avg_metacritic is not None:
                    combined_sum += avg_metacritic
                    combined_count += 1
                avg_combined = Decimal(str(round(float(combined_sum) / combined_count, 2))) if combined_count > 0 else None

                history[-1] = DisparitySnapshotSchema(
                    date=review_date,
                    avg_disparity_steam=avg_steam,
                    avg_disparity_metacritic=avg_metacritic,
                    avg_disparity_combined=avg_combined,
                    review_count=steam_count + metacritic_count,
                )

    # Return last N entries if we have more than limit
    if len(history) > limit:
        history = history[-limit:]

    return history

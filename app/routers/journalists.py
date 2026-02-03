"""Journalists API endpoints."""

from datetime import timedelta
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

# Anti-gaming constants
LAUNCH_WINDOW_DAYS = 60  # Reviews within 60 days of game release count for launch window disparity
MIN_USER_REVIEWS = 50    # Minimum user reviews required for a game to count in disparity


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
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    sort_by: str = Query("disparity", regex="^(disparity|name|review_count)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all journalists with pagination, sorting, and search."""
    # Build base query with review count - only count reviews WITH actual scores
    subq = (
        select(
            Review.journalist_id,
            func.count(Review.id).label("review_count"),
        )
        .where(
            Review.score_normalized.isnot(None),  # Only reviews with scores
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
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
        .join(subq, Journalist.id == subq.c.journalist_id)  # INNER JOIN - only journalists with scored reviews
        .outerjoin(disparity_subq, Journalist.id == disparity_subq.c.journalist_id)
    )

    # Filter by search term if provided
    if search:
        query = query.where(Journalist.name.ilike(f"%{search}%"))

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

    # Get total count (only journalists with scored reviews)
    count_query = (
        select(func.count(Journalist.id.distinct()))
        .select_from(Journalist)
        .join(subq, Journalist.id == subq.c.journalist_id)
    )
    if search:
        count_query = count_query.where(Journalist.name.ilike(f"%{search}%"))
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
                    "sample_size": us.sample_size or 0,
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
        else:  # late or unknown
            late_review_count += 1

        is_launch_window = timing == "launch_window"

        # Calculate Steam disparity (only if 50+ user reviews)
        if steam_data and steam_data["sample_size"] >= MIN_USER_REVIEWS:
            disparity = float(review.score_normalized - steam_data["score"])
            overall_steam_disparities.append(disparity)
            if is_launch_window:
                launch_window_steam_disparities.append(disparity)

        # Calculate Metacritic disparity (only if 50+ user reviews)
        if metacritic_data and metacritic_data["sample_size"] >= MIN_USER_REVIEWS:
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
    outlet_breakdown = []
    for row in outlet_rows:
        outlet_disparities = []
        for review, game in review_rows:
            if review.outlet_id == row.outlet_id:
                # Check launch window
                review_date = review.published_at.date() if review.published_at and hasattr(review.published_at, 'date') else review.published_at
                timing = calculate_review_timing(review_date, game.release_date)
                is_launch_window = timing == "launch_window"

                if is_launch_window:
                    steam_data = user_score_lookup.get((game.id, "steam"))
                    metacritic_data = user_score_lookup.get((game.id, "metacritic"))

                    if steam_data and steam_data["sample_size"] >= MIN_USER_REVIEWS:
                        outlet_disparities.append(float(review.score_normalized - steam_data["score"]))
                    elif metacritic_data and metacritic_data["sample_size"] >= MIN_USER_REVIEWS:
                        outlet_disparities.append(float(review.score_normalized - metacritic_data["score"]))

        outlet_avg_disparity = Decimal(str(round(sum(outlet_disparities) / len(outlet_disparities), 2))) if outlet_disparities else None

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

        # Only use scores if they meet the minimum sample size requirement
        steam_user_score = steam_score_obj.score if steam_score_obj and (steam_score_obj.sample_size or 0) >= MIN_USER_REVIEWS else None
        metacritic_user_score = metacritic_score_obj.score if metacritic_score_obj and (metacritic_score_obj.sample_size or 0) >= MIN_USER_REVIEWS else None

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
                "sample_size": us.sample_size or 0,
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

        # Calculate this review's disparity (only if 50+ user reviews)
        if steam_data and steam_data["sample_size"] >= MIN_USER_REVIEWS:
            steam_sum += review.score_normalized - steam_data["score"]
            steam_count += 1
        if metacritic_data and metacritic_data["sample_size"] >= MIN_USER_REVIEWS:
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

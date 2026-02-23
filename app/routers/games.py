"""Games API endpoints."""

from typing import Optional
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc, extract, or_, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.models import Game, Review, Journalist, Outlet, NewsArticle
from app.schemas.schemas import (
    GameDetail,
    GameWithScores,
    ReviewWithJournalist,
    NewsArticleSummary,
    PaginatedResponse,
)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Anti-gaming: minimum user reviews required for a game to appear in lists (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20
MIN_CRITIC_REVIEWS_FOR_GAMES_LIST = 5


@router.get("", response_model=PaginatedResponse[GameWithScores])
async def list_games(
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    year: Optional[int] = Query(None, ge=2015),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    sort_by: str = Query("release_date", regex="^(release_date|title|disparity)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all games with pagination (uses denormalized columns - instant!)."""
    filters = [
        # Include games with either:
        # - at least one valid user-score signal, or
        # - at least N critic reviews (for new releases that have critic coverage first).
        or_(
            Game.steam_sample_size >= MIN_STEAM_USER_REVIEWS,
            and_(
                Game.metacritic_user_score.isnot(None),
                or_(
                    Game.metacritic_sample_size.is_(None),
                    Game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS,
                )
            ),
            Game.critic_review_count >= MIN_CRITIC_REVIEWS_FOR_GAMES_LIST,
        ),
    ]

    query = select(
        Game,
        func.count().over().label("total_count"),
    ).where(*filters)

    # Filter by year if provided
    if year:
        query = query.where(extract("year", Game.release_date) == year)

    # Filter by search term if provided
    if search:
        query = query.where(Game.title.ilike(f"%{search}%"))

    # Use the same validity rules as the API response fields/UI badge so sort order
    # matches what users actually see on the page.
    steam_disparity_display_expr = case(
        (
            and_(
                Game.steam_sample_size.isnot(None),
                Game.steam_sample_size >= MIN_STEAM_USER_REVIEWS,
            ),
            Game.disparity_steam,
        ),
        else_=None,
    )
    metacritic_disparity_display_expr = case(
        (
            and_(
                Game.metacritic_user_score.isnot(None),
                or_(
                    Game.metacritic_sample_size.is_(None),
                    Game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS,
                ),
            ),
            Game.disparity_metacritic,
        ),
        else_=None,
    )
    combined_disparity_expr = func.coalesce(
        (steam_disparity_display_expr + metacritic_disparity_display_expr) / 2,
        steam_disparity_display_expr,
        metacritic_disparity_display_expr,
    )

    # Apply sorting using denormalized columns
    if sort_by == "release_date":
        # Keep newly discovered games visible even when release_date is missing by
        # using created_at as a tiebreaker/fallback without non-immutable casts.
        if sort_order == "desc":
            query = query.order_by(
                desc(Game.release_date).nulls_last(),
                desc(Game.created_at).nulls_last(),
            )
        else:
            query = query.order_by(
                asc(Game.release_date).nulls_last(),
                asc(Game.created_at).nulls_last(),
            )
    else:
        if sort_by == "title":
            order_col = Game.title
        else:  # disparity
            order_col = func.abs(combined_disparity_expr)

        if sort_order == "desc":
            if sort_by == "disparity":
                query = query.order_by(
                    desc(order_col).nulls_last(),
                    desc(combined_disparity_expr).nulls_last(),
                    desc(Game.release_date).nulls_last(),
                    asc(Game.id),
                )
            else:
                query = query.order_by(desc(order_col).nulls_last())
        else:
            if sort_by == "disparity":
                query = query.order_by(
                    asc(order_col).nulls_last(),
                    asc(combined_disparity_expr).nulls_last(),
                    desc(Game.release_date).nulls_last(),
                    asc(Game.id),
                )
            else:
                query = query.order_by(asc(order_col).nulls_last())

    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()
    games = [row[0] for row in rows]
    total = rows[0].total_count if rows else 0

    if not rows and page > 1:
        count_query = select(func.count()).select_from(Game).where(*filters)
        if year:
            count_query = count_query.where(extract("year", Game.release_date) == year)
        if search:
            count_query = count_query.where(Game.title.ilike(f"%{search}%"))
        total = (await db.execute(count_query)).scalar() or 0

    items = []
    for game in games:
        # Check which scores are valid based on sample size
        steam_valid = game.steam_sample_size is not None and game.steam_sample_size >= MIN_STEAM_USER_REVIEWS
        metacritic_valid = (
            game.metacritic_user_score is not None
            and (game.metacritic_sample_size is None or game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS)
        )

        items.append(
            GameWithScores(
                id=game.id,
                title=game.title,
                release_date=game.release_date,
                description=game.description,
                image_url=game.image_url,
                opencritic_id=game.opencritic_id,
                steam_app_id=game.steam_app_id,
                critic_review_count=game.critic_review_count or 0,
                opencritic_score=game.top_critic_score,
                steam_user_score=game.steam_user_score if steam_valid else None,
                steam_sample_size=game.steam_sample_size if steam_valid else None,
                metacritic_user_score=game.metacritic_user_score if metacritic_valid else None,
                metacritic_sample_size=game.metacritic_sample_size if metacritic_valid else None,
                avg_critic_score=game.avg_critic_score,
                disparity_steam=game.disparity_steam if steam_valid else None,
                disparity_metacritic=game.disparity_metacritic if metacritic_valid else None,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


@router.get("/{game_id}", response_model=GameDetail)
async def get_game(
    game_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get game detail (uses denormalized columns - instant!)."""
    result = await db.execute(
        select(Game).where(Game.id == game_id)
    )
    game = result.scalar_one_or_none()

    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    steam_valid = game.steam_sample_size is not None and game.steam_sample_size >= MIN_STEAM_USER_REVIEWS
    metacritic_valid = (
        game.metacritic_user_score is not None
        and (game.metacritic_sample_size is None or game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS)
    )

    # Fetch the 5 most recent news articles for this game
    news_result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.game_id == game_id)
        .order_by(desc(NewsArticle.published_at).nulls_last())
        .limit(5)
    )
    recent_news = news_result.scalars().all()

    return GameDetail(
        id=game.id,
        title=game.title,
        release_date=game.release_date,
        description=game.description,
        image_url=game.image_url,
        opencritic_id=game.opencritic_id,
        steam_app_id=game.steam_app_id,
        critic_review_count=game.critic_review_count or 0,
        opencritic_score=game.top_critic_score,
        steam_user_score=game.steam_user_score if steam_valid else None,
        steam_sample_size=game.steam_sample_size if steam_valid else None,
        metacritic_user_score=game.metacritic_user_score if metacritic_valid else None,
        metacritic_sample_size=game.metacritic_sample_size if metacritic_valid else None,
        avg_critic_score=game.avg_critic_score,
        disparity_steam=game.disparity_steam if steam_valid else None,
        disparity_metacritic=game.disparity_metacritic if metacritic_valid else None,
        tier=game.tier,
        percent_recommended=game.percent_recommended,
        created_at=game.created_at,
        updated_at=game.updated_at,
        recent_news=[NewsArticleSummary.model_validate(a) for a in recent_news],
    )


@router.get("/{game_id}/news", response_model=PaginatedResponse[NewsArticleSummary])
@limiter.limit("30/minute")
async def get_game_news(
    request: Request,
    game_id: int,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get all news articles for a game, newest first."""
    game_result = await db.execute(select(Game).where(Game.id == game_id))
    game = game_result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    count_result = await db.execute(
        select(func.count())
        .select_from(NewsArticle)
        .where(NewsArticle.game_id == game_id)
    )
    total = count_result.scalar() or 0

    articles_result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.game_id == game_id)
        .order_by(desc(NewsArticle.published_at).nulls_last())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    articles = articles_result.scalars().all()

    return PaginatedResponse(
        items=[NewsArticleSummary.model_validate(a) for a in articles],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )


# Anti-gaming constants
LAUNCH_WINDOW_DAYS = 60


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


@router.get("/{game_id}/reviews", response_model=PaginatedResponse[ReviewWithJournalist])
@limiter.limit("30/minute")
async def get_game_reviews(
    request: Request,
    game_id: int,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=100),
    review_timing: Optional[str] = Query(None, regex="^(early|launch_window|late)$"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get all critic reviews for a game."""
    # Get game with release date
    game_result = await db.execute(
        select(Game).where(Game.id == game_id)
    )
    game = game_result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Build timing filter conditions
    timing_conditions = []
    if review_timing and game.release_date:
        if review_timing == "early":
            timing_conditions.append(Review.published_at < game.release_date)
        elif review_timing == "launch_window":
            timing_conditions.append(Review.published_at >= game.release_date)
            timing_conditions.append(
                Review.published_at <= game.release_date + timedelta(days=LAUNCH_WINDOW_DAYS)
            )
        elif review_timing == "late":
            timing_conditions.append(
                Review.published_at > game.release_date + timedelta(days=LAUNCH_WINDOW_DAYS)
            )

    # Get total count (only reviews with actual scores)
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(
            Review.game_id == game_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
            *timing_conditions,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Determine sort direction
    order = asc(Review.published_at) if sort_order == "asc" else desc(Review.published_at)

    # Get reviews (only reviews with actual scores)
    query = (
        select(Review, Journalist, Outlet)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(
            Review.game_id == game_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            Review.score_normalized > 0,  # Exclude unscored (0) reviews
            *timing_conditions,
        )
        .order_by(order)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    for review, journalist, outlet in rows:
        disparity_steam = review.cached_disparity_steam
        disparity_metacritic = review.cached_disparity_metacritic

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
                outlet_name=outlet.name if outlet else None,
                game_title=None,  # Already on game page, title known
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

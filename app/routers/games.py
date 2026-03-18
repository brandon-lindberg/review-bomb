"""Games API endpoints."""

import json
from typing import Optional
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc, extract, or_, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.models import (
    Game,
    Review,
    Journalist,
    Outlet,
    NewsArticle,
    DisparitySnapshot,
    SteamPlayerSnapshot,
    SteamPlayerRangeSnapshot,
)
from app.public_ids import resolve_entity_by_identifier
from app.schemas.schemas import (
    GameDetail,
    GameWithScores,
    DisparitySnapshot as DisparitySnapshotSchema,
    SteamActivityResponse,
    SteamPlayerPoint,
    SteamPlayerMarker,
    ReviewWithJournalist,
    NewsArticleSummary,
    PaginatedResponse,
)
from app.cache import get_cached, set_cached, cache_key, CACHE_TTL_HOT, CACHE_TTL_SHORT
from app.services.review_score_correction import corrected_normalized_score
from app.services.disparity_timeline import build_disparity_timeline_from_reviews
from app.services.flopathon import (
    FlopathonService,
    extract_flopathon_history_points,
    parse_flopathon_peak_summary,
)
from app.services.steam_activity import (
    build_observed_24h_player_points,
    build_steam_activity_markers,
)
from app.services.tokyo_time import tokyo_tomorrow_start_utc, to_tokyo_date

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Anti-gaming: minimum user reviews required for a game to appear in lists (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20
MIN_CRITIC_REVIEWS_FOR_GAMES_LIST = 5


def _steam_score_is_valid(game: Game) -> bool:
    return game.steam_sample_size is not None and game.steam_sample_size >= MIN_STEAM_USER_REVIEWS


def _metacritic_score_is_valid(game: Game) -> bool:
    return (
        game.metacritic_user_score is not None
        and (
            game.metacritic_sample_size is None
            or game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS
        )
    )


def _build_game_with_scores(
    game: Game,
    *,
    latest_review: Optional[ReviewWithJournalist] = None,
) -> GameWithScores:
    steam_valid = _steam_score_is_valid(game)
    metacritic_valid = _metacritic_score_is_valid(game)

    return GameWithScores(
        id=game.id,
        public_id=game.public_id or str(game.id),
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
        steam_player_24h_peak=game.steam_player_24h_peak,
        steam_player_24h_low_observed=game.steam_player_24h_low_observed,
        steam_player_all_time_peak=game.steam_player_all_time_peak,
        steam_player_all_time_peak_at=game.steam_player_all_time_peak_at,
        steam_player_stats_synced_at=game.steam_player_stats_synced_at,
        steam_achievement_count=game.steam_achievement_count,
        steam_achievement_count_synced_at=game.steam_achievement_count_synced_at,
        metacritic_user_score=game.metacritic_user_score if metacritic_valid else None,
        metacritic_sample_size=game.metacritic_sample_size if metacritic_valid else None,
        avg_critic_score=game.avg_critic_score,
        disparity_steam=game.disparity_steam if steam_valid else None,
        disparity_metacritic=game.disparity_metacritic if metacritic_valid else None,
        latest_review=latest_review,
    )


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
    key_hash = cache_key(
        "games:list:v3",
        page=page,
        per_page=per_page,
        year=year,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    cached = await get_cached(f"games:list:{key_hash}")
    if cached:
        return PaginatedResponse[GameWithScores](**json.loads(cached))

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
        # Keep already-released games first, then sort by release date.
        # This prevents upcoming titles from displacing the "most recent" released titles.
        unreleased_sort_expr = case(
            (Game.release_date > func.current_date(), 1),
            else_=0,
        )
        # Keep newly discovered games visible even when release_date is missing by
        # using created_at as a tiebreaker/fallback without non-immutable casts.
        if sort_order == "desc":
            query = query.order_by(
                asc(unreleased_sort_expr),
                desc(Game.release_date).nulls_last(),
                desc(Game.created_at).nulls_last(),
                desc(Game.id),
            )
        else:
            query = query.order_by(
                asc(unreleased_sort_expr),
                asc(Game.release_date).nulls_last(),
                asc(Game.created_at).nulls_last(),
                asc(Game.id),
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
                    desc(Game.release_date).nulls_last(),
                    asc(Game.id),
                )
            else:
                query = query.order_by(desc(order_col).nulls_last())
        else:
            if sort_by == "disparity":
                query = query.order_by(
                    asc(order_col).nulls_last(),
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

    latest_review_lookup: dict[int, ReviewWithJournalist] = {}
    game_ids = [game.id for game in games]
    tokyo_cutoff_utc = tokyo_tomorrow_start_utc()

    if game_ids:
        ranked_reviews = (
            select(
                Review.id.label("review_id"),
                Review.journalist_id.label("journalist_id"),
                Review.outlet_id.label("outlet_id"),
                Review.game_id.label("game_id"),
                Review.review_url.label("review_url"),
                Review.snippet.label("snippet"),
                Review.score_raw.label("score_raw"),
                Review.score_scale.label("score_scale"),
                Review.score_normalized.label("score_normalized"),
                Review.published_at.label("published_at"),
                func.row_number().over(
                    partition_by=Review.game_id,
                    order_by=(Review.published_at.desc(), Review.id.desc()),
                ).label("rn"),
            )
            .where(
                Review.game_id.in_(game_ids),
                Review.score_normalized.isnot(None),
                Review.published_at.isnot(None),
                Review.published_at < tokyo_cutoff_utc,
            )
            .subquery()
        )

        latest_reviews_query = (
            select(
                ranked_reviews.c.game_id,
                ranked_reviews.c.review_id,
                ranked_reviews.c.journalist_id,
                ranked_reviews.c.outlet_id,
                ranked_reviews.c.review_url,
                ranked_reviews.c.snippet,
                ranked_reviews.c.score_raw,
                ranked_reviews.c.score_scale,
                ranked_reviews.c.score_normalized,
                ranked_reviews.c.published_at,
                Journalist.name.label("journalist_name"),
                Journalist.public_id.label("journalist_public_id"),
                Journalist.image_url.label("journalist_image_url"),
                Outlet.name.label("outlet_name"),
                Outlet.public_id.label("outlet_public_id"),
                Game.title.label("game_title"),
                Game.public_id.label("game_public_id"),
                Game.release_date.label("game_release_date"),
            )
            .join(Game, ranked_reviews.c.game_id == Game.id)
            .join(Journalist, ranked_reviews.c.journalist_id == Journalist.id)
            .outerjoin(Outlet, ranked_reviews.c.outlet_id == Outlet.id)
            .where(ranked_reviews.c.rn == 1)
        )

        latest_reviews_result = await db.execute(latest_reviews_query)

        for row in latest_reviews_result:
            corrected_score, _ = corrected_normalized_score(
                score_raw=row.score_raw,
                score_scale=row.score_scale,
                stored_score_normalized=row.score_normalized,
            )
            review_timing = "unknown"
            review_date = to_tokyo_date(row.published_at)
            if review_date and row.game_release_date:
                review_timing = (
                    "early"
                    if review_date < row.game_release_date
                    else "launch_window"
                    if review_date <= row.game_release_date + timedelta(days=60)
                    else "late"
                )
            latest_review_lookup[row.game_id] = ReviewWithJournalist(
                id=row.review_id,
                journalist_id=row.journalist_id,
                journalist_public_id=row.journalist_public_id or str(row.journalist_id),
                game_id=row.game_id,
                game_public_id=row.game_public_id or str(row.game_id),
                outlet_id=row.outlet_id,
                outlet_public_id=(row.outlet_public_id or str(row.outlet_id)) if row.outlet_id is not None else None,
                score_raw=row.score_raw,
                score_scale=row.score_scale,
                score_normalized=corrected_score,
                review_url=row.review_url,
                snippet=row.snippet,
                published_at=row.published_at,
                journalist_name=row.journalist_name,
                journalist_image_url=row.journalist_image_url,
                outlet_name=row.outlet_name,
                game_title=row.game_title,
                game_release_date=row.game_release_date,
                disparity_steam=None,
                disparity_metacritic=None,
                is_launch_window=review_timing == "launch_window",
                review_timing=review_timing,
            )

    items = []
    for game in games:
        items.append(_build_game_with_scores(game, latest_review=latest_review_lookup.get(game.id)))

    response = PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )

    await set_cached(
        f"games:list:{key_hash}",
        json.dumps(response.model_dump(mode="json")),
        CACHE_TTL_HOT,
    )

    return response


@router.get("/{game_id}", response_model=GameDetail)
async def get_game(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get game detail (uses denormalized columns - instant!)."""
    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_id = game.id

    # Fetch the 5 most recent news articles for this game
    news_result = await db.execute(
        select(NewsArticle)
        .where(NewsArticle.game_id == game_id)
        .order_by(desc(NewsArticle.published_at).nulls_last())
        .limit(5)
    )
    recent_news = news_result.scalars().all()

    # Review timing aggregates (pre-release / launch window / late)
    early_review_count = 0
    launch_window_review_count = 0
    late_review_count = 0
    if game.release_date is not None:
        timing_counts_query = select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Review.published_at.isnot(None),
                                Review.published_at < game.release_date,
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
                                Review.published_at >= game.release_date,
                                Review.published_at <= game.release_date + timedelta(days=LAUNCH_WINDOW_DAYS),
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
                                Review.published_at > game.release_date + timedelta(days=LAUNCH_WINDOW_DAYS),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("late_review_count"),
        ).where(
            Review.game_id == game_id,
            Review.score_normalized.isnot(None),
        )
        try:
            timing_counts_row = (await db.execute(timing_counts_query)).one()
        except AssertionError:
            # Unit-test fakes may not provide this aggregate query result.
            timing_counts_row = None
        if timing_counts_row is not None:
            early_review_count = int(timing_counts_row.early_review_count or 0)
            launch_window_review_count = int(timing_counts_row.launch_window_review_count or 0)
            late_review_count = int(timing_counts_row.late_review_count or 0)

    base_game = _build_game_with_scores(game)

    return GameDetail(
        **base_game.model_dump(),
        tier=game.tier,
        percent_recommended=game.percent_recommended,
        early_review_count=early_review_count,
        launch_window_review_count=launch_window_review_count,
        late_review_count=late_review_count,
        created_at=game.created_at,
        updated_at=game.updated_at,
        recent_news=[NewsArticleSummary.model_validate(a) for a in recent_news],
    )


@router.get("/{game_id}/steam-activity", response_model=SteamActivityResponse)
async def get_game_steam_activity(
    game_id: str,
    limit: int = Query(10000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get Steam activity range history and derived milestone markers for a game."""
    cache_hash = cache_key("games:steam-activity:v4", game_id=game_id, limit=limit)
    cached = await get_cached(f"games:steam-activity:{cache_hash}")
    if cached:
        return SteamActivityResponse(**json.loads(cached))

    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    points: list[SteamPlayerPoint] = []
    marker_source_points: list[dict[str, object]] = []
    live_summary_updates: dict[str, object] = {}

    range_result = await db.execute(
        select(SteamPlayerRangeSnapshot)
        .where(SteamPlayerRangeSnapshot.game_id == game.id)
        .order_by(desc(SteamPlayerRangeSnapshot.sampled_at))
        .limit(limit)
    )
    range_snapshots = list(reversed(range_result.scalars().all()))

    if range_snapshots:
        points = [
            SteamPlayerPoint(
                sampled_at=snapshot.sampled_at,
                observed_24h_high=snapshot.players_24h_high,
                observed_24h_low=snapshot.players_24h_low,
            )
            for snapshot in range_snapshots
        ]
        marker_source_points = [
            {
                "sampled_at": snapshot.sampled_at,
                "concurrent_players": snapshot.players_24h_high,
            }
            for snapshot in range_snapshots
        ]
    elif game.steam_app_id is not None:
        raw_points: list[dict[str, object]] = []
        try:
            async with FlopathonService() as flopathon_service:
                payload = await flopathon_service.get_players_payload(game.steam_app_id)
            if payload:
                raw_points = extract_flopathon_history_points(payload)
                if len(raw_points) > limit:
                    raw_points = raw_points[-limit:]
                live_summary_updates = parse_flopathon_peak_summary(payload)
        except Exception:
            raw_points = []
            live_summary_updates = {}

        if not raw_points:
            points = []
            marker_source_points = []
        else:
            observed_points = build_observed_24h_player_points(raw_points)
            points = [SteamPlayerPoint(**point) for point in observed_points]
            marker_source_points = [
                {
                    "sampled_at": point["sampled_at"],
                    "concurrent_players": point["observed_24h_high"],
                }
                for point in observed_points
            ]
    else:
        snapshots_result = await db.execute(
            select(SteamPlayerSnapshot)
            .where(SteamPlayerSnapshot.game_id == game.id)
            .order_by(desc(SteamPlayerSnapshot.sampled_at))
            .limit(limit)
        )
        snapshots = list(reversed(snapshots_result.scalars().all()))
        raw_points = [
            {
                "sampled_at": snapshot.sampled_at,
                "concurrent_players": snapshot.concurrent_players,
            }
            for snapshot in snapshots
        ]
        observed_points = build_observed_24h_player_points(raw_points)
        points = [SteamPlayerPoint(**point) for point in observed_points]
        marker_source_points = [
            {
                "sampled_at": point["sampled_at"],
                "concurrent_players": point["observed_24h_high"],
            }
            for point in observed_points
        ]

    marker_payload = build_steam_activity_markers(
        marker_source_points,
        all_time_peak=game.steam_player_all_time_peak,
        all_time_peak_at=game.steam_player_all_time_peak_at,
    )
    markers = [SteamPlayerMarker(**marker) for marker in marker_payload]

    summary = _build_game_with_scores(game)
    if live_summary_updates:
        summary = summary.model_copy(update=live_summary_updates)

    response = SteamActivityResponse(
        summary=summary,
        points=points,
        markers=markers,
    )
    await set_cached(
        f"games:steam-activity:{cache_hash}",
        response.model_dump_json(),
        CACHE_TTL_SHORT,
    )
    return response


@router.get("/{game_id}/news", response_model=PaginatedResponse[NewsArticleSummary])
@limiter.limit("30/minute")
async def get_game_news(
    request: Request,
    game_id: str,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get all news articles for a game, newest first."""
    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_id = game.id

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


@router.get("/{game_id}/history", response_model=list[DisparitySnapshotSchema])
async def get_game_history(
    game_id: str,
    limit: int = Query(10000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Get historical disparity data for a game from real review timeline."""
    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_id = game.id

    timeline = await build_disparity_timeline_from_reviews(
        db=db,
        entity_filter=(Review.game_id == game_id),
        limit=limit,
    )
    if timeline:
        return timeline

    # Fallback for legacy/edge cases where review dates are unavailable.
    query = (
        select(DisparitySnapshot)
        .where(DisparitySnapshot.game_id == game_id)
        .order_by(desc(DisparitySnapshot.snapshot_date), desc(DisparitySnapshot.id))
        .limit(min(limit * 5, 10000))
    )
    result = await db.execute(query)
    snapshots = result.scalars().all()

    # Deduplicate same-day reruns and keep the latest snapshot for each date.
    unique_snapshots: list[DisparitySnapshot] = []
    seen_dates = set()
    for snapshot in snapshots:
        if snapshot.snapshot_date in seen_dates:
            continue
        seen_dates.add(snapshot.snapshot_date)
        unique_snapshots.append(snapshot)
        if len(unique_snapshots) >= limit:
            break

    return [
        DisparitySnapshotSchema(
            date=s.snapshot_date,
            avg_disparity_steam=s.avg_disparity_steam,
            avg_disparity_metacritic=s.avg_disparity_metacritic,
            avg_disparity_combined=s.avg_disparity_combined,
            review_count=s.review_count,
        )
        for s in reversed(unique_snapshots)
    ]


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
    game_id: str,
    page: int = Query(1, ge=1, le=100),
    per_page: int = Query(20, ge=1, le=500),
    review_timing: Optional[str] = Query(None, regex="^(early|launch_window|late)$"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get all critic reviews for a game."""
    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_id = game.id

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

    # Get total count (only scored reviews, including 0)
    count_query = (
        select(func.count())
        .select_from(Review)
        .where(
            Review.game_id == game_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            *timing_conditions,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Determine sort direction
    order = asc(Review.published_at) if sort_order == "asc" else desc(Review.published_at)

    # Get reviews (only scored reviews, including 0)
    query = (
        select(Review, Journalist, Outlet)
        .join(Journalist, Review.journalist_id == Journalist.id)
        .outerjoin(Outlet, Review.outlet_id == Outlet.id)
        .where(
            Review.game_id == game_id,
            Review.score_normalized.isnot(None),  # Only scored reviews
            *timing_conditions,
        )
        .order_by(order)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    corrected_count = 0
    for review, journalist, outlet in rows:
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
                outlet_public_id=(outlet.public_id or str(outlet.id)) if outlet else None,
                score_raw=review.score_raw,
                score_scale=review.score_scale,
                score_normalized=corrected_score,
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

    if corrected_count:
        print(
            f"Runtime score corrections (game_id={game_id}): "
            f"{corrected_count}/{len(rows)}"
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total > 0 else 0,
    )

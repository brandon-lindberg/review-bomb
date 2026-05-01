"""Games API endpoints."""

import json
import math
from typing import Literal, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, desc, asc, extract, or_, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.models import (
    Game,
    GameSimilarityV3Neighbor,
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
    SimilarGame,
    GameWithScores,
    DisparitySnapshot as DisparitySnapshotSchema,
    SteamActivityResponse,
    SteamActivityMetadata,
    SteamPlayerPoint,
    SteamPlayerMarker,
    ReviewWithJournalist,
    NewsArticleSummary,
    PaginatedResponse,
)
from app.cache import get_cached, set_cached, cache_key, CACHE_TTL_HOT, CACHE_TTL_SHORT
from app.services.review_score_correction import corrected_normalized_score
from app.services.disparity_timeline import build_disparity_timeline_from_reviews
from app.services.player_scraper import PlayerScraperClient, sync_scraper_activity_to_db
from app.services.steam_activity import (
    build_observed_24h_player_points,
    build_steam_activity_markers,
)
from app.services.game_taxonomy import (
    build_similarity_breakdown,
    game_has_sufficient_taxonomy_support,
)
from app.services.game_taxonomy_v2 import (
    TAXONOMY_V2_READY_STATUSES,
    SimilarityBreakdownV2,
    build_similarity_breakdown_v2,
    game_has_sufficient_taxonomy_v2_support,
    get_taxonomy_v2_allowed_archetypes,
)
from app.services.game_similarity_v3 import (
    SIMILARITY_V3_STATUS_HIDDEN,
    SIMILARITY_V3_VERSION,
)
from app.services.tokyo_time import tokyo_tomorrow_start_utc, to_tokyo_date

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Anti-gaming: minimum user reviews required for a game to appear in lists (per source)
MIN_STEAM_USER_REVIEWS = 50
MIN_METACRITIC_USER_REVIEWS = 20
MIN_CRITIC_REVIEWS_FOR_GAMES_LIST = 5
STEAM_ACTIVITY_PREVIEW_POINTS = 12
STEAM_ACTIVITY_DEFAULT_MAX_POINTS = 700
STEAM_ACTIVITY_MIN_BUCKET_SECONDS = 60 * 60
STEAM_ACTIVITY_TRACKING_START_AT = datetime(2026, 3, 19, tzinfo=timezone.utc)


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


def _get_steam_activity_window_start(coverage_end: datetime, window: str) -> datetime | None:
    if window == "24h":
        return coverage_end - timedelta(hours=24)
    if window == "48h":
        return coverage_end - timedelta(hours=48)
    if window == "1w":
        return coverage_end - timedelta(days=7)
    if window == "1m":
        return coverage_end - timedelta(days=30)
    if window == "3m":
        return coverage_end - timedelta(days=90)
    if window == "6m":
        return coverage_end - timedelta(days=180)
    if window == "1y":
        return coverage_end - timedelta(days=365)
    return None


def _resolve_steam_activity_point_budget(limit: int | None, max_points: int | None) -> int:
    if max_points is not None:
        return max_points
    if limit is not None:
        return limit
    return STEAM_ACTIVITY_DEFAULT_MAX_POINTS


def _bucket_steam_activity_points(
    points: list[SteamPlayerPoint],
    max_points: int,
) -> tuple[list[SteamPlayerPoint], int | None, bool]:
    if max_points <= 0 or not points:
        return [], None, False
    if len(points) <= max_points:
        return points, None, False

    first_timestamp = points[0].sampled_at
    last_timestamp = points[-1].sampled_at
    span_seconds = max(1, int((last_timestamp - first_timestamp).total_seconds()))
    bucket_seconds = max(
        STEAM_ACTIVITY_MIN_BUCKET_SECONDS,
        math.ceil(span_seconds / max_points),
    )

    buckets: dict[int, SteamPlayerPoint] = {}
    for point in points:
        bucket_index = int(point.sampled_at.timestamp()) // bucket_seconds
        existing = buckets.get(bucket_index)
        low_candidate = point.observed_24h_low
        if low_candidate == 0 and point.observed_24h_high > 0:
            low_candidate = existing.observed_24h_low if existing else 0

        if existing is None:
            buckets[bucket_index] = SteamPlayerPoint(
                sampled_at=point.sampled_at,
                observed_24h_high=point.observed_24h_high,
                observed_24h_low=low_candidate,
                latest_players=point.latest_players,
            )
            continue

        existing.observed_24h_high = max(existing.observed_24h_high, point.observed_24h_high)
        if low_candidate > 0 or existing.observed_24h_low == 0:
            existing.observed_24h_low = (
                min(existing.observed_24h_low, low_candidate)
                if existing.observed_24h_low > 0 and low_candidate > 0
                else low_candidate
            )
        if point.sampled_at >= existing.sampled_at:
            existing.sampled_at = point.sampled_at
            existing.latest_players = point.latest_players

    bucketed_points = sorted(buckets.values(), key=lambda point: point.sampled_at)
    return bucketed_points, bucket_seconds, True


def _meaningful_game_signal_expression():
    return or_(
        Game.steam_sample_size >= MIN_STEAM_USER_REVIEWS,
        and_(
            Game.metacritic_user_score.isnot(None),
            or_(
                Game.metacritic_sample_size.is_(None),
                Game.metacritic_sample_size >= MIN_METACRITIC_USER_REVIEWS,
            ),
        ),
        Game.critic_review_count >= MIN_CRITIC_REVIEWS_FOR_GAMES_LIST,
    )


def _meaningful_v2_similarity_signal_expression():
    return or_(
        _meaningful_game_signal_expression(),
        Game.top_critic_score.isnot(None),
        Game.avg_critic_score.isnot(None),
        Game.percent_recommended.isnot(None),
        Game.metacritic_score.isnot(None),
    )


def _build_game_with_scores(
    game: Game,
    *,
    latest_review: Optional[ReviewWithJournalist] = None,
    steam_activity_preview: Optional[list[int]] = None,
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
        steam_current_players=game.steam_current_players,
        steam_current_players_sampled_at=game.steam_current_players_sampled_at,
        steam_activity_preview=steam_activity_preview or [],
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


def _build_similar_game(
    game: Game,
    breakdown,
) -> SimilarGame:
    steam_valid = _steam_score_is_valid(game)
    metacritic_valid = _metacritic_score_is_valid(game)

    return SimilarGame(
        id=game.id,
        public_id=game.public_id or str(game.id),
        title=game.title,
        release_date=game.release_date,
        image_url=game.image_url,
        avg_critic_score=game.avg_critic_score,
        steam_user_score=game.steam_user_score if steam_valid else None,
        metacritic_user_score=game.metacritic_user_score if metacritic_valid else None,
        critic_review_count=game.critic_review_count or 0,
        match_reasons=breakdown.match_reasons,
        similarity_score=breakdown.score,
        confidence=breakdown.confidence,
    )


def _build_v3_similar_game(
    game: Game,
    neighbor: GameSimilarityV3Neighbor,
) -> SimilarGame:
    steam_valid = _steam_score_is_valid(game)
    metacritic_valid = _metacritic_score_is_valid(game)
    payload = neighbor.explanation_payload or {}
    match_reasons = list(payload.get("match_reasons") or [])
    confidence = str(payload.get("confidence") or "medium")
    similarity_score = int(round(float(neighbor.final_score or 0) * 1000))
    return SimilarGame(
        id=game.id,
        public_id=game.public_id or str(game.id),
        title=game.title,
        release_date=game.release_date,
        image_url=game.image_url,
        avg_critic_score=game.avg_critic_score,
        steam_user_score=game.steam_user_score if steam_valid else None,
        metacritic_user_score=game.metacritic_user_score if metacritic_valid else None,
        critic_review_count=game.critic_review_count or 0,
        match_reasons=match_reasons[:3],
        similarity_score=similarity_score,
        confidence=confidence,
    )


def _v2_entry_selection_key(
    entry: tuple[int, Game, SimilarGame, SimilarityBreakdownV2],
    *,
    duplicate_count: int = 0,
) -> tuple[int, int, int, str]:
    score, _candidate, item, breakdown = entry
    review_bonus = min(item.critic_review_count or 0, 120)
    critic_bonus = int(item.avg_critic_score or 0) // 2
    derived_bonus = breakdown.derived_similarity_score // 2
    relationship_bonus = {
        "same": 36,
        "strong_neighbor": 24,
        "bridge_neighbor": 22,
        "strong_secondary": 20,
        "bridge_secondary": 18,
        "adjacent_neighbor": 12,
        "adjacent_secondary": 10,
    }.get(breakdown.relationship, 0)
    duplicate_penalty = duplicate_count * 150
    return (
        score + review_bonus + critic_bonus + derived_bonus + relationship_bonus - duplicate_penalty,
        score,
        item.critic_review_count or 0,
        item.title.lower(),
    )


def _candidate_matches_v2_archetype(
    candidate: Game,
    archetype: str,
) -> bool:
    primary = getattr(candidate, "taxonomy_v2_primary_archetype", None)
    if primary == archetype:
        return True
    secondary = getattr(candidate, "taxonomy_v2_secondary_archetypes", None) or []
    return archetype in secondary


def _pick_best_v2_entry(
    entries: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]],
    *,
    selected_ids: set[int],
    predicate,
) -> tuple[int, Game, SimilarGame, SimilarityBreakdownV2] | None:
    best_entry = None
    best_key = None
    for entry in entries:
        _score, candidate, _item, _breakdown = entry
        if candidate.id in selected_ids or not predicate(entry):
            continue
        entry_key = _v2_entry_selection_key(entry)
        if best_key is None or entry_key > best_key:
            best_entry = entry
            best_key = entry_key
    return best_entry


def _select_open_world_fantasy_v2_similar_games(
    anchor: Game,
    qualified: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]],
    *,
    limit: int,
) -> list[SimilarGame]:
    selected: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]] = []
    selected_ids: set[int] = set()
    anchor_primary = getattr(anchor, "taxonomy_v2_primary_archetype", None)
    anchor_fingerprint = getattr(anchor, "taxonomy_v2_fingerprint", None) or {}
    anchor_progression = set(anchor_fingerprint.get("progression_model") or [])
    anchor_traversal = set(anchor_fingerprint.get("traversal_verbs") or [])
    anchor_rules_goals = set(anchor_fingerprint.get("rules_goals") or [])
    anchor_entity_interaction = set(anchor_fingerprint.get("entity_interaction") or [])

    crimson_like_anchor = (
        "horseback" in anchor_traversal
        or "quest_driven" in anchor_progression
        or "complete_quests" in anchor_rules_goals
    )
    zelda_like_anchor = bool(anchor_traversal & {"climbing", "gliding"}) or (
        "construction_placement" in anchor_entity_interaction
    )

    def add_best(predicate) -> None:
        entry = _pick_best_v2_entry(qualified, selected_ids=selected_ids, predicate=predicate)
        if entry is None:
            return
        selected.append(entry)
        selected_ids.add(entry[1].id)

    lane_plan: list[str] = ["same"]
    if crimson_like_anchor:
        lane_plan.extend(
            [
                "soulslike_action_rpg",
                "mmo_action_rpg",
                "western_narrative_rpg",
                "same",
                "open_world_action_adventure",
                "cinematic_action_adventure",
            ]
        )
    else:
        lane_plan.extend(
            [
                "same",
                "soulslike_action_rpg",
                "open_world_action_adventure",
                "western_narrative_rpg",
                "mmo_action_rpg",
                "cinematic_action_adventure",
            ]
        )

    for lane in lane_plan:
        if len(selected) >= limit:
            break
        if lane == "same":
            add_best(
                lambda entry: (
                    getattr(entry[3], "relationship", "") == "same"
                    and getattr(entry[1], "taxonomy_v2_primary_archetype", None) == anchor_primary
                )
            )
            continue
        add_best(
            lambda entry, lane=lane: (
                getattr(entry[3], "relationship", "").startswith(("bridge", "strong", "adjacent"))
                and _candidate_matches_v2_archetype(entry[1], lane)
                and getattr(entry[1], "taxonomy_v2_primary_archetype", None) != anchor_primary
            )
        )

    if len(selected) >= limit:
        return [entry[2] for entry in selected[:limit]]

    remaining = [entry for entry in qualified if entry[1].id not in selected_ids]
    remaining.sort(key=_v2_entry_selection_key, reverse=True)
    for entry in remaining:
        if len(selected) >= limit:
            break
        selected.append(entry)
        selected_ids.add(entry[1].id)

    return [entry[2] for entry in selected[:limit]]


def _select_soulslike_v2_similar_games(
    anchor: Game,
    qualified: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]],
    *,
    limit: int,
) -> list[SimilarGame]:
    def soulslike_key(
        entry: tuple[int, Game, SimilarGame, SimilarityBreakdownV2],
    ) -> tuple[int, int, int, int, str]:
        score, candidate, item, breakdown = entry
        critic_bonus = int(item.avg_critic_score or 0)
        review_bonus = min(item.critic_review_count or 0, 120)
        same_lane_bonus = 40 if _candidate_matches_v2_archetype(candidate, "soulslike_action_rpg") else 0
        studio_bonus = 60 if breakdown.shared_studios else 0
        boss_bonus = 28 if "boss_centric" in breakdown.shared_combat_structure else 0
        challenge_bonus = 42 if "soulslike" in breakdown.shared_challenge_model else 0
        return (
            score + critic_bonus + review_bonus + same_lane_bonus + studio_bonus + boss_bonus + challenge_bonus,
            score,
            critic_bonus,
            item.critic_review_count or 0,
            item.title.lower(),
        )

    anchor_primary = getattr(anchor, "taxonomy_v2_primary_archetype", None)
    exact_primary_lane = [
        entry
        for entry in qualified
        if anchor_primary
        and getattr(entry[1], "taxonomy_v2_primary_archetype", None) == anchor_primary
    ]
    if len(exact_primary_lane) >= limit:
        exact_primary_lane.sort(key=soulslike_key, reverse=True)
        return [entry[2] for entry in exact_primary_lane[:limit]]

    same_lane = list(exact_primary_lane)
    same_lane_ids = {entry[1].id for entry in same_lane}
    secondary_lane = [
        entry
        for entry in qualified
        if anchor_primary
        and entry[1].id not in same_lane_ids
        and _candidate_matches_v2_archetype(entry[1], anchor_primary)
    ]
    same_lane.extend(secondary_lane)
    if len(same_lane) >= limit:
        same_lane.sort(key=soulslike_key, reverse=True)
        return [entry[2] for entry in same_lane[:limit]]

    ordered = list(qualified)
    ordered.sort(key=soulslike_key, reverse=True)
    return [entry[2] for entry in ordered[:limit]]


def _select_diverse_v2_similar_games(
    anchor: Game,
    qualified: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]],
    *,
    limit: int,
) -> list[SimilarGame]:
    anchor_primary = getattr(anchor, "taxonomy_v2_primary_archetype", None)
    if anchor_primary == "open_world_fantasy_action_rpg":
        return _select_open_world_fantasy_v2_similar_games(anchor, qualified, limit=limit)
    if anchor_primary == "soulslike_action_rpg":
        return _select_soulslike_v2_similar_games(anchor, qualified, limit=limit)
    if len(qualified) <= limit:
        return [item for _, _, item, _ in qualified]

    remaining = list(qualified)
    selected: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]] = []
    primary_counts: dict[str, int] = {}

    while remaining and len(selected) < limit:
        best_index = 0
        best_entry = remaining[0]
        best_primary = getattr(best_entry[1], "taxonomy_v2_primary_archetype", None) or ""
        best_key = _v2_entry_selection_key(best_entry, duplicate_count=primary_counts.get(best_primary, 0))

        for index, entry in enumerate(remaining[1:], start=1):
            primary_archetype = getattr(entry[1], "taxonomy_v2_primary_archetype", None) or ""
            entry_key = _v2_entry_selection_key(entry, duplicate_count=primary_counts.get(primary_archetype, 0))
            if entry_key > best_key:
                best_index = index
                best_entry = entry
                best_primary = primary_archetype
                best_key = entry_key

        selected.append(best_entry)
        primary_counts[best_primary] = primary_counts.get(best_primary, 0) + 1
        remaining.pop(best_index)

    return [entry for _, _, entry, _ in selected]


async def _load_steam_activity_previews(
    db: AsyncSession,
    game_ids: list[int],
    *,
    limit_per_game: int = STEAM_ACTIVITY_PREVIEW_POINTS,
) -> dict[int, list[int]]:
    if not game_ids:
        return {}

    ranked_snapshots = (
        select(
            SteamPlayerSnapshot.game_id.label("game_id"),
            SteamPlayerSnapshot.sampled_at.label("sampled_at"),
            SteamPlayerSnapshot.concurrent_players.label("concurrent_players"),
            func.row_number().over(
                partition_by=SteamPlayerSnapshot.game_id,
                order_by=SteamPlayerSnapshot.sampled_at.desc(),
            ).label("rn"),
        )
        .where(SteamPlayerSnapshot.game_id.in_(game_ids))
        .subquery()
    )

    result = await db.execute(
        select(
            ranked_snapshots.c.game_id,
            ranked_snapshots.c.concurrent_players,
            ranked_snapshots.c.sampled_at,
        )
        .where(ranked_snapshots.c.rn <= limit_per_game)
        .order_by(ranked_snapshots.c.game_id.asc(), ranked_snapshots.c.sampled_at.asc())
    )

    previews: dict[int, list[int]] = {}
    for row in result:
        previews.setdefault(row.game_id, []).append(int(row.concurrent_players))

    return previews


@router.get("", response_model=PaginatedResponse[GameWithScores])
async def list_games(
    page: int = Query(1, ge=1, le=10000),
    per_page: int = Query(20, ge=1, le=100),
    year: Optional[int] = Query(None, ge=2015),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    sort_by: str = Query("release_date", regex="^(release_date|title|disparity)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all games with pagination (uses denormalized columns - instant!)."""
    key_hash = cache_key(
        "games:list:v4",
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
    steam_activity_preview_lookup: dict[int, list[int]] = {}
    game_ids = [game.id for game in games]
    tokyo_cutoff_utc = tokyo_tomorrow_start_utc()

    if game_ids:
        steam_activity_preview_lookup = await _load_steam_activity_previews(db, game_ids)

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
        items.append(
            _build_game_with_scores(
                game,
                latest_review=latest_review_lookup.get(game.id),
                steam_activity_preview=steam_activity_preview_lookup.get(game.id),
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


@router.get("/{game_id}/similar", response_model=list[SimilarGame])
async def get_game_similar(
    game_id: str,
    limit: int = Query(4, ge=2, le=5),
    db: AsyncSession = Depends(get_db),
):
    """Get strict similar games using canonical gameplay taxonomy."""
    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    cache_hash = cache_key(
        "games:similar:v23",
        game_id=game_id,
        limit=limit,
        similarity_v3_status=getattr(game, "similarity_v3_status", None),
        similarity_v3_version=getattr(game, "similarity_v3_version", None),
        similarity_v3_computed_at=(
            getattr(game, "similarity_v3_computed_at", None).isoformat()
            if getattr(game, "similarity_v3_computed_at", None) is not None
            else None
        ),
        taxonomy_v2_status=getattr(game, "taxonomy_v2_status", None),
        taxonomy_v2_version=getattr(game, "taxonomy_v2_version", None),
        taxonomy_v2_computed_at=(
            getattr(game, "taxonomy_v2_computed_at", None).isoformat()
            if getattr(game, "taxonomy_v2_computed_at", None) is not None
            else None
        ),
        updated_at=(
            getattr(game, "updated_at", None).isoformat()
            if getattr(game, "updated_at", None) is not None
            else None
        ),
    )
    cached = await get_cached(f"games:similar:{cache_hash}")
    if cached:
        return [SimilarGame(**item) for item in json.loads(cached)]

    if getattr(game, "similarity_v3_version", None) == SIMILARITY_V3_VERSION:
        if getattr(game, "similarity_v3_status", None) == SIMILARITY_V3_STATUS_HIDDEN:
            return []
        neighbor_rows = (
            await db.execute(
                select(GameSimilarityV3Neighbor, Game)
                .join(Game, Game.id == GameSimilarityV3Neighbor.candidate_game_id)
                .where(
                    GameSimilarityV3Neighbor.anchor_game_id == game.id,
                    GameSimilarityV3Neighbor.similarity_version == SIMILARITY_V3_VERSION,
                )
                .order_by(GameSimilarityV3Neighbor.rank.asc())
                .limit(limit)
            )
        ).all()
        if len(neighbor_rows) < 2:
            return []
        items = [_build_v3_similar_game(candidate, neighbor) for neighbor, candidate in neighbor_rows]
        await set_cached(
            f"games:similar:{cache_hash}",
            json.dumps([item.model_dump(mode="json") for item in items]),
            expire_seconds=CACHE_TTL_SHORT,
        )
        return items

    if game_has_sufficient_taxonomy_v2_support(game):
        allowed_archetypes = sorted(get_taxonomy_v2_allowed_archetypes(game))
        if not allowed_archetypes:
            return []

        candidate_query = (
            select(Game)
            .where(
                Game.id != game.id,
                Game.release_date.isnot(None),
                Game.release_date <= func.current_date(),
                _meaningful_v2_similarity_signal_expression(),
                Game.taxonomy_v2_status.in_(list(TAXONOMY_V2_READY_STATUSES)),
                or_(
                    Game.taxonomy_v2_primary_archetype.in_(allowed_archetypes),
                    Game.taxonomy_v2_secondary_archetypes.overlap(allowed_archetypes),
                ),
            )
            .order_by(
                Game.critic_review_count.desc().nulls_last(),
                Game.release_date.desc().nulls_last(),
                Game.id.desc(),
            )
            .limit(max(limit * 60, 600))
        )
        candidate_result = await db.execute(candidate_query)
        candidates = candidate_result.scalars().all()
        if not candidates:
            return []

        qualified: list[tuple[int, Game, SimilarGame, SimilarityBreakdownV2]] = []
        for candidate in candidates:
            breakdown = build_similarity_breakdown_v2(game, candidate)
            if breakdown is None:
                continue
            qualified.append((breakdown.score, candidate, _build_similar_game(candidate, breakdown), breakdown))

        qualified.sort(
            key=lambda item: (
                -item[0],
                -(item[2].critic_review_count or 0),
                item[2].title.lower(),
            ),
        )

        items = _select_diverse_v2_similar_games(game, qualified, limit=limit)
        if len(items) < 2:
            return []
    else:
        if getattr(game, "taxonomy_v2_version", None):
            return []
        if not game_has_sufficient_taxonomy_support(game):
            return []

        anchor_genres = list(game.taxonomy_genres or [])
        secondary_overlap_clauses = []
        if game.taxonomy_themes:
            secondary_overlap_clauses.append(Game.taxonomy_themes.overlap(list(game.taxonomy_themes)))
        if game.taxonomy_modes:
            secondary_overlap_clauses.append(Game.taxonomy_modes.overlap(list(game.taxonomy_modes)))
        if game.taxonomy_perspectives:
            secondary_overlap_clauses.append(Game.taxonomy_perspectives.overlap(list(game.taxonomy_perspectives)))

        if not anchor_genres or not secondary_overlap_clauses:
            return []

        candidate_query = (
            select(Game)
            .where(
                Game.id != game.id,
                Game.release_date.isnot(None),
                Game.release_date <= func.current_date(),
                _meaningful_game_signal_expression(),
                Game.taxonomy_genres.overlap(anchor_genres),
                or_(*secondary_overlap_clauses),
            )
            .order_by(
                Game.release_date.desc().nulls_last(),
                Game.critic_review_count.desc().nulls_last(),
                Game.id.desc(),
            )
            .limit(max(limit * 20, 80))
        )
        candidate_result = await db.execute(candidate_query)
        candidates = candidate_result.scalars().all()
        if not candidates:
            return []

        anchor_outlets = (
            select(Review.outlet_id.label("outlet_id"))
            .where(Review.game_id == game.id, Review.outlet_id.isnot(None))
            .distinct()
            .subquery()
        )
        anchor_journalists = (
            select(Review.journalist_id.label("journalist_id"))
            .where(Review.game_id == game.id)
            .distinct()
            .subquery()
        )
        candidate_ids = [candidate.id for candidate in candidates]
        overlap_result = await db.execute(
            select(
                Review.game_id,
                func.count(
                    func.distinct(
                        case(
                            (
                                Review.outlet_id.in_(select(anchor_outlets.c.outlet_id)),
                                Review.outlet_id,
                            ),
                            else_=None,
                        )
                    )
                ).label("shared_outlets"),
                func.count(
                    func.distinct(
                        case(
                            (
                                Review.journalist_id.in_(select(anchor_journalists.c.journalist_id)),
                                Review.journalist_id,
                            ),
                            else_=None,
                        )
                    )
                ).label("shared_journalists"),
            )
            .where(Review.game_id.in_(candidate_ids))
            .group_by(Review.game_id)
        )
        overlap_lookup = {
            row.game_id: (
                int(getattr(row, "shared_outlets", 0) or 0),
                int(getattr(row, "shared_journalists", 0) or 0),
            )
            for row in overlap_result
        }

        qualified: list[tuple[int, SimilarGame]] = []
        for candidate in candidates:
            shared_outlets, shared_journalists = overlap_lookup.get(candidate.id, (0, 0))
            breakdown = build_similarity_breakdown(
                game,
                candidate,
                shared_outlets=shared_outlets,
                shared_journalists=shared_journalists,
            )
            if breakdown is None:
                continue
            qualified.append((breakdown.score, _build_similar_game(candidate, breakdown)))

        qualified.sort(
            key=lambda item: (
                -item[0],
                -(item[1].critic_review_count or 0),
                -(item[1].release_date.toordinal() if item[1].release_date else -1),
                item[1].title.lower(),
            ),
            reverse=False,
        )

        items = [item for _, item in qualified[:limit]]
        if len(items) < 2:
            return []

    await set_cached(
        f"games:similar:{cache_hash}",
        json.dumps([item.model_dump(mode="json") for item in items]),
        expire_seconds=CACHE_TTL_SHORT,
    )
    return items


@router.get("/{game_id}/steam-activity", response_model=SteamActivityResponse)
async def get_game_steam_activity(
    game_id: str,
    limit: Optional[int] = Query(None, ge=1, le=10000),
    max_points: Optional[int] = Query(None, ge=24, le=5000),
    window: Literal["24h", "48h", "1w", "1m", "3m", "6m", "1y", "max"] = Query("1y"),
    db: AsyncSession = Depends(get_db),
):
    """Get Steam activity range history and derived milestone markers for a game."""
    limit = limit if isinstance(limit, int) else None
    max_points = max_points if isinstance(max_points, int) else None
    window_value = window if isinstance(window, str) else "1y"
    point_budget = _resolve_steam_activity_point_budget(limit, max_points)
    cache_hash = cache_key(
        "games:steam-activity:v12",
        game_id=game_id,
        max_points=point_budget,
        window=window_value,
    )
    cached = await get_cached(f"games:steam-activity:{cache_hash}")
    if cached:
        return SteamActivityResponse(**json.loads(cached))

    game = await resolve_entity_by_identifier(db, Game, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    points: list[SteamPlayerPoint] = []
    marker_source_points: list[dict[str, object]] = []

    scraper_activity = None
    if game.steam_app_id is not None:
        player_scraper = PlayerScraperClient()
        if player_scraper.is_configured:
            async with player_scraper:
                scraper_activity = await player_scraper.get_steam_activity(
                    game.steam_app_id,
                    limit=point_budget,
                    window="max" if window_value == "max" else "1y",
                )

    if scraper_activity and scraper_activity.points:
        await sync_scraper_activity_to_db(db, game, scraper_activity)
        # Flush any newly added player snapshots so the canonical DB-backed series
        # below can include them in the same request.
        await db.flush()

    range_filters = [SteamPlayerRangeSnapshot.game_id == game.id]
    snapshot_filters = [SteamPlayerSnapshot.game_id == game.id]
    range_filters.append(SteamPlayerRangeSnapshot.sampled_at >= STEAM_ACTIVITY_TRACKING_START_AT)
    snapshot_filters.append(SteamPlayerSnapshot.sampled_at >= STEAM_ACTIVITY_TRACKING_START_AT)
    if game.release_date is not None:
        range_filters.append(func.date(SteamPlayerRangeSnapshot.sampled_at) >= game.release_date)
        snapshot_filters.append(func.date(SteamPlayerSnapshot.sampled_at) >= game.release_date)

    range_coverage_result = await db.execute(
        select(
            func.min(SteamPlayerRangeSnapshot.sampled_at),
            func.max(SteamPlayerRangeSnapshot.sampled_at),
            func.count(SteamPlayerRangeSnapshot.id),
        ).where(*range_filters)
    )
    coverage_start, coverage_end, raw_point_count = range_coverage_result.one()
    raw_point_count = int(raw_point_count or 0)

    series_range_filters = list(range_filters)
    if coverage_end is not None:
        window_start = _get_steam_activity_window_start(coverage_end, window_value)
        if window_start is not None:
            series_range_filters.append(SteamPlayerRangeSnapshot.sampled_at >= window_start)

    range_result = await db.execute(
        select(SteamPlayerRangeSnapshot)
        .where(*series_range_filters)
        .order_by(asc(SteamPlayerRangeSnapshot.sampled_at))
    )
    range_snapshots = list(range_result.scalars().all())
    range_snapshots = [
        snapshot
        for snapshot in range_snapshots
        if snapshot.sampled_at >= STEAM_ACTIVITY_TRACKING_START_AT
        and (game.release_date is None or snapshot.sampled_at.date() >= game.release_date)
    ]
    range_snapshots.sort(key=lambda snapshot: snapshot.sampled_at)

    if range_snapshots:
        snapshot_result = await db.execute(
            select(
                SteamPlayerSnapshot.sampled_at,
                SteamPlayerSnapshot.concurrent_players,
            )
            .where(
                SteamPlayerSnapshot.game_id == game.id,
                SteamPlayerSnapshot.sampled_at.in_([snapshot.sampled_at for snapshot in range_snapshots]),
            )
            .order_by(SteamPlayerSnapshot.sampled_at, SteamPlayerSnapshot.id)
        )
        latest_players_by_sampled_at: dict[object, int] = {}
        for sampled_at, concurrent_players in snapshot_result.all():
            latest_players_by_sampled_at[sampled_at] = concurrent_players

        points = [
            SteamPlayerPoint(
                sampled_at=snapshot.sampled_at,
                observed_24h_high=snapshot.players_24h_high,
                observed_24h_low=snapshot.players_24h_low,
                latest_players=latest_players_by_sampled_at.get(snapshot.sampled_at),
            )
            for snapshot in range_snapshots
        ]
    else:
        snapshot_coverage_result = await db.execute(
            select(
                func.min(SteamPlayerSnapshot.sampled_at),
                func.max(SteamPlayerSnapshot.sampled_at),
                func.count(SteamPlayerSnapshot.id),
            ).where(*snapshot_filters)
        )
        coverage_start, coverage_end, raw_point_count = snapshot_coverage_result.one()
        raw_point_count = int(raw_point_count or 0)

        series_snapshot_filters = list(snapshot_filters)
        if coverage_end is not None:
            window_start = _get_steam_activity_window_start(coverage_end, window_value)
            if window_start is not None:
                series_snapshot_filters.append(SteamPlayerSnapshot.sampled_at >= window_start)

        snapshots_result = await db.execute(
            select(SteamPlayerSnapshot)
            .where(*series_snapshot_filters)
            .order_by(asc(SteamPlayerSnapshot.sampled_at))
        )
        snapshots = list(snapshots_result.scalars().all())
        snapshots = [
            snapshot
            for snapshot in snapshots
            if snapshot.sampled_at >= STEAM_ACTIVITY_TRACKING_START_AT
            and (game.release_date is None or snapshot.sampled_at.date() >= game.release_date)
        ]
        snapshots.sort(key=lambda snapshot: snapshot.sampled_at)
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
                "concurrent_players": point.get("latest_players", point["observed_24h_high"]),
            }
            for point in observed_points
        ]

    summary_source_points = points
    points, bucket_seconds, is_aggregated = _bucket_steam_activity_points(points, point_budget)
    marker_source_points = [
        {
            "sampled_at": point.sampled_at,
            "concurrent_players": point.latest_players
            if point.latest_players is not None
            else point.observed_24h_high,
        }
        for point in points
    ]

    summary = _build_game_with_scores(game)
    if summary_source_points:
        latest_point = summary_source_points[-1]
        # Guard against transient zero lows: if the 24h low is 0 but the high
        # is healthy, a server blip likely corrupted the low.  Keep the
        # previous value (None lets the model default stand).
        observed_low: int | None = latest_point.observed_24h_low
        if observed_low == 0 and latest_point.observed_24h_high > 0:
            observed_low = None
        trusted_summary_updates: dict[str, object] = {
            "steam_player_24h_peak": latest_point.observed_24h_high,
            "steam_player_24h_low_observed": observed_low,
            "steam_player_stats_synced_at": latest_point.sampled_at,
        }
        peak_point = max(summary_source_points, key=lambda point: point.observed_24h_high)
        trusted_summary_updates["steam_player_all_time_peak"] = peak_point.observed_24h_high
        trusted_summary_updates["steam_player_all_time_peak_at"] = peak_point.sampled_at
        summary = summary.model_copy(update=trusted_summary_updates)
    else:
        summary = summary.model_copy(
            update={
                "steam_player_24h_peak": None,
                "steam_player_24h_low_observed": None,
                "steam_player_all_time_peak": None,
                "steam_player_all_time_peak_at": None,
                "steam_player_stats_synced_at": None,
            }
        )

    marker_payload = build_steam_activity_markers(
        marker_source_points,
        all_time_peak=summary.steam_player_all_time_peak,
        all_time_peak_at=summary.steam_player_all_time_peak_at,
    )
    markers = [SteamPlayerMarker(**marker) for marker in marker_payload]

    response = SteamActivityResponse(
        summary=summary,
        points=points,
        markers=markers,
        metadata=SteamActivityMetadata(
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            raw_point_count=raw_point_count,
            bucket_seconds=bucket_seconds,
            is_aggregated=is_aggregated,
        ),
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

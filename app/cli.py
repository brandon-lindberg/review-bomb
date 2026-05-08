#!/usr/bin/env python3
"""
CLI for managing the Game Journalist Review Disparity Tracker.

Usage:
    python -m app sync              Run OpenCritic sync (fast incremental tail scan)
    python -m app sync --status     Show sync status and progress
    python -m app sync --reset      Reset sync state (start fresh)
    python -m app sync --full-scan  Force full OpenCritic catalog sweep
    python -m app import-steam-game --app-id 2701720
                                    Import a Steam-only game directly into the catalog
    python -m app match             Match games to Steam/Metacritic IDs
    python -m app match --days 180  Match only games released in last 180 days
    python -m app steam             Sync Steam user scores and public Steam activity
    python -m app steam --days 30   Sync Steam-owned data for games released in last 30 days
    python -m app steamdb           Sync SteamDB peak data only
    python -m app steamdb --days 30 Sync SteamDB peaks for games released in last 30 days
    python -m app game-images       Backfill missing game images from Steam
    python -m app metacritic        Sync Metacritic scores (skips recently synced games)
    python -m app metacritic --recent  Sync only games released in last 90 days
    python -m app disparity         Calculate disparity snapshots
    python -m app refresh-reviews   Re-fetch reviews for recent games (last 90 days)
    python -m app clear             Clear all data from database
    python -m app backfill          Backfill denormalized Game columns from UserScore/Review data
    python -m app recompute-scores  Recompute review score_normalized values from score_raw/score_scale
    python -m app merge-games       Merge deprecated games into canonical records
    python -m app news              Fetch latest gaming news from RSS feeds
    python -m app news-backfill     Link existing news articles to games by title matching
    python -m app taxonomy-backfill Refresh stored taxonomy labels and canonical facets
    python -m app description-backfill Refresh source-specific descriptions and taxonomy V2 text corpus
    python -m app taxonomy-audit    Show raw source labels that do not map to canonical facets
    python -m app similar-debug     Explain why a game does or does not qualify for similar games
    python -m app taxonomy-v2-backfill Compute and store Similar Games Taxonomy V2 fingerprints
    python -m app taxonomy-v2-debug    Inspect the Similar Games Taxonomy V2 fingerprint for one game
    python -m app taxonomy-v2-label-audit Audit raw label coverage against Similar Games Taxonomy V2
    python -m app taxonomy-v2-text-audit  Audit recurring text phrases by Similar Games Taxonomy V2 status
    python -m app taxonomy-v2-near-miss-audit Audit missing required axes for hidden V2 games
    python -m app taxonomy-v2-boilerplate-audit Audit recurring storefront boilerplate in V2 text corpora
    python -m app taxonomy-v2-confusion-audit Audit V2 family/archetype coverage and pairings
    python -m app taxonomy-v2-gold-set-audit Audit live similar-games output against the V2 gold set
    python -m app similarity-v3-corpus Build Similar Games V3 corpus rows and embeddings
    python -m app similarity-v3-embed Refresh Similar Games V3 embeddings for target games
    python -m app similarity-v3-neighbors Preview Similar Games V3 ranked neighbors
    python -m app similarity-v3-publish Publish Similar Games V3 neighbors for serving
    python -m app similarity-v3-gold-audit Audit Similar Games V3 against the gold set
    python -m app similarity-v3-confusion-audit Audit Similar Games V3 relationship distribution
    python -m app similarity-v3-hidden-audit Audit Similar Games V3 hidden states
    python -m app queue-job Enqueue a background worker job onto the Dramatiq queues
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from app.database import async_session_maker, engine
from app.models.models import Game
from app.services.sync_orchestrator import SyncOrchestrator, run_daily_sync, get_sync_status


_SIMILARITY_V3_CORPUS_BATCH_SIZE = 50
_SIMILARITY_V3_PUBLISH_BATCH_SIZE = 25
_SIMILARITY_V3_BATCH_RETRY_LIMIT = 5
_SIMILARITY_V3_RETRYABLE_ERROR_MARKERS = (
    "connection was closed in the middle of operation",
    "the database system is in recovery mode",
    "cannot connect now",
    "connection does not exist",
    "server closed the connection unexpectedly",
    "terminating connection",
    "connection reset by peer",
)


def _truncate_cli_text(value: str | None, *, limit: int = 96) -> str:
    if not value:
        return ""
    cleaned = " ".join(str(value).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _is_transient_database_error(exc: BaseException) -> bool:
    if isinstance(exc, (DBAPIError, OperationalError, InterfaceError)):
        if getattr(exc, "connection_invalidated", False):
            return True
    lowered = str(exc).lower()
    if any(marker in lowered for marker in _SIMILARITY_V3_RETRYABLE_ERROR_MARKERS):
        return True
    for nested in (getattr(exc, "__cause__", None), getattr(exc, "__context__", None)):
        if nested is not None and nested is not exc and _is_transient_database_error(nested):
            return True
    return False


async def _retry_similarity_v3_batch(
    label: str,
    batch_number: int,
    total_batches: int,
    operation,
):
    last_error: BaseException | None = None
    for attempt in range(1, _SIMILARITY_V3_BATCH_RETRY_LIMIT + 1):
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            if not _is_transient_database_error(exc) or attempt >= _SIMILARITY_V3_BATCH_RETRY_LIMIT:
                raise
            delay_seconds = min(30, 2 * attempt)
            print(
                f"  {label} batch {batch_number}/{total_batches} hit transient DB failure "
                f"(attempt {attempt}/{_SIMILARITY_V3_BATCH_RETRY_LIMIT}): {exc}"
            )
            print(f"  Retrying after {delay_seconds}s...")
            await engine.dispose()
            await asyncio.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{label} batch {batch_number}/{total_batches} failed without an exception")


async def _load_similarity_v3_target_game_ids(
    *,
    dirty_only: bool = False,
    game_identifier: str | None = None,
    limit: int | None = None,
) -> list[int]:
    from app.services.game_similarity_v3 import load_similarity_v3_target_games

    async with async_session_maker() as db:
        games = await load_similarity_v3_target_games(
            db,
            dirty_only=dirty_only,
            game_identifier=game_identifier,
            limit=limit,
        )
    return [game.id for game in games if game is not None and game.id is not None]


async def _load_games_by_ids(db, game_ids: list[int]) -> list[Game]:
    if not game_ids:
        return []
    result = await db.execute(select(Game).where(Game.id.in_(game_ids)))
    by_id = {game.id: game for game in result.scalars().all()}
    return [by_id[game_id] for game_id in game_ids if game_id in by_id]


def _should_update_release_date_from_metacritic(
    existing_release_date,
    candidate_release_date,
    *,
    today,
) -> bool:
    """
    Decide whether a Metacritic-derived release date should overwrite DB value.

    Strategy:
    - Always fill missing dates.
    - Correct placeholder future dates using earlier/released dates.
    - Never regress a known released date to a future value.
    - For two past dates, only apply large forward corrections (>=120 days),
      which catches stale-year errors while avoiding remaster/port regressions.
    """
    if candidate_release_date is None:
        return False
    if existing_release_date is None:
        return True
    if candidate_release_date == existing_release_date:
        return False

    # Do not replace a known released date with a future candidate.
    if existing_release_date <= today and candidate_release_date > today:
        return False

    # Replace placeholder future dates with released or earlier corrected dates.
    if existing_release_date > today:
        if candidate_release_date <= today:
            return True
        return candidate_release_date < existing_release_date

    # Both are in the past: allow only substantial forward corrections.
    if candidate_release_date > existing_release_date:
        return (candidate_release_date - existing_release_date).days >= 120

    # Avoid moving a date earlier in the past from Metacritic alone.
    return False


async def _resolve_target_game_with_title_fallback(db, Game, identifier: str):
    from sqlalchemy import func, select

    from app.public_ids import resolve_entity_by_identifier
    from app.services.game_taxonomy import normalize_taxonomy_label

    raw_identifier = str(identifier).strip()
    if not raw_identifier:
        return None

    game = await resolve_entity_by_identifier(db, Game, raw_identifier)
    if game is not None:
        return game

    lowered = raw_identifier.lower()
    exact = (
        await db.execute(
            select(Game)
            .where(func.lower(Game.title) == lowered)
            .order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
        )
    ).scalars().first()
    if exact is not None:
        return exact

    normalized_target = normalize_taxonomy_label(raw_identifier)
    if not normalized_target:
        return None

    candidates = (
        await db.execute(
            select(Game)
            .where(func.lower(Game.title).like(f"%{lowered}%"))
            .order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
            .limit(25)
        )
    ).scalars().all()
    if not candidates:
        return None

    def _rank(candidate):
        title = getattr(candidate, "title", "") or ""
        lowered_title = title.lower()
        normalized_title = normalize_taxonomy_label(title)
        exact_lower = 0 if lowered_title == lowered else 1
        exact_normalized = 0 if normalized_title == normalized_target else 1
        starts_with = 0 if lowered_title.startswith(lowered) else 1
        contains_normalized = 0 if normalized_target in normalized_title else 1
        return (
            exact_lower,
            exact_normalized,
            starts_with,
            contains_normalized,
            len(title),
            -(getattr(candidate, "id", 0) or 0),
        )

    return sorted(candidates, key=_rank)[0]


async def cmd_sync(args):
    """Handle sync command."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)

        if args.status:
            status = await orchestrator.get_sync_status()
            print("\n=== Sync Status ===")
            print(f"Games synced (total): {status['games_synced_total']}")
            print(f"Games in queue: {status['games_in_queue']}")
            print(f"Last skip position: {status['last_skip_position']}")
            print("\n--- Database Stats ---")
            for key, value in status['database_stats'].items():
                print(f"  {key}: {value:,}")
            return

        if args.reset:
            confirm = input("Are you sure you want to reset sync state? [y/N] ")
            if confirm.lower() == 'y':
                await orchestrator.reset_sync_state()
                print("Sync state has been reset.")
            else:
                print("Cancelled.")
            return

        # Run the daily sync
        print(f"\n{'='*50}")
        print(f"Starting OpenCritic sync at {datetime.now().isoformat()}")
        if args.full_scan:
            print("Mode: FULL catalog scan")
        else:
            print(
                "Mode: incremental tail scan "
                f"(stop after {args.stale_pages} consecutive stale pages)"
            )
        if args.no_auto_review_refresh:
            print("Post-sync review refresh: disabled")
        else:
            print(
                "Post-sync review refresh: enabled "
                f"(days={args.review_refresh_days}, "
                f"limit={args.review_refresh_limit}, "
                f"min_hours={args.review_refresh_min_hours})"
            )
        print(f"{'='*50}\n")

        try:
            stats = await orchestrator.run_daily_sync(
                full_scan=args.full_scan,
                stale_pages_before_stop=args.stale_pages,
                auto_refresh_recent_reviews=not args.no_auto_review_refresh,
                review_refresh_days=args.review_refresh_days,
                review_refresh_limit=args.review_refresh_limit,
                review_refresh_min_hours=args.review_refresh_min_hours,
            )
            print(f"\n{'='*50}")
            print("Sync completed successfully!")
            print(f"{'='*50}")
            return 0
        except Exception as e:
            print(f"\nSync failed: {e}")
            return 1


async def _load_cli_steam_games(db, args, Game):
    """Load Steam-linked games for CLI sync commands."""
    from sqlalchemy import select, and_, or_, func

    min_recent_add_window_days = 14
    recent_opencritic_id_window = 300

    query = select(Game).where(Game.steam_app_id.isnot(None))
    mode = "with Steam IDs"
    if getattr(args, "app_id", None) is not None:
        query = query.where(Game.steam_app_id == args.app_id)
        mode = f"with Steam app ID {args.app_id}"
    if args.days is not None:
        now = datetime.now(timezone.utc)
        cutoff_date = (now - timedelta(days=args.days)).date()
        today = now.date()
        created_cutoff_date = (now - timedelta(days=min_recent_add_window_days)).date()
        created_cutoff_dt = datetime.combine(
            created_cutoff_date,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        max_opencritic_id_subq = select(func.max(Game.opencritic_id)).scalar_subquery()
        recent_opencritic_condition = and_(
            Game.opencritic_id.isnot(None),
            Game.opencritic_id >= (max_opencritic_id_subq - recent_opencritic_id_window),
        )
        query = query.where(
            or_(
                and_(
                    Game.release_date.isnot(None),
                    Game.release_date >= cutoff_date,
                    Game.release_date <= today,
                ),
                and_(
                    Game.created_at >= created_cutoff_dt,
                    or_(Game.release_date.is_(None), Game.release_date <= today),
                ),
                and_(
                    recent_opencritic_condition,
                    or_(Game.release_date.is_(None), Game.release_date <= today),
                ),
            )
        )
        mode = (
            f"released in last {args.days} days, or added in last "
            f"{min_recent_add_window_days} days, or in recent OpenCritic ID window "
            "(excluding future release dates) with Steam IDs"
        )

    if args.days is not None:
        query = query.order_by(
            Game.created_at.desc().nulls_last(),
            Game.release_date.desc().nulls_last(),
            Game.id.desc(),
        )
    else:
        query = query.order_by(Game.release_date.desc().nulls_last(), Game.id.desc())

    if args.limit:
        query = query.limit(args.limit)

    result = await db.execute(query)
    return result.scalars().all(), mode


async def cmd_steam(args):
    """Handle Steam sync command."""
    from app.services.game_taxonomy import (
        extract_steam_source_labels,
        sync_game_source_taxonomy,
    )
    from app.services.game_taxonomy_v2 import (
        apply_steam_descriptions,
        refresh_game_taxonomy_v2_text,
    )
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty
    from app.services.steam import SteamService
    from app.services.steam_catalog import ensure_tracked_steam_games
    from app.services.steam_activity import SteamActivityService, sync_game_steam_public_activity
    from app.models.models import Game, UserScore, UserScoreSource
    from sqlalchemy import delete
    from difflib import SequenceMatcher
    from contextlib import AsyncExitStack
    import re

    mapping_similarity_min = 0.65

    def normalize_title_for_match(title: str) -> str:
        normalized = (title or "").lower()
        normalized = re.sub(r"[`'’]", "", normalized)
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def title_similarity(a: str, b: str) -> float:
        return SequenceMatcher(
            None,
            normalize_title_for_match(a),
            normalize_title_for_match(b),
        ).ratio()

    run_activity = bool(getattr(args, "with_activity", False))
    if not run_activity:
        print("Steam activity writes are disabled for this run (scores-only mode).")
        print("Use --with-activity only when scraper worker is paused to avoid write contention.")

    async with async_session_maker() as db:
        synced = 0
        activity_updated = 0
        activity_snapshots = 0
        processed = 0
        failed = 0
        no_score = 0
        skipped_upcoming = 0
        skipped_invalid_app = 0
        skipped_mismatch = 0
        cleared_mismatch = 0
        cleared_steam_score_rows = 0

        async with AsyncExitStack() as stack:
            service = await stack.enter_async_context(SteamService())
            activity_service = (
                await stack.enter_async_context(SteamActivityService())
                if run_activity
                else None
            )
            curated_stats = await ensure_tracked_steam_games(db, service)
            if curated_stats["created"] or curated_stats["updated"]:
                print(
                    "Ensured curated Steam-only catalog entries: "
                    f"{curated_stats['created']} created, {curated_stats['updated']} updated"
                )

            games, mode = await _load_cli_steam_games(db, args, Game)

            print(f"Found {len(games)} games {mode}")

            if args.limit:
                print(f"Processing up to {args.limit} games")

            for game in games:
                processed += 1
                try:
                    app_id = game.steam_app_id
                    print(f"Fetching Steam score for: {game.title} (app_id={app_id})...")

                    app_details = await service.get_app_details(app_id)
                    if not app_details:
                        print("  Skip: app_id not found via Steam appdetails")
                        skipped_invalid_app += 1

                        candidates = await service.search_games(game.title)
                        if candidates:
                            top = ", ".join(
                                f"{c['steam_app_id']}:{c['name']}" for c in candidates[:3]
                            )
                            print(f"  Candidate app IDs: {top}")
                        continue

                    transformed = SteamService.transform_app_details(app_details, app_id)
                    text_changed = apply_steam_descriptions(
                        game,
                        short_description=transformed.get("steam_short_description"),
                        detailed_description=transformed.get("steam_detailed_description"),
                    )
                    if text_changed:
                        refresh_game_taxonomy_v2_text(game)
                        mark_game_similarity_v3_dirty(game, "source_text_steam")

                    taxonomy_changed = await sync_game_source_taxonomy(
                        db,
                        game,
                        source="steam",
                        source_labels=extract_steam_source_labels(app_details),
                    )
                    if taxonomy_changed:
                        mark_game_similarity_v3_dirty(game, "source_labels_steam")

                    steam_title = (app_details.get("name") or "").strip()
                    release_info = app_details.get("release_date") or {}
                    release_raw = release_info.get("date") or "unknown"

                    # Cross-reference mapped app title before pulling score.
                    if steam_title:
                        similarity = title_similarity(game.title, steam_title)
                        if similarity < mapping_similarity_min:
                            print(
                                f"  Skip: likely wrong app mapping "
                                f"(similarity={similarity:.2f}, steam_title='{steam_title}')"
                            )
                            skipped_mismatch += 1
                            game.steam_app_id = None
                            game.steam_user_score = None
                            game.steam_sample_size = None
                            cleared_mismatch += 1
                            deleted_scores = await db.execute(
                                delete(UserScore).where(
                                    UserScore.game_id == game.id,
                                    UserScore.source == UserScoreSource.STEAM,
                                )
                            )
                            if deleted_scores.rowcount:
                                cleared_steam_score_rows += deleted_scores.rowcount
                            print("  Cleared stored steam_app_id for rematch")

                            candidates = await service.search_games(game.title)
                            if candidates:
                                top = ", ".join(
                                    f"{c['steam_app_id']}:{c['name']}" for c in candidates[:3]
                                )
                                print(f"  Candidate app IDs: {top}")
                            continue

                    if release_info.get("coming_soon"):
                        print(
                            f"  Skip: Steam marks app as coming soon "
                            f"(steam_title='{steam_title}', release='{release_raw}')"
                        )
                        skipped_upcoming += 1
                        continue

                    score_data = await service.get_user_score(app_id)

                    if score_data:
                        user_score = UserScore(
                            game_id=game.id,
                            source=UserScoreSource.STEAM,
                            score=score_data["score"],
                            score_raw=score_data["score_raw"],
                            sample_size=score_data["sample_size"],
                            positive_count=score_data["positive_count"],
                            negative_count=score_data["negative_count"],
                            review_score_desc=score_data["review_score_desc"],
                            scraped_at=score_data["scraped_at"],
                        )
                        db.add(user_score)
                        synced += 1
                        print(f"  Score: {score_data['score']} ({score_data['review_score_desc']})")

                        # Update denormalized columns on Game
                        game.steam_user_score = score_data["score"]
                        game.steam_sample_size = score_data["sample_size"]
                    else:
                        no_score += 1
                        print(
                            f"  No score data returned "
                            f"(steam_title='{steam_title}', release='{release_raw}')"
                        )

                    if run_activity and activity_service is not None:
                        activity_result = await sync_game_steam_public_activity(
                            db,
                            game,
                            activity_service,
                        )
                        if activity_result["snapshot_created"]:
                            activity_snapshots += 1
                        if (
                            activity_result["snapshot_created"]
                            or activity_result["achievement_updated"]
                        ):
                            activity_updated += 1
                            if activity_result["current_players"] is not None:
                                print(f"  Players Right Now: {activity_result['current_players']:,}")
                            if game.steam_achievement_count is not None:
                                print(f"  Achievements: {game.steam_achievement_count:,}")

                except Exception as e:
                    print(f"  Error: {e}")
                    failed += 1

                # Commit every 25 games processed
                if processed % 25 == 0:
                    await db.commit()
                    print(f"  Processed {processed}/{len(games)} games...")

        await db.commit()
        print(
            "\nSteam sync complete: "
            f"{synced} synced, {no_score} no score, {skipped_upcoming} upcoming skipped, "
            f"{skipped_invalid_app} invalid app IDs, {skipped_mismatch} mapping mismatches "
            f"({cleared_mismatch} cleared, {cleared_steam_score_rows} score rows deleted), "
            f"{activity_updated} activity updates ({activity_snapshots} snapshots), "
            f"{failed} failed, {processed} processed"
        )


async def cmd_steamdb(args):
    """Handle SteamDB peak sync command."""
    from app.services.steam import SteamService
    from app.services.steam_catalog import ensure_tracked_steam_games
    from app.services.steam_activity import SteamActivityService, sync_game_steamdb_peaks
    from app.models.models import Game

    async with async_session_maker() as db:
        processed = 0
        updated = 0
        failed = 0

        async with SteamService() as steam_service, SteamActivityService() as activity_service:
            curated_stats = await ensure_tracked_steam_games(db, steam_service)
            if curated_stats["created"] or curated_stats["updated"]:
                print(
                    "Ensured curated Steam-only catalog entries: "
                    f"{curated_stats['created']} created, {curated_stats['updated']} updated"
                )

            games, mode = await _load_cli_steam_games(db, args, Game)

            print(f"Found {len(games)} games {mode}")

            if args.limit:
                print(f"Processing up to {args.limit} games")

            for game in games:
                processed += 1
                try:
                    print(f"Fetching SteamDB peaks for: {game.title} (app_id={game.steam_app_id})...")
                    peak_result = await sync_game_steamdb_peaks(
                        game,
                        activity_service,
                    )

                    if peak_result["peaks_updated"]:
                        updated += 1
                        if game.steam_player_24h_peak is not None:
                            print(f"  24h Peak: {game.steam_player_24h_peak:,}")
                        if game.steam_player_all_time_peak is not None:
                            print(f"  All-Time Peak: {game.steam_player_all_time_peak:,}")
                        if game.steam_player_all_time_peak_at is not None:
                            print(f"  All-Time Peak At: {game.steam_player_all_time_peak_at.isoformat()}")
                    else:
                        print("  No SteamDB peak data returned")
                except Exception as e:
                    print(f"  Error: {e}")
                    failed += 1

                if processed % 25 == 0:
                    await db.commit()
                    print(f"  Processed {processed}/{len(games)} games...")

        await db.commit()
        print(
            "\nSteamDB sync complete: "
            f"{updated} peak rows updated, {failed} failed, {processed} processed"
        )


async def cmd_import_steam_game(args):
    """Import or update a game directly from Steam, even without OpenCritic coverage."""
    import re

    from sqlalchemy import select, func

    from app.models.models import Game, UserScore, UserScoreSource
    from app.services.game_taxonomy import (
        extract_steam_source_labels,
        sync_game_source_taxonomy,
    )
    from app.services.game_taxonomy_v2 import (
        apply_steam_descriptions,
        refresh_game_taxonomy_v2_text,
    )
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty
    from app.services.steam import SteamService
    from app.services.steam_activity import (
        SteamActivityService,
        sync_game_steam_public_activity,
        sync_game_steamdb_peaks,
    )

    if args.app_id is None and not getattr(args, "query", None):
        print("Provide either --app-id or --query.")
        return 1

    def normalize_title(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
        return re.sub(r"\s+", " ", normalized).strip()

    async with async_session_maker() as db:
        async with SteamService() as steam_service, SteamActivityService() as activity_service:
            app_id = args.app_id
            selected_name = None

            if app_id is None:
                query = args.query.strip()
                search_results = await steam_service.search_games(query)
                if not search_results:
                    print(f"No Steam results found for query: {query}")
                    return 1

                normalized_query = normalize_title(query)

                def result_rank(item: dict[str, object]) -> tuple[int, int]:
                    name = normalize_title(str(item.get("name") or ""))
                    if name == normalized_query:
                        return (3, len(name))
                    if name.startswith(normalized_query):
                        return (2, len(name))
                    if normalized_query in name:
                        return (1, len(name))
                    return (0, len(name))

                ranked_results = sorted(search_results, key=result_rank, reverse=True)
                best_match = ranked_results[0]
                app_id = int(best_match["steam_app_id"])
                selected_name = str(best_match.get("name") or "").strip() or None
                print(f"Selected Steam app {app_id}: {selected_name or 'Unknown title'}")

            app_details = await steam_service.get_app_details(app_id)
            if not app_details:
                print(f"Steam app details not found for app_id={app_id}")
                return 1

            transformed = SteamService.transform_app_details(app_details, app_id)
            steam_title = (transformed.get("title") or selected_name or "").strip()
            if not steam_title:
                print(f"Steam app {app_id} did not return a title")
                return 1

            existing_by_app = (
                await db.execute(select(Game).where(Game.steam_app_id == app_id))
            ).scalar_one_or_none()
            existing_by_title = (
                await db.execute(
                    select(Game).where(func.lower(Game.title) == steam_title.lower())
                )
            ).scalar_one_or_none()

            if existing_by_app is not None:
                game = existing_by_app
                action = "Updated existing Steam-linked game"
            elif existing_by_title is not None:
                if existing_by_title.steam_app_id is not None and existing_by_title.steam_app_id != app_id:
                    print(
                        "Refusing to import due to title collision with a different Steam app ID: "
                        f"{existing_by_title.title} already points to {existing_by_title.steam_app_id}"
                    )
                    return 1
                game = existing_by_title
                action = "Updated existing title match"
            else:
                game = Game(
                    title=steam_title,
                    steam_app_id=app_id,
                    description=transformed.get("description"),
                    release_date=transformed.get("release_date"),
                    image_url=transformed.get("image_url"),
                )
                db.add(game)
                await db.flush()
                action = "Created new Steam-only game"

            if game.steam_app_id != app_id:
                game.steam_app_id = app_id

            if not game.title:
                game.title = steam_title
            elif normalize_title(game.title) == normalize_title(steam_title) and game.title != steam_title:
                game.title = steam_title

            if transformed.get("description") and not game.description:
                game.description = transformed["description"]
            if apply_steam_descriptions(
                game,
                short_description=transformed.get("steam_short_description"),
                detailed_description=transformed.get("steam_detailed_description"),
            ):
                refresh_game_taxonomy_v2_text(game)
                mark_game_similarity_v3_dirty(game, "source_text_steam")

            if transformed.get("image_url") and not game.image_url:
                game.image_url = transformed["image_url"]

            candidate_release_date = transformed.get("release_date")
            today = datetime.now(timezone.utc).date()
            if _should_update_release_date_from_metacritic(
                game.release_date,
                candidate_release_date,
                today=today,
            ):
                game.release_date = candidate_release_date

            score_data = await steam_service.get_user_score(app_id)
            if score_data:
                db.add(
                    UserScore(
                        game_id=game.id,
                        source=UserScoreSource.STEAM,
                        score=score_data["score"],
                        score_raw=score_data["score_raw"],
                        sample_size=score_data["sample_size"],
                        positive_count=score_data["positive_count"],
                        negative_count=score_data["negative_count"],
                        review_score_desc=score_data["review_score_desc"],
                        scraped_at=score_data["scraped_at"],
                    )
                )
                game.steam_user_score = score_data["score"]
                game.steam_sample_size = score_data["sample_size"]

            activity_result = await sync_game_steam_public_activity(
                db,
                game,
                activity_service,
            )
            await sync_game_source_taxonomy(
                db,
                game,
                source="steam",
                source_labels=extract_steam_source_labels(app_details),
            )
            peak_result = await sync_game_steamdb_peaks(
                game,
                activity_service,
            )

            await db.commit()

            print(action)
            print(f"  Title: {game.title}")
            print(f"  Public ID: {game.public_id}")
            print(f"  Steam app ID: {game.steam_app_id}")
            if game.release_date is not None:
                print(f"  Release date: {game.release_date.isoformat()}")
            if game.steam_user_score is not None:
                print(
                    "  Steam user score: "
                    f"{game.steam_user_score} ({game.steam_sample_size or 0} reviews)"
                )
            if activity_result["current_players"] is not None:
                print(f"  Current players: {activity_result['current_players']:,}")
            if peak_result.get("steam_player_24h_peak") is not None:
                print(f"  24h peak: {peak_result['steam_player_24h_peak']:,}")
            if peak_result.get("steam_player_all_time_peak") is not None:
                print(f"  All-time peak: {peak_result['steam_player_all_time_peak']:,}")

    return 0


async def cmd_metacritic(args):
    """Handle Metacritic sync command."""
    import asyncio
    import time
    from app.services.game_taxonomy import (
        extract_metacritic_source_labels,
        sync_game_source_taxonomy,
    )
    from app.services.game_taxonomy_v2 import (
        apply_metacritic_description,
        refresh_game_taxonomy_v2_text,
    )
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty
    from app.services.metacritic import MetacriticService
    from app.models.models import Game, UserScore, UserScoreSource, Review
    from sqlalchemy import select, func, delete, or_, and_, case
    from datetime import timedelta, date as date_type

    min_recent_add_window_days = 14
    recent_opencritic_id_window = 300

    async with async_session_maker() as db:
        # Handle --status flag
        if args.status:
            # Count total games with metacritic_slug
            total_result = await db.execute(
                select(func.count()).select_from(Game).where(Game.metacritic_slug.isnot(None))
            )
            total_with_slug = total_result.scalar() or 0

            # Count games with metascore synced
            synced_result = await db.execute(
                select(func.count()).select_from(Game).where(
                    Game.metacritic_slug.isnot(None),
                    Game.metacritic_score.isnot(None)
                )
            )
            synced_metascore = synced_result.scalar() or 0

            # Count user scores from Metacritic
            user_scores_result = await db.execute(
                select(func.count()).select_from(UserScore).where(
                    UserScore.source == UserScoreSource.METACRITIC
                )
            )
            user_scores_count = user_scores_result.scalar() or 0

            remaining = total_with_slug - synced_metascore
            pct = (synced_metascore / total_with_slug * 100) if total_with_slug > 0 else 0

            print("\n=== Metacritic Sync Status ===")
            print(f"Games with Metacritic slug: {total_with_slug:,}")
            print(f"Games with Metascore synced: {synced_metascore:,} ({pct:.1f}%)")
            print(f"Games remaining to sync: {remaining:,}")
            print(f"User scores collected: {user_scores_count:,}")
            return

        now = datetime.now(timezone.utc)
        today = now.date()

        # Missing-data condition (used by targeted modes only).
        needs_sync_condition = or_(
            Game.metacritic_score.is_(None),
            Game.metacritic_user_score.is_(None),
        )
        max_opencritic_id_subq = select(func.max(Game.opencritic_id)).scalar_subquery()
        recent_opencritic_condition = and_(
            Game.opencritic_id.isnot(None),
            Game.opencritic_id >= (max_opencritic_id_subq - recent_opencritic_id_window),
        )
        published_review_game_ids = (
            select(Review.game_id)
            .where(
                Review.score_normalized.isnot(None),
                Review.published_at.isnot(None),
                Review.published_at <= now,
            )
            .distinct()
            .scalar_subquery()
        )
        release_date_reconcile_condition = and_(
            or_(Game.release_date.is_(None), Game.release_date > today),
            Game.id.in_(published_review_game_ids),
        )
        recent_review_window_days = max(
            args.recent or 0,
            args.new_only or 0,
            min_recent_add_window_days,
        )
        recent_review_cutoff_dt = now - timedelta(days=recent_review_window_days)
        recent_review_game_ids = (
            select(Review.game_id)
            .where(
                Review.score_normalized.isnot(None),
                Review.published_at.isnot(None),
                Review.published_at >= recent_review_cutoff_dt,
                Review.published_at <= now,
            )
            .distinct()
            .scalar_subquery()
        )
        recent_review_activity_condition = Game.id.in_(recent_review_game_ids)

        # Get games with Metacritic slugs
        if args.backfill_counts:
            # Only re-scrape games missing metacritic_sample_size
            query = select(Game).where(
                Game.metacritic_slug.isnot(None),
                Game.metacritic_user_score.isnot(None),
                Game.metacritic_sample_size.is_(None),
            )
            if args.recent is not None:
                days = args.recent
                cutoff_date = date_type.today() - timedelta(days=days)
                query = query.where(
                    Game.release_date.isnot(None),
                    Game.release_date >= cutoff_date,
                )
                mode = f'missing sample size (released in last {days} days)'
            else:
                mode = 'missing sample size'
        elif args.force:
            # Re-sync all games
            query = select(Game).where(Game.metacritic_slug.isnot(None))
            mode = 'total'
        elif args.recent is not None:
            # Process all recent games so score/sample changes are refreshed,
            # not only games missing initial Metacritic data.
            days = args.recent
            cutoff_date = (now - timedelta(days=days)).date()
            created_cutoff_date = (now - timedelta(days=min_recent_add_window_days)).date()
            created_cutoff_dt = datetime.combine(
                created_cutoff_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            query = select(Game).where(
                Game.metacritic_slug.isnot(None),
                or_(
                    and_(
                        Game.release_date.isnot(None),
                        Game.release_date >= cutoff_date,
                    ),
                    Game.created_at >= created_cutoff_dt,
                    recent_opencritic_condition,
                    release_date_reconcile_condition,
                    recent_review_activity_condition,
                ),
            )
            mode = (
                f'recent-window refresh (released in last {days} days, or added in last '
                f'{min_recent_add_window_days} days, or in recent OpenCritic ID window, '
                f'or release-date reconciliation needed, or with scored reviews in last '
                f'{recent_review_window_days} days)'
            )
        elif args.new_only is not None:
            # Only process recently released games that have never been synced from Metacritic
            days = args.new_only
            cutoff_date = (now - timedelta(days=days)).date()
            created_cutoff_date = (now - timedelta(days=min_recent_add_window_days)).date()
            created_cutoff_dt = datetime.combine(
                created_cutoff_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            query = select(Game).where(
                Game.metacritic_slug.isnot(None),
                Game.metacritic_synced_at.is_(None),
                or_(
                    and_(
                        Game.release_date.isnot(None),
                        Game.release_date >= cutoff_date,
                    ),
                    Game.created_at >= created_cutoff_dt,
                    recent_opencritic_condition,
                ),
            )
            mode = (
                f'new (released in last {days} days, or added in last '
                f'{min_recent_add_window_days} days, or in recent OpenCritic ID window, never synced)'
            )
        else:
            # Refresh all games with Metacritic slugs, with stale-days gating.
            query = select(Game).where(
                Game.metacritic_slug.isnot(None),
            )

            # Apply stale-days filter: skip games synced recently
            stale_days = args.stale_days
            if stale_days > 0:
                stale_cutoff = now - timedelta(days=stale_days)
                query = query.where(
                    or_(
                        release_date_reconcile_condition,
                        Game.metacritic_synced_at.is_(None),
                        Game.metacritic_synced_at < stale_cutoff,
                    )
                )

            mode = 'stale/refresh'
        if args.title:
            query = query.where(Game.title.ilike(f"%{args.title}%"))
            mode = f"{mode}, title contains '{args.title}'"
        release_reconcile_priority = case(
            (or_(release_date_reconcile_condition, recent_review_activity_condition), 0),
            else_=1,
        )
        if args.recent is not None:
            query = query.order_by(
                release_reconcile_priority.asc(),
                Game.created_at.desc().nulls_last(),
                Game.release_date.desc().nulls_last(),
                Game.id.desc(),
            )
        elif args.new_only is not None:
            query = query.order_by(
                Game.created_at.desc().nulls_last(),
                Game.release_date.desc().nulls_last(),
                Game.id.desc(),
            )
        else:
            query = query.order_by(
                release_reconcile_priority.asc(),
                Game.metacritic_synced_at.asc().nulls_first(),
                Game.created_at.desc().nulls_last(),
                Game.id.desc(),
            )
        if args.limit:
            query = query.limit(args.limit)
        result = await db.execute(query)
        games = result.scalars().all()
        print(f"Found {len(games)} games {mode} Metacritic sync")

        if args.limit:
            print(f"Processing up to {args.limit} games")

        synced_user = 0
        synced_meta = 0
        skipped = 0
        failed = 0
        processed = 0
        total_games = len(games)
        per_game_timeout_seconds = 120

        async with MetacriticService() as service:
            for index, game in enumerate(games, start=1):
                started_at = time.monotonic()
                try:
                    print(f"[{index}/{total_games}] Fetching Metacritic scores for: {game.title}...")

                    score_data = await asyncio.wait_for(
                        service.get_scores(game.metacritic_slug, title=game.title),
                        timeout=per_game_timeout_seconds,
                    )

                    if not score_data:
                        print(f"  No data returned from Metacritic")

                    if score_data:
                        await sync_game_source_taxonomy(
                            db,
                            game,
                            source="metacritic",
                            source_labels=extract_metacritic_source_labels(score_data),
                        )
                        updated_anything = False
                        resolved_slug = score_data.get("resolved_slug")
                        if resolved_slug and resolved_slug != game.metacritic_slug:
                            print(f"  Slug resolved: {game.metacritic_slug} -> {resolved_slug}")
                            game.metacritic_slug = resolved_slug
                            updated_anything = True
                            mark_game_similarity_v3_dirty(game, "source_identifier_metacritic")
                        if apply_metacritic_description(game, score_data.get("description")):
                            refresh_game_taxonomy_v2_text(game)
                            updated_anything = True
                            mark_game_similarity_v3_dirty(game, "source_text_metacritic")

                        # Check and update user score/sample size only if changed
                        if score_data.get("user_score") is not None:
                            # Get existing user score for this game
                            existing_score_result = await db.execute(
                                select(UserScore).where(
                                    UserScore.game_id == game.id,
                                    UserScore.source == UserScoreSource.METACRITIC
                                ).order_by(UserScore.scraped_at.desc()).limit(1)
                            )
                            existing_score = existing_score_result.scalar_one_or_none()

                            score_changed = (
                                existing_score is None or existing_score.score != score_data["user_score"]
                            )
                            sample_size_changed = (
                                existing_score is None or existing_score.sample_size != score_data["user_sample_size"]
                            )
                            if score_changed or sample_size_changed:
                                user_score = UserScore(
                                    game_id=game.id,
                                    source=UserScoreSource.METACRITIC,
                                    score=score_data["user_score"],
                                    score_raw=score_data["user_score_raw"],
                                    sample_size=score_data["user_sample_size"],
                                    positive_count=None,
                                    negative_count=None,
                                    review_score_desc=None,
                                    scraped_at=score_data["scraped_at"],
                                )
                                db.add(user_score)
                                synced_user += 1
                                updated_anything = True
                                old_score = existing_score.score if existing_score else "None"
                                old_size = existing_score.sample_size if existing_score else "None"
                                print(
                                    "  User Score/Sample: "
                                    f"{old_score} ({old_size}) -> "
                                    f"{score_data['user_score']} ({score_data['user_sample_size']})"
                                )
                            else:
                                print(
                                    f"  User Score/Sample: {score_data['user_score']} "
                                    f"({score_data['user_sample_size']}) (unchanged)"
                                )

                            # Update denormalized columns on Game
                            previous_user = game.metacritic_user_score
                            previous_size = game.metacritic_sample_size
                            game.metacritic_user_score = score_data["user_score"]
                            game.metacritic_sample_size = score_data["user_sample_size"]
                            if previous_user != game.metacritic_user_score or previous_size != game.metacritic_sample_size:
                                updated_anything = True
                            if score_data["user_sample_size"] is not None:
                                print(f"  Sample Size: {score_data['user_sample_size']}")
                        else:
                            # User score is N/A - delete any existing invalid scores for this game
                            delete_result = await db.execute(
                                delete(UserScore).where(
                                    UserScore.game_id == game.id,
                                    UserScore.source == UserScoreSource.METACRITIC,
                                )
                            )
                            if delete_result.rowcount > 0:
                                print(f"  User Score: Deleted {delete_result.rowcount} invalid score(s) (now N/A)")
                                updated_anything = True

                            # Clear denormalized columns
                            game.metacritic_user_score = None
                            game.metacritic_sample_size = None

                        # Check and update metascore only if changed
                        if score_data.get("metascore") is not None:
                            if game.metacritic_score != score_data["metascore"]:
                                old_val = game.metacritic_score
                                game.metacritic_score = score_data["metascore"]
                                synced_meta += 1
                                updated_anything = True
                                print(f"  Metascore: {old_val} -> {score_data['metascore']}")
                            else:
                                print(f"  Metascore: {score_data['metascore']} (unchanged)")

                        # Fill missing/placeholder release_date from Metacritic when available.
                        mc_release_date = score_data.get("release_date")
                        if mc_release_date is not None:
                            today = datetime.now(timezone.utc).date()
                            should_update_release_date = (
                                _should_update_release_date_from_metacritic(
                                    game.release_date,
                                    mc_release_date,
                                    today=today,
                                )
                            )
                            if should_update_release_date and game.release_date != mc_release_date:
                                old_release = game.release_date
                                game.release_date = mc_release_date
                                updated_anything = True
                                print(f"  Release Date: {old_release} -> {mc_release_date}")

                        if not updated_anything:
                            skipped += 1

                    # Mark this game as synced regardless of whether data changed
                    game.metacritic_synced_at = datetime.now(timezone.utc)

                    # Small delay to be respectful
                    await asyncio.sleep(1)

                    elapsed = time.monotonic() - started_at
                    print(f"  Completed in {elapsed:.1f}s")
                except asyncio.TimeoutError:
                    elapsed = time.monotonic() - started_at
                    print(
                        f"  Error: timed out after {elapsed:.1f}s "
                        f"(limit {per_game_timeout_seconds}s)"
                    )
                    failed += 1
                except Exception as e:
                    print(f"  Error: {e}")
                    failed += 1
                finally:
                    # Commit progress in chunks so long runs do not appear stalled.
                    processed += 1
                    if processed % 10 == 0 or processed == total_games:
                        await db.commit()
                        print(
                            f"Progress: {processed}/{total_games} processed "
                            f"({synced_user} user, {synced_meta} metascore, "
                            f"{skipped} unchanged, {failed} failed)"
                        )

        await db.commit()
        print(f"\nMetacritic sync complete: {synced_user} user scores updated, {synced_meta} metascores updated, {skipped} unchanged, {failed} failed")


async def cmd_taxonomy_backfill(args):
    """Refresh stored source taxonomy labels and canonical game taxonomy."""
    from sqlalchemy import select, or_

    from app.models.models import Game
    from app.public_ids import resolve_entity_by_identifier
    from app.services.game_taxonomy import (
        extract_metacritic_source_labels,
        extract_opencritic_source_labels,
        extract_steam_source_labels,
        rebuild_game_taxonomy,
        sync_game_source_taxonomy,
    )
    from app.services.game_taxonomy_v2 import (
        apply_metacritic_description,
        apply_opencritic_description,
        apply_steam_descriptions,
        refresh_game_taxonomy_v2_text,
    )
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty
    from app.services.metacritic import MetacriticService
    from app.services.opencritic import OpenCriticService
    from app.services.steam import SteamService

    async with async_session_maker() as db:
        if args.game:
            game = await _resolve_target_game_with_title_fallback(db, Game, str(args.game))
            games = [game] if game else []
        else:
            query = select(Game).where(
                or_(
                    Game.opencritic_id.isnot(None),
                    Game.steam_app_id.isnot(None),
                    Game.metacritic_slug.isnot(None),
                )
            ).order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
            if args.limit:
                query = query.limit(args.limit)
            result = await db.execute(query)
            games = result.scalars().all()

        if not games:
            print("No games found for taxonomy backfill.")
            return 1

        opencritic_service = OpenCriticService()
        processed = 0
        updated = 0

        async with SteamService() as steam_service, MetacriticService() as metacritic_service:
            for game in games:
                if game is None:
                    continue
                print(f"Backfilling taxonomy for: {game.title}")
                touched = False

                if args.source in (None, "opencritic") and game.opencritic_id is not None:
                    game_data = await opencritic_service.get_game(game.opencritic_id)
                    if game_data:
                        if apply_opencritic_description(game, game_data.get("description")):
                            mark_game_similarity_v3_dirty(game, "source_text_opencritic")
                        touched = (
                            await sync_game_source_taxonomy(
                                db,
                                game,
                                source="opencritic",
                                source_labels=extract_opencritic_source_labels(game_data),
                            )
                            or touched
                        )

                if args.source in (None, "steam") and game.steam_app_id is not None:
                    app_details = await steam_service.get_app_details(game.steam_app_id)
                    if app_details:
                        transformed = SteamService.transform_app_details(app_details, game.steam_app_id)
                        if apply_steam_descriptions(
                            game,
                            short_description=transformed.get("steam_short_description"),
                            detailed_description=transformed.get("steam_detailed_description"),
                        ):
                            mark_game_similarity_v3_dirty(game, "source_text_steam")
                        store_tags = await steam_service.get_store_tags(game.steam_app_id)
                        if store_tags:
                            app_details = {**app_details, "store_tags": store_tags}
                        touched = (
                            await sync_game_source_taxonomy(
                                db,
                                game,
                                source="steam",
                                source_labels=extract_steam_source_labels(app_details),
                            )
                            or touched
                        )

                if args.source in (None, "metacritic") and game.metacritic_slug:
                    score_data = await metacritic_service.get_scores(
                        game.metacritic_slug,
                        title=game.title,
                    )
                    if score_data:
                        if apply_metacritic_description(game, score_data.get("description")):
                            mark_game_similarity_v3_dirty(game, "source_text_metacritic")
                        touched = (
                            await sync_game_source_taxonomy(
                                db,
                                game,
                                source="metacritic",
                                source_labels=extract_metacritic_source_labels(score_data),
                            )
                            or touched
                        )

                if not touched:
                    await rebuild_game_taxonomy(db, game)
                refresh_game_taxonomy_v2_text(game)

                processed += 1
                if touched:
                    updated += 1
                if processed % 10 == 0 or processed == len(games):
                    await db.commit()
                    print(f"  Progress: {processed}/{len(games)}")

        await db.commit()
        print(f"Taxonomy backfill complete: {updated} updated, {processed} processed")
    return 0


async def cmd_description_backfill(args):
    """Fetch and store source-specific narrative descriptions for taxonomy V2 text enrichment."""
    from contextlib import AsyncExitStack
    from sqlalchemy import or_, select

    from app.models.models import Game
    from app.public_ids import resolve_entity_by_identifier
    from app.services.game_taxonomy_v2 import (
        apply_metacritic_description,
        apply_opencritic_description,
        apply_steam_descriptions,
        refresh_game_taxonomy_v2_text,
    )
    from app.services.game_similarity_v3 import mark_game_similarity_v3_dirty
    from app.services.metacritic import MetacriticService
    from app.services.opencritic import OpenCriticService
    from app.services.steam import SteamService

    async with async_session_maker() as db:
        if args.game:
            game = await _resolve_target_game_with_title_fallback(db, Game, str(args.game))
            games = [game] if game else []
        else:
            query = (
                select(Game)
                .where(
                    or_(
                        Game.opencritic_id.isnot(None),
                        Game.steam_app_id.isnot(None),
                        Game.metacritic_slug.isnot(None),
                    )
                )
                .order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
            )
            if args.limit:
                query = query.limit(args.limit)
            result = await db.execute(query)
            games = result.scalars().all()

        if not games:
            print("No games found for description backfill.")
            return 1

        use_opencritic = args.source in (None, "opencritic")
        use_steam = args.source in (None, "steam")
        use_metacritic = args.source in (None, "metacritic")

        opencritic_service = OpenCriticService() if use_opencritic else None
        processed = 0
        updated = 0

        async with AsyncExitStack() as stack:
            steam_service = await stack.enter_async_context(SteamService()) if use_steam else None
            metacritic_service = (
                await stack.enter_async_context(MetacriticService()) if use_metacritic else None
            )
            for game in games:
                if game is None:
                    continue
                print(f"Backfilling descriptions for: {game.title}")
                changed = False

                if opencritic_service and game.opencritic_id is not None:
                    game_data = await opencritic_service.get_game(game.opencritic_id)
                    if game_data:
                        source_changed = apply_opencritic_description(game, game_data.get("description"))
                        if source_changed:
                            mark_game_similarity_v3_dirty(game, "source_text_opencritic")
                        changed = source_changed or changed

                if steam_service and game.steam_app_id is not None:
                    app_details = await steam_service.get_app_details(game.steam_app_id)
                    if app_details:
                        transformed = SteamService.transform_app_details(app_details, game.steam_app_id)
                        source_changed = apply_steam_descriptions(
                                game,
                                short_description=transformed.get("steam_short_description"),
                                detailed_description=transformed.get("steam_detailed_description"),
                        )
                        if source_changed:
                            mark_game_similarity_v3_dirty(game, "source_text_steam")
                        changed = source_changed or changed

                if metacritic_service and game.metacritic_slug:
                    score_data = await metacritic_service.get_scores(
                        game.metacritic_slug,
                        title=game.title,
                    )
                    if score_data:
                        source_changed = apply_metacritic_description(game, score_data.get("description"))
                        if source_changed:
                            mark_game_similarity_v3_dirty(game, "source_text_metacritic")
                        changed = source_changed or changed

                previous_corpus = getattr(game, "taxonomy_v2_text_corpus", None)
                previous_sources = list(getattr(game, "taxonomy_v2_text_sources", None) or [])
                corpus, sources = refresh_game_taxonomy_v2_text(game)
                if corpus != previous_corpus or sources != previous_sources:
                    changed = True
                    mark_game_similarity_v3_dirty(game, "source_text_corpus")

                processed += 1
                if changed:
                    updated += 1
                if processed % 10 == 0 or processed == len(games):
                    await db.commit()
                    print(f"  Progress: {processed}/{len(games)}")

        await db.commit()
        print(f"Description backfill complete: {updated} updated, {processed} processed")
    return 0


async def cmd_taxonomy_audit(args):
    """Show raw source labels that do not map to canonical taxonomy."""
    from collections import defaultdict
    from sqlalchemy import select

    from app.models.models import GameSourceTaxonomyLabel
    from app.services.game_taxonomy import raw_label_is_mapped

    async with async_session_maker() as db:
        query = select(GameSourceTaxonomyLabel)
        if args.source:
            query = query.where(GameSourceTaxonomyLabel.source == args.source)
        result = await db.execute(query)
        rows = result.scalars().all()

        unmapped: dict[tuple[str, str, str], dict[str, object]] = defaultdict(
            lambda: {"count": 0, "sample": ""}
        )
        for row in rows:
            if raw_label_is_mapped(row.source, row.facet, row.raw_label):
                continue
            key = (row.source, row.facet, row.normalized_label)
            unmapped[key]["count"] = int(unmapped[key]["count"]) + 1
            unmapped[key]["sample"] = row.raw_label

        if not unmapped:
            print("All stored taxonomy labels map to canonical facets.")
            return 0

        print("Unmapped taxonomy labels:")
        ranked = sorted(
            unmapped.items(),
            key=lambda item: (-int(item[1]["count"]), item[0][0], item[0][1], item[0][2]),
        )
        for index, ((source, facet, normalized), info) in enumerate(ranked[: args.limit or 50], start=1):
            print(
                f"{index:>3}. {source}/{facet}: {normalized} "
                f"(games={info['count']}, sample='{info['sample']}')"
            )
    return 0


async def cmd_similar_debug(args):
    """Explain current taxonomy support and top strict similar-game matches."""
    from sqlalchemy import select, and_, or_

    from app.models.models import Game
    from app.public_ids import resolve_entity_by_identifier
    from app.services.game_taxonomy import (
        build_game_taxonomy_sets,
        build_similarity_breakdown,
        game_has_curated_override,
        game_has_sufficient_taxonomy_support,
    )

    async with async_session_maker() as db:
        game = await _resolve_target_game_with_title_fallback(db, Game, str(args.game))
        if not game:
            print("Game not found.")
            return 1

        taxonomy = build_game_taxonomy_sets(game)
        print(f"Game: {game.title}")
        print(f"  Sources: {', '.join(game.taxonomy_sources or []) or 'none'}")
        print(f"  Curated override: {'yes' if game_has_curated_override(game) else 'no'}")
        print(f"  Genres: {', '.join(sorted(taxonomy['genres'])) or 'none'}")
        print(f"  Themes: {', '.join(sorted(taxonomy['themes'])) or 'none'}")
        print(f"  Modes: {', '.join(sorted(taxonomy['modes'])) or 'none'}")
        print(f"  Perspectives: {', '.join(sorted(taxonomy['perspectives'])) or 'none'}")

        if not game_has_sufficient_taxonomy_support(game):
            print("  Fails support gate: requires at least 2 taxonomy sources or a curated override.")
            return 0
        if not taxonomy["genres"]:
            print("  Fails similarity gate: no canonical genres.")
            return 0
        if not (taxonomy["themes"] or taxonomy["modes"] or taxonomy["perspectives"]):
            print("  Fails similarity gate: no secondary gameplay facets (theme/mode/perspective).")
            return 0

        secondary_overlap_clauses = []
        if game.taxonomy_themes:
            secondary_overlap_clauses.append(Game.taxonomy_themes.overlap(list(game.taxonomy_themes)))
        if game.taxonomy_modes:
            secondary_overlap_clauses.append(Game.taxonomy_modes.overlap(list(game.taxonomy_modes)))
        if game.taxonomy_perspectives:
            secondary_overlap_clauses.append(Game.taxonomy_perspectives.overlap(list(game.taxonomy_perspectives)))

        query = (
            select(Game)
            .where(
                Game.id != game.id,
                Game.release_date.isnot(None),
                Game.release_date <= datetime.now(timezone.utc).date(),
                Game.taxonomy_genres.overlap(list(game.taxonomy_genres or [])),
                or_(*secondary_overlap_clauses),
                or_(
                    Game.steam_sample_size >= 50,
                    and_(
                        Game.metacritic_user_score.isnot(None),
                        or_(Game.metacritic_sample_size.is_(None), Game.metacritic_sample_size >= 20),
                    ),
                    Game.critic_review_count >= 5,
                ),
            )
            .limit(args.limit or 10)
        )
        result = await db.execute(query)
        candidates = result.scalars().all()
        if not candidates:
            print("  No candidate games passed the coarse query.")
            return 0

        ranked: list[tuple[int, str, list[str]]] = []
        for candidate in candidates:
            breakdown = build_similarity_breakdown(game, candidate)
            if breakdown is None:
                continue
            ranked.append((breakdown.score, candidate.title, breakdown.match_reasons))

        if not ranked:
            print("  Candidates exist, but none passed strict similarity rules.")
            return 0

        ranked.sort(key=lambda item: (-item[0], item[1].lower()))
        print("Top strict matches:")
        for index, (score, title, reasons) in enumerate(ranked[: args.limit or 10], start=1):
            print(f"{index:>3}. {title} (score={score})")
            for reason in reasons:
                print(f"     - {reason}")
    return 0


async def cmd_taxonomy_v2_backfill(args):
    """Compute and store Similar Games Taxonomy V2 fingerprints."""
    from sqlalchemy import func, or_, select

    from app.models.models import Game
    from app.public_ids import resolve_entity_by_identifier
    from app.services.game_taxonomy_v2 import (
        TAXONOMY_V2_STATUS_COMPUTED,
        TAXONOMY_V2_STATUS_CURATED,
        TAXONOMY_V2_STATUS_HIDDEN,
        compute_and_store_game_taxonomy_v2,
    )

    async with async_session_maker() as db:
        if args.game:
            game = await _resolve_target_game_with_title_fallback(db, Game, str(args.game))
            games = [game] if game else []
        else:
            query = (
                select(Game)
                .where(
                    or_(
                        Game.description.isnot(None),
                        Game.opencritic_description.isnot(None),
                        Game.steam_short_description.isnot(None),
                        Game.steam_detailed_description.isnot(None),
                        Game.metacritic_description.isnot(None),
                        Game.taxonomy_v2_text_corpus.isnot(None),
                        Game.opencritic_id.isnot(None),
                        Game.steam_app_id.isnot(None),
                        Game.metacritic_slug.isnot(None),
                    )
                )
                .order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
            )
            if args.limit:
                query = query.limit(args.limit)
            result = await db.execute(query)
            games = result.scalars().all()

        if not games:
            print("No games found for taxonomy V2 backfill.")
            return 1

        processed = 0
        computed = 0
        curated = 0
        hidden = 0
        hidden_reasons: dict[str, int] = {}

        for game in games:
            if game is None:
                continue
            print(f"Backfilling taxonomy V2 for: {game.title}")
            result = await compute_and_store_game_taxonomy_v2(db, game)
            processed += 1
            if result.status == TAXONOMY_V2_STATUS_COMPUTED:
                computed += 1
            elif result.status == TAXONOMY_V2_STATUS_CURATED:
                curated += 1
            elif result.status == TAXONOMY_V2_STATUS_HIDDEN:
                hidden += 1
                audit_state = str(result.debug_payload.get("audit_state") or "unknown")
                hidden_reasons[audit_state] = hidden_reasons.get(audit_state, 0) + 1
            if processed % 25 == 0 or processed == len(games):
                await db.commit()
                print(
                    f"  Progress: {processed}/{len(games)} "
                    f"(computed={computed}, curated={curated}, hidden={hidden})"
                )

        await db.commit()
        hidden_summary = ", ".join(
            f"{reason}={count}"
            for reason, count in sorted(hidden_reasons.items(), key=lambda item: (-item[1], item[0]))
        ) or "none"
        print(
            "Taxonomy V2 backfill complete: "
            f"{processed} processed, {computed} computed, {curated} curated, "
            f"{hidden} hidden"
        )
        print(f"Hidden audit states: {hidden_summary}")
    return 0


async def cmd_taxonomy_v2_debug(args):
    """Explain the computed Similar Games Taxonomy V2 fingerprint for a game."""
    from app.models.models import Game
    from app.services.game_taxonomy_v2 import (
        build_similarity_breakdown_v2,
        compute_game_taxonomy_v2,
        display_taxonomy_v2_token,
        store_game_taxonomy_v2,
    )

    def _clone_game_for_breakdown(source: Game, result) -> Game:
        return Game(
            id=source.id,
            public_id=source.public_id,
            title=source.title,
            release_date=source.release_date,
            taxonomy_studios=list(getattr(source, "taxonomy_studios", None) or []),
            taxonomy_v2_status=result.status,
            taxonomy_v2_primary_family=result.primary_family,
            taxonomy_v2_primary_archetype=result.primary_archetype,
            taxonomy_v2_secondary_archetypes=list(result.secondary_archetypes or []),
            taxonomy_v2_hard_exclusions=list(result.hard_exclusions or []),
            taxonomy_v2_soft_penalties=list(result.soft_penalties or []),
            taxonomy_v2_fingerprint={key: list(values) for key, values in (result.fingerprint or {}).items()},
        )

    def _print_breakdown(label: str, breakdown) -> None:
        print(f"  {label}:")
        if breakdown is None:
            print("    none")
            return
        print(f"    relationship: {breakdown.relationship}")
        print(f"    score: {breakdown.score}")
        print(f"    confidence: {breakdown.confidence}")
        reasons = list(getattr(breakdown, "match_reasons", None) or [])
        if reasons:
            print(f"    reasons: {', '.join(reasons)}")
        else:
            print("    reasons: none")

    def _print_compact_result(label: str, result_like) -> None:
        status = getattr(result_like, "status", None)
        if status is None:
            status = getattr(result_like, "taxonomy_v2_status", None)
        primary_archetype = getattr(result_like, "primary_archetype", None)
        if primary_archetype is None:
            primary_archetype = getattr(result_like, "taxonomy_v2_primary_archetype", None)
        secondary_archetypes = getattr(result_like, "secondary_archetypes", None)
        if secondary_archetypes is None:
            secondary_archetypes = getattr(result_like, "taxonomy_v2_secondary_archetypes", None) or []
        hard_exclusions = getattr(result_like, "hard_exclusions", None)
        if hard_exclusions is None:
            hard_exclusions = getattr(result_like, "taxonomy_v2_hard_exclusions", None) or []
        fingerprint = getattr(result_like, "fingerprint", None)
        if fingerprint is None:
            fingerprint = getattr(result_like, "taxonomy_v2_fingerprint", None) or {}
        print(f"  {label}:")
        print(f"    status: {status or 'none'}")
        print(f"    primary archetype: {primary_archetype or 'none'}")
        print(f"    secondary archetypes: {', '.join(secondary_archetypes) or 'none'}")
        print(
            "    hard exclusions: "
            + (", ".join(display_taxonomy_v2_token(value) for value in hard_exclusions) or "none")
        )
        interesting_axes = ("world_topology", "perspective", "combat_style", "combat_structure", "traversal_verbs", "progression_model", "challenge_model", "setting", "rules_goals", "entity_interaction")
        for axis in interesting_axes:
            values = fingerprint.get(axis, [])
            if not values:
                continue
            rendered = ", ".join(display_taxonomy_v2_token(value) for value in values)
            print(f"    {axis}: {rendered}")

    def _print_source_snippets(label: str, game_like) -> None:
        snippet_fields = (
            ("generic", getattr(game_like, "description", None)),
            ("opencritic", getattr(game_like, "opencritic_description", None)),
            ("steam_short", getattr(game_like, "steam_short_description", None)),
            ("steam_detailed", getattr(game_like, "steam_detailed_description", None)),
            ("metacritic", getattr(game_like, "metacritic_description", None)),
        )
        printed = False
        print(f"  {label}:")
        for source_name, value in snippet_fields:
            if not value:
                continue
            printed = True
            print(f"    {source_name}: {_truncate_cli_text(str(value).replace(chr(10), ' '), limit=240)}")
        if not printed:
            print("    none")

    def _print_provenance(label: str, result_like, fingerprint_like) -> None:
        debug_payload = getattr(result_like, "debug_payload", None)
        if debug_payload is None:
            debug_payload = getattr(result_like, "taxonomy_v2_debug_payload", None) or {}
        provenance = debug_payload.get("provenance_by_field_value", {}) if isinstance(debug_payload, dict) else {}
        if not provenance:
            print(f"  {label}: none")
            return
        interesting_axes = (
            "world_topology",
            "perspective",
            "combat_style",
            "combat_structure",
            "traversal_verbs",
            "progression_model",
            "challenge_model",
            "setting",
            "rules_goals",
            "entity_interaction",
        )
        printed = False
        print(f"  {label}:")
        for axis in interesting_axes:
            values = (fingerprint_like or {}).get(axis, [])
            if not values:
                continue
            for value in values:
                providers = provenance.get(axis, {}).get(value, [])
                if not providers:
                    continue
                printed = True
                print(f"    {axis}={value}: {', '.join(providers)}")
        if not printed:
            print("    none")

    async with async_session_maker() as db:
        game = await _resolve_target_game_with_title_fallback(db, Game, str(args.game))
        if not game:
            print("Game not found.")
            return 1

        result = await compute_game_taxonomy_v2(db, game)
        if args.persist:
            await store_game_taxonomy_v2(db, game, result)
            await db.commit()

        print(f"Game: {game.title}")
        print(f"  Status: {result.status}")
        if result.status == "hidden":
            print(f"  Audit state: {result.debug_payload.get('audit_state', 'unknown')}")
        print(f"  Version: {result.version}")
        print(f"  Primary family: {result.primary_family or 'none'}")
        print(f"  Primary archetype: {result.primary_archetype or 'none'}")
        print(f"  Secondary archetypes: {', '.join(result.secondary_archetypes) or 'none'}")
        print(f"  Confidence: {result.confidence:.2f}" if result.confidence is not None else "  Confidence: none")
        print(f"  Curated override: {'yes' if result.curated else 'no'}")
        text_sources = result.debug_payload.get("text_sources", [])
        print(f"  Text sources: {', '.join(text_sources) or 'none'}")
        print(f"  Text length: {result.debug_payload.get('text_length', 0)}")
        matrix_versions = result.debug_payload.get("matrix_versions", {})
        if matrix_versions:
            print(
                "  Matrix versions: "
                + ", ".join(f"{key}={value}" for key, value in matrix_versions.items() if value)
            )

        interesting_axes = (
            "world_topology",
            "world_density",
            "session_shape",
            "perspective",
            "combat_presence",
            "combat_style",
            "combat_tempo",
            "combat_structure",
            "traversal_verbs",
            "progression_model",
            "challenge_model",
            "narrative_structure",
            "setting",
            "tone",
            "mode_profile",
            "content_model",
            "input_complexity",
        )
        print("  Fingerprint:")
        for axis in interesting_axes:
            values = result.fingerprint.get(axis, [])
            if not values:
                continue
            rendered = ", ".join(display_taxonomy_v2_token(value) for value in values)
            print(f"    {axis}: {rendered}")
        print(
            "    hard_exclusions: "
            f"{', '.join(display_taxonomy_v2_token(value) for value in result.hard_exclusions) or 'none'}"
        )
        print(
            "    soft_penalties: "
            f"{', '.join(display_taxonomy_v2_token(value) for value in result.soft_penalties) or 'none'}"
        )

        candidates = result.debug_payload.get("candidate_archetypes", [])
        if candidates:
            print("  Top archetype candidates:")
            for index, candidate in enumerate(candidates[: args.limit or 5], start=1):
                print(
                    f"    {index}. {candidate['archetype']} "
                    f"(score={candidate['score']}, required={candidate['required_hits']}/{candidate['required_total']}, "
                    f"preferred={candidate['preferred_hits']}/{candidate['preferred_total']}, "
                    f"confidence={candidate['confidence']})"
                )
        else:
            print("  Top archetype candidates: none")

        near_misses = result.debug_payload.get("near_misses", [])
        if near_misses:
            print("  Near misses:")
            for index, near_miss in enumerate(near_misses[: args.limit or 5], start=1):
                missing = ", ".join(
                    display_taxonomy_v2_token(value)
                    for value in near_miss.get("missing_required_axes", [])
                ) or "none"
                print(
                    f"    {index}. {near_miss['archetype']} "
                    f"(required={near_miss['required_hits']}/{near_miss['required_total']}, missing={missing})"
                )

        if result.evidence:
            print("  Evidence:")
            ranked_evidence = sorted(
                result.evidence,
                key=lambda item: (-item.confidence, item.field, item.value, item.source),
            )
            for record in ranked_evidence[: args.evidence_limit]:
                note = f" ({record.evidence_text})" if record.evidence_text else ""
                print(
                    f"    - {record.field}={record.value} "
                    f"[{record.source}/{record.source_field}, confidence={record.confidence:.2f}]{note}"
                )
        else:
            print("  Evidence: none")
        _print_provenance("Provenance", result, result.fingerprint)
        _print_source_snippets("Source snippets", game)

        if args.compare:
            compare_game = await _resolve_target_game_with_title_fallback(db, Game, str(args.compare))
            if not compare_game:
                print("Compare game not found.")
                return 1

            compare_result = await compute_game_taxonomy_v2(db, compare_game)
            if args.persist:
                await store_game_taxonomy_v2(db, compare_game, compare_result)
                await db.commit()

            print(f"Compare Game: {compare_game.title}")
            _print_compact_result("Stored compare taxonomy", compare_game)
            _print_compact_result("Recomputed compare taxonomy", compare_result)
            _print_provenance(
                "Stored compare provenance",
                compare_game,
                getattr(compare_game, "taxonomy_v2_fingerprint", None) or {},
            )
            _print_provenance("Recomputed compare provenance", compare_result, compare_result.fingerprint)
            _print_source_snippets("Compare source snippets", compare_game)

            stored_breakdown = build_similarity_breakdown_v2(game, compare_game)
            recomputed_breakdown = build_similarity_breakdown_v2(
                _clone_game_for_breakdown(game, result),
                _clone_game_for_breakdown(compare_game, compare_result),
            )
            _print_breakdown("Stored pair breakdown", stored_breakdown)
            _print_breakdown("Recomputed pair breakdown", recomputed_breakdown)
    return 0


async def cmd_taxonomy_v2_label_audit(args):
    """Audit grouped raw labels against the V2 label extractor."""
    from sqlalchemy import func, select

    from app.models.models import GameSourceTaxonomyLabel
    from app.services.game_taxonomy_v2 import analyze_taxonomy_v2_label

    async with async_session_maker() as db:
        query = (
            select(
                GameSourceTaxonomyLabel.source,
                GameSourceTaxonomyLabel.facet,
                GameSourceTaxonomyLabel.normalized_label,
                func.min(GameSourceTaxonomyLabel.raw_label).label("sample_raw_label"),
                func.count().label("row_count"),
                func.count(func.distinct(GameSourceTaxonomyLabel.game_id)).label("game_count"),
            )
            .group_by(
                GameSourceTaxonomyLabel.source,
                GameSourceTaxonomyLabel.facet,
                GameSourceTaxonomyLabel.normalized_label,
            )
        )
        if args.source:
            query = query.where(GameSourceTaxonomyLabel.source == args.source)
        if args.facet:
            query = query.where(GameSourceTaxonomyLabel.facet == args.facet)

        rows = (await db.execute(query)).all()

    audited: list[dict[str, object]] = []
    for source, facet, normalized_label, sample_raw_label, row_count, game_count in rows:
        if int(game_count) < args.min_count:
            continue
        analysis = analyze_taxonomy_v2_label(
            source=str(source),
            facet=str(facet),
            raw_label=str(normalized_label),
            normalized_label=str(normalized_label),
        )
        audited.append(
            {
                "source": str(source),
                "facet": str(facet),
                "normalized_label": str(normalized_label),
                "sample_raw_label": str(sample_raw_label or normalized_label),
                "row_count": int(row_count),
                "game_count": int(game_count),
                "analysis": analysis,
            }
        )

    if not audited:
        print("No grouped labels matched the requested audit scope.")
        return 0

    mapped = [row for row in audited if row["analysis"].classification == "mapped"]
    suppressed = [row for row in audited if row["analysis"].classification == "suppressed"]
    ignored = [row for row in audited if row["analysis"].classification == "ignored"]
    provider_gap = [row for row in audited if row["analysis"].classification == "provider_gap"]
    unmapped = [row for row in audited if row["analysis"].classification == "unmapped"]
    print(
        "Taxonomy V2 label audit: "
        f"{len(audited)} grouped labels "
        f"(mapped={len(mapped)}, suppressed={len(suppressed)}, ignored={len(ignored)}, "
        f"provider_gap={len(provider_gap)}, unmapped={len(unmapped)}, min_count={args.min_count})"
    )

    if suppressed:
        print("Top suppressed labels:")
        ranked_suppressed = sorted(
            suppressed,
            key=lambda row: (
                -int(row["game_count"]),
                str(row["source"]),
                str(row["facet"]),
                str(row["normalized_label"]),
            ),
        )
        for index, row in enumerate(ranked_suppressed[: args.limit], start=1):
            analysis = row["analysis"]
            print(
                f"{index:>3}. {row['source']}/{row['facet']}: {row['normalized_label']} "
                f"(games={row['game_count']}, reason={analysis.suppression_reason or 'suppressed'})"
            )
    else:
        print("Top suppressed labels: none")

    if ignored:
        print("Top ignored labels:")
        ranked_ignored = sorted(
            ignored,
            key=lambda row: (
                -int(row["game_count"]),
                str(row["source"]),
                str(row["facet"]),
                str(row["normalized_label"]),
            ),
        )
        for index, row in enumerate(ranked_ignored[: args.limit], start=1):
            print(
                f"{index:>3}. {row['source']}/{row['facet']}: {row['normalized_label']} "
                f"(games={row['game_count']})"
            )
    else:
        print("Top ignored labels: none")

    if provider_gap:
        print("Top provider-gap labels:")
        ranked_provider_gap = sorted(
            provider_gap,
            key=lambda row: (
                -int(row["game_count"]),
                str(row["source"]),
                str(row["facet"]),
                str(row["normalized_label"]),
            ),
        )
        for index, row in enumerate(ranked_provider_gap[: args.limit], start=1):
            print(
                f"{index:>3}. {row['source']}/{row['facet']}: {row['normalized_label']} "
                f"(games={row['game_count']}, sample='{_truncate_cli_text(str(row['sample_raw_label']), limit=72)}')"
            )
    else:
        print("Top provider-gap labels: none")

    if unmapped:
        print("Top unmapped labels:")
        ranked_unmapped = sorted(
            unmapped,
            key=lambda row: (
                -int(row["game_count"]),
                str(row["source"]),
                str(row["facet"]),
                str(row["normalized_label"]),
            ),
        )
        for index, row in enumerate(ranked_unmapped[: args.limit], start=1):
            print(
                f"{index:>3}. {row['source']}/{row['facet']}: {row['normalized_label']} "
                f"(games={row['game_count']}, rows={row['row_count']}, sample='{_truncate_cli_text(str(row['sample_raw_label']), limit=72)}')"
            )
    else:
        print("Top unmapped labels: none")

    if args.show_mapped:
        print("Top mapped labels:")
        ranked_mapped = sorted(
            mapped,
            key=lambda row: (
                -int(row["game_count"]),
                str(row["source"]),
                str(row["facet"]),
                str(row["normalized_label"]),
            ),
        )
        for index, row in enumerate(ranked_mapped[: args.limit], start=1):
            analysis = row["analysis"]
            tokens = ", ".join(analysis.resolved_tokens[:4]) or "none"
            signals = ", ".join(analysis.emitted_signals[:4]) or "none"
            print(
                f"{index:>3}. {row['source']}/{row['facet']}: {row['normalized_label']} "
                f"(games={row['game_count']}, tokens={tokens}, signals={signals}, "
                f"role={analysis.role_tier or 'none'}, rarity={analysis.rarity_bucket or 'none'})"
            )
    return 0


async def cmd_taxonomy_v2_text_audit(args):
    """Audit recurring phrases in stored V2 text corpora."""
    from collections import Counter, defaultdict
    from sqlalchemy import select

    from app.models.models import Game
    from app.services.game_taxonomy_v2 import extract_taxonomy_v2_text_phrases

    async with async_session_maker() as db:
        query = select(Game.title, Game.taxonomy_v2_status, Game.taxonomy_v2_text_corpus).where(
            Game.taxonomy_v2_text_corpus.isnot(None)
        )
        if args.status:
            query = query.where(Game.taxonomy_v2_status.in_(list(args.status)))
        if args.limit_games:
            query = query.limit(args.limit_games)
        rows = (await db.execute(query)).all()

    phrase_counts: dict[str, Counter[str]] = defaultdict(Counter)
    phrase_samples: dict[str, dict[str, str]] = defaultdict(dict)
    game_counts = Counter()

    for title, status, text_corpus in rows:
        status_key = str(status or "unknown")
        game_counts[status_key] += 1
        phrases = extract_taxonomy_v2_text_phrases(
            text_corpus,
            ngram=args.ngram,
            exclude_boilerplate=not args.include_boilerplate,
        )
        for phrase in phrases:
            phrase_counts[status_key][phrase] += 1
            phrase_samples[status_key].setdefault(phrase, str(title))

    if not game_counts:
        print("No games with taxonomy V2 text corpus matched the requested audit scope.")
        return 0

    statuses = list(args.status or [])
    if not statuses:
        statuses = [
            status
            for status in ("computed", "hidden", "curated", "pending", "needs_review", "failed", "unknown")
            if status in game_counts
        ]

    print(
        "Taxonomy V2 text audit: "
        f"games_scanned={sum(game_counts.values())}, "
        f"ngram={args.ngram}, "
        f"exclude_boilerplate={'no' if args.include_boilerplate else 'yes'}"
    )
    for status in statuses:
        print(f"  {status}: games={game_counts.get(status, 0)}")

    for status in statuses:
        ranked = [
            (phrase, count)
            for phrase, count in phrase_counts.get(status, Counter()).most_common()
            if count >= args.min_count
        ]
        print(f"Top phrases for {status}:")
        if not ranked:
            print("  none")
            continue
        for index, (phrase, count) in enumerate(ranked[: args.limit], start=1):
            sample_title = phrase_samples.get(status, {}).get(phrase, "")
            print(
                f"{index:>3}. {phrase} "
                f"(games={count}, sample='{_truncate_cli_text(sample_title, limit=56)}')"
            )
    return 0


async def cmd_taxonomy_v2_near_miss_audit(args):
    """Audit the closest archetype misses for V2 games without a clean classification."""
    from collections import Counter, defaultdict
    from sqlalchemy import select

    from app.models.models import Game
    from app.services.game_taxonomy_v2 import display_taxonomy_v2_token, rank_taxonomy_v2_near_misses

    async with async_session_maker() as db:
        query = select(
            Game.title,
            Game.public_id,
            Game.taxonomy_v2_status,
            Game.taxonomy_v2_fingerprint,
            Game.taxonomy_v2_hard_exclusions,
        )
        if args.status:
            query = query.where(Game.taxonomy_v2_status.in_(list(args.status)))
        if args.limit_games:
            query = query.limit(args.limit_games)
        rows = (await db.execute(query)).all()

    games_scanned = 0
    games_with_fingerprint = 0
    games_with_near_miss = 0
    archetype_counts = Counter()
    missing_axis_counts = Counter()
    archetype_missing_axis_counts: dict[str, Counter[str]] = defaultdict(Counter)
    examples: list[tuple[int, int, int, str, str, object]] = []

    for title, public_id, status, fingerprint, hard_exclusions in rows:
        games_scanned += 1
        if not fingerprint:
            continue
        games_with_fingerprint += 1
        near_misses = rank_taxonomy_v2_near_misses(
            fingerprint,
            hard_exclusions=hard_exclusions or [],
            limit=args.candidate_depth,
        )
        if not near_misses:
            continue
        games_with_near_miss += 1
        top = near_misses[0]
        archetype_counts[top.archetype] += 1
        for axis in top.missing_required_axes:
            missing_axis_counts[axis] += 1
            archetype_missing_axis_counts[top.archetype][axis] += 1
        examples.append(
            (
                top.required_hits,
                -len(top.missing_required_axes),
                top.preferred_hits,
                str(title),
                str(public_id or ""),
                top,
            )
        )

    print(
        "Taxonomy V2 near-miss audit: "
        f"games_scanned={games_scanned}, "
        f"with_fingerprint={games_with_fingerprint}, "
        f"with_near_miss={games_with_near_miss}, "
        f"statuses={', '.join(args.status or []) or 'all'}"
    )

    print("Top near archetypes:")
    if not archetype_counts:
        print("  none")
    else:
        for index, (archetype, count) in enumerate(archetype_counts.most_common(args.limit), start=1):
            common_missing = ", ".join(
                display_taxonomy_v2_token(axis)
                for axis, _ in archetype_missing_axis_counts[archetype].most_common(3)
            ) or "none"
            print(
                f"{index:>3}. {display_taxonomy_v2_token(archetype)} "
                f"(games={count}, common_missing={common_missing})"
            )

    print("Top missing required axes:")
    if not missing_axis_counts:
        print("  none")
    else:
        for index, (axis, count) in enumerate(missing_axis_counts.most_common(args.limit), start=1):
            print(f"{index:>3}. {display_taxonomy_v2_token(axis)} (games={count})")

    print("Examples:")
    if not examples:
        print("  none")
    else:
        examples.sort(key=lambda item: (-item[0], item[1], -item[2], item[3].lower()))
        for index, (_, _, _, title, public_id, near_miss) in enumerate(examples[: args.examples], start=1):
            missing = ", ".join(display_taxonomy_v2_token(axis) for axis in near_miss.missing_required_axes) or "none"
            print(
                f"{index:>3}. {title} -> {display_taxonomy_v2_token(near_miss.archetype)} "
                f"(missing={missing}, required={near_miss.required_hits}/{near_miss.required_total})"
            )
            if public_id:
                print(f"     public_id={public_id}")
    return 0


async def cmd_taxonomy_v2_boilerplate_audit(args):
    """Audit recurring storefront boilerplate in taxonomy V2 text corpora."""
    from collections import Counter
    from sqlalchemy import select

    from app.models.models import Game
    from app.services.game_taxonomy_v2 import detect_taxonomy_v2_boilerplate_segments

    async with async_session_maker() as db:
        query = select(Game.title, Game.taxonomy_v2_status, Game.taxonomy_v2_text_corpus).where(
            Game.taxonomy_v2_text_corpus.isnot(None)
        )
        if args.status:
            query = query.where(Game.taxonomy_v2_status.in_(list(args.status)))
        if args.limit_games:
            query = query.limit(args.limit_games)
        rows = (await db.execute(query)).all()

    category_game_counts = Counter()
    category_hit_counts = Counter()
    snippet_counts = Counter()
    snippet_samples: dict[tuple[str, str], tuple[str, str]] = {}
    games_scanned = 0

    for title, status, text_corpus in rows:
        games_scanned += 1
        hits = detect_taxonomy_v2_boilerplate_segments(text_corpus)
        seen_categories: set[str] = set()
        seen_snippets: set[tuple[str, str]] = set()
        for hit in hits:
            category_hit_counts[hit.category] += 1
            seen_categories.add(hit.category)
            marker = (hit.category, hit.normalized_segment)
            if marker in seen_snippets:
                continue
            seen_snippets.add(marker)
            snippet_counts[marker] += 1
            snippet_samples.setdefault(marker, (str(title), hit.segment))
        for category in seen_categories:
            category_game_counts[category] += 1

    print(
        "Taxonomy V2 boilerplate audit: "
        f"games_scanned={games_scanned}, statuses={', '.join(args.status or []) or 'all'}"
    )

    print("Top boilerplate categories:")
    if not category_game_counts:
        print("  none")
    else:
        for index, (category, game_count) in enumerate(category_game_counts.most_common(args.limit), start=1):
            print(
                f"{index:>3}. {category} "
                f"(games={game_count}, hits={category_hit_counts.get(category, 0)})"
            )

    print("Top boilerplate snippets:")
    ranked_snippets = [
        (marker, count)
        for marker, count in snippet_counts.most_common()
        if count >= args.min_count
    ]
    if not ranked_snippets:
        print("  none")
    else:
        for index, ((category, normalized_segment), count) in enumerate(ranked_snippets[: args.limit], start=1):
            sample_title, sample_segment = snippet_samples[(category, normalized_segment)]
            print(
                f"{index:>3}. [{category}] {_truncate_cli_text(sample_segment, limit=96)} "
                f"(games={count}, sample='{_truncate_cli_text(sample_title, limit=40)}')"
            )
    return 0


async def cmd_taxonomy_v2_confusion_audit(args):
    """Summarize taxonomy V2 family/archetype coverage and common secondary pairings."""
    from collections import Counter
    from sqlalchemy import select

    from app.models.models import Game
    from app.services.game_taxonomy_v2 import display_taxonomy_v2_token

    async with async_session_maker() as db:
        query = select(
            Game.title,
            Game.taxonomy_v2_status,
            Game.taxonomy_v2_primary_family,
            Game.taxonomy_v2_primary_archetype,
            Game.taxonomy_v2_secondary_archetypes,
        )
        if args.status:
            query = query.where(Game.taxonomy_v2_status.in_(list(args.status)))
        if args.limit_games:
            query = query.limit(args.limit_games)
        rows = (await db.execute(query)).all()

    status_counts = Counter()
    family_counts = Counter()
    archetype_counts = Counter()
    confusion_pairs = Counter()

    for _title, status, family, archetype, secondaries in rows:
        status_key = str(status or "unknown")
        status_counts[status_key] += 1
        if family:
            family_counts[str(family)] += 1
        if archetype:
            archetype_counts[str(archetype)] += 1
        primary = str(archetype or "")
        if primary:
            for secondary in secondaries or []:
                confusion_pairs[(primary, str(secondary))] += 1

    print(
        "Taxonomy V2 confusion audit: "
        f"games_scanned={sum(status_counts.values())}, statuses={', '.join(args.status or []) or 'all'}"
    )
    print("Statuses:")
    for index, (status, count) in enumerate(status_counts.most_common(args.limit), start=1):
        print(f"{index:>3}. {status} (games={count})")

    print("Top primary families:")
    if not family_counts:
        print("  none")
    else:
        for index, (family, count) in enumerate(family_counts.most_common(args.limit), start=1):
            print(f"{index:>3}. {display_taxonomy_v2_token(family)} (games={count})")

    print("Top primary archetypes:")
    if not archetype_counts:
        print("  none")
    else:
        for index, (archetype, count) in enumerate(archetype_counts.most_common(args.limit), start=1):
            print(f"{index:>3}. {display_taxonomy_v2_token(archetype)} (games={count})")

    print("Top primary->secondary pairings:")
    if not confusion_pairs:
        print("  none")
    else:
        for index, ((primary, secondary), count) in enumerate(confusion_pairs.most_common(args.limit), start=1):
            print(
                f"{index:>3}. {display_taxonomy_v2_token(primary)} -> "
                f"{display_taxonomy_v2_token(secondary)} (games={count})"
            )
    return 0


async def cmd_taxonomy_v2_gold_set_audit(args):
    """Evaluate live similar-games output against the taxonomy V2 gold set."""
    import json
    from pathlib import Path

    from sqlalchemy import select

    from app.models.models import Game
    from app.routers.games import get_game_similar

    gold_set_path = Path(__file__).resolve().parent / "data" / "taxonomy_v2_gold_set.json"
    payload = json.loads(gold_set_path.read_text())
    anchors = list(payload.get("anchors", []))
    if args.limit_games:
        anchors = anchors[: args.limit_games]

    processed = 0
    expected_total = 0
    expected_hits = 0
    blocked_violations = 0

    async with async_session_maker() as db:
        for anchor in anchors:
            anchor_title = str(anchor.get("title") or "").strip()
            if not anchor_title:
                continue
            game = (
                await db.execute(
                    select(Game).where(Game.title == anchor_title).order_by(Game.release_date.desc().nulls_last(), Game.id.desc())
                )
            ).scalars().first()
            if not game:
                print(f"Missing anchor: {anchor_title}")
                continue

            processed += 1
            results = await get_game_similar(game_id=str(game.id), limit=args.limit, db=db)
            result_titles = [item.title for item in results]
            result_title_set = set(result_titles)

            expected_neighbors = [str(value) for value in anchor.get("expected_neighbors", [])]
            blocked_neighbors = [str(value) for value in anchor.get("blocked_neighbors", [])]

            hits = [title for title in expected_neighbors if title in result_title_set]
            violations = [title for title in blocked_neighbors if title in result_title_set]

            expected_total += len(expected_neighbors)
            expected_hits += len(hits)
            blocked_violations += len(violations)

            precision = (len(hits) / max(1, min(len(expected_neighbors), len(result_titles)))) if result_titles else 0.0
            print(f"{anchor_title}: precision@{args.limit}={precision:.2f}")
            print(f"  results: {', '.join(result_titles) or 'none'}")
            print(f"  expected_hits: {', '.join(hits) or 'none'}")
            print(f"  blocked_hits: {', '.join(violations) or 'none'}")

    print(
        "Taxonomy V2 gold-set audit: "
        f"anchors={processed}, expected_hits={expected_hits}/{expected_total}, blocked_violations={blocked_violations}"
    )
    return 0


async def cmd_similarity_v3_corpus(args):
    """Build/update Similar Games V3 document rows and embeddings."""
    from app.services.game_similarity_v3 import (
        build_similarity_v3_document_rows,
    )

    game_ids = await _load_similarity_v3_target_game_ids(
        dirty_only=args.dirty_only,
        game_identifier=args.game,
        limit=args.limit,
    )
    if not game_ids:
        print("No games found for similarity V3 corpus build.")
        return 1

    processed = 0
    total_batches = max(1, (len(game_ids) + _SIMILARITY_V3_CORPUS_BATCH_SIZE - 1) // _SIMILARITY_V3_CORPUS_BATCH_SIZE)
    for batch_index, batch_start in enumerate(range(0, len(game_ids), _SIMILARITY_V3_CORPUS_BATCH_SIZE), start=1):
        batch_ids = game_ids[batch_start : batch_start + _SIMILARITY_V3_CORPUS_BATCH_SIZE]

        async def _process_batch() -> int:
            async with async_session_maker() as db:
                batch_games = await _load_games_by_ids(db, batch_ids)
                updated = await build_similarity_v3_document_rows(db, batch_games)
                await db.commit()
                return updated

        updated = await _retry_similarity_v3_batch(
            "Similarity V3 corpus",
            batch_index,
            total_batches,
            _process_batch,
        )
        processed += len(batch_ids)
        print(
            f"  Progress: {processed}/{len(game_ids)} "
            f"(documents_refreshed={updated})"
        )

    print(f"Similarity V3 corpus complete: {processed} games processed")
    return 0


async def cmd_similarity_v3_embed(args):
    """Refresh Similar Games V3 embeddings for target games."""
    return await cmd_similarity_v3_corpus(args)


async def cmd_similarity_v3_neighbors(args):
    """Preview Similar Games V3 ranked neighbors without switching the live route."""
    from app.services.game_similarity_v3 import (
        build_similarity_v3_document_rows,
        compute_similarity_v3_neighbors_for_game,
        load_similarity_v3_target_games,
    )

    async with async_session_maker() as db:
        games = await load_similarity_v3_target_games(
            db,
            dirty_only=args.dirty_only,
            game_identifier=args.game,
            limit=args.limit_games,
        )
        if not games:
            print("No games found for similarity V3 neighbor preview.")
            return 1

        await build_similarity_v3_document_rows(db, games)
        await db.commit()

        for game in games:
            print(f"Similarity V3 preview for: {game.title}")
            neighbors = await compute_similarity_v3_neighbors_for_game(db, game, limit=args.limit)
            if not neighbors:
                print("  none")
                continue
            for index, neighbor in enumerate(neighbors, start=1):
                print(
                    f"  {index}. {neighbor.candidate.title} "
                    f"(score={neighbor.final_score:.4f}, relationship={neighbor.relationship_type}, "
                    f"vector_exception={'yes' if neighbor.used_vector_exception else 'no'})"
                )
                reasons = neighbor.explanation_payload.get("match_reasons") or []
                if reasons:
                    print(f"     reasons: {', '.join(reasons)}")
    return 0


async def cmd_similarity_v3_publish(args):
    """Publish Similar Games V3 neighbors to the DB-backed serving table."""
    from app.services.game_similarity_v3 import (
        build_similarity_v3_document_rows,
        publish_similarity_v3_neighbors_for_games,
    )

    game_ids = await _load_similarity_v3_target_game_ids(
        dirty_only=args.dirty_only,
        game_identifier=args.game,
        limit=args.limit_games,
    )
    if not game_ids:
        print("No games found for similarity V3 publish.")
        return 1

    processed = 0
    computed = 0
    hidden = 0
    total_batches = max(1, (len(game_ids) + _SIMILARITY_V3_PUBLISH_BATCH_SIZE - 1) // _SIMILARITY_V3_PUBLISH_BATCH_SIZE)
    for batch_index, batch_start in enumerate(range(0, len(game_ids), _SIMILARITY_V3_PUBLISH_BATCH_SIZE), start=1):
        batch_ids = game_ids[batch_start : batch_start + _SIMILARITY_V3_PUBLISH_BATCH_SIZE]

        async def _process_batch() -> dict[str, int]:
            async with async_session_maker() as db:
                batch_games = await _load_games_by_ids(db, batch_ids)
                await build_similarity_v3_document_rows(db, batch_games)
                stats = await publish_similarity_v3_neighbors_for_games(
                    db,
                    batch_games,
                    limit=args.limit,
                    persist_run=batch_index == total_batches,
                )
                await db.commit()
                return stats

        stats = await _retry_similarity_v3_batch(
            "Similarity V3 publish",
            batch_index,
            total_batches,
            _process_batch,
        )
        processed += stats["processed"]
        computed += stats["computed"]
        hidden += stats["hidden"]
        print(
            f"  Progress: {processed}/{len(game_ids)} "
            f"(computed={computed}, hidden={hidden})"
        )

    print(
        "Similarity V3 publish complete: "
        f"{processed} processed, {computed} computed, {hidden} hidden"
    )
    return 0


async def cmd_similarity_v3_gold_audit(args):
    """Audit published Similar Games V3 neighbors against the gold set."""
    from app.services.game_similarity_v3 import audit_similarity_v3_gold_set

    async with async_session_maker() as db:
        results = await audit_similarity_v3_gold_set(db, limit=args.limit)

    if not results:
        print("No Similar Games V3 gold-set results available.")
        return 0

    hits = 0
    expected_total = 0
    blocked_hits = 0
    for row in results:
        if not row.get("found"):
            print(f"{row['anchor']}: missing")
            continue
        print(f"{row['anchor']}: precision@{args.limit}={row['precision_at_limit']:.2f}")
        print(f"  results: {', '.join(row['results']) or 'none'}")
        hits += int(row["hits"])
        expected_total += int(row["expected_count"])
        blocked_hits += int(row["blocked_hits"])

    print(
        "Similarity V3 gold-set audit: "
        f"expected_hits={hits}/{expected_total}, blocked_hits={blocked_hits}"
    )
    return 0


async def cmd_similarity_v3_confusion_audit(args):
    """Audit published Similar Games V3 relationship distribution by archetype."""
    from app.services.game_similarity_v3 import audit_similarity_v3_confusion

    async with async_session_maker() as db:
        rows = await audit_similarity_v3_confusion(
            db,
            limit=args.limit,
            include_same=args.include_same,
        )

    if not rows:
        print("No Similar Games V3 confusion data available.")
        return 0

    print("Similarity V3 confusion audit:")
    for index, row in enumerate(rows, start=1):
        print(
            f"{index:>3}. {row['primary_archetype'] or 'none'} -> "
            f"{row['relationship_type'] or 'none'} (rows={row['count']})"
        )
    return 0


async def cmd_similarity_v3_hidden_audit(args):
    """Audit hidden Similar Games V3 states by cause."""
    from app.services.game_similarity_v3 import SIMILARITY_V3_VERSION, audit_similarity_v3_hidden_states

    async with async_session_maker() as db:
        rows = await audit_similarity_v3_hidden_states(
            db,
            similarity_version=None if args.all_versions else SIMILARITY_V3_VERSION,
        )

    if args.all_versions:
        print("Similarity V3 hidden audit (all versions):")
    else:
        print(f"Similarity V3 hidden audit ({SIMILARITY_V3_VERSION}):")
    if not rows:
        print("  none")
        return 0
    for index, (reason, count) in enumerate(rows.items(), start=1):
        print(f"{index:>3}. {reason} (games={count})")
    return 0


def cmd_enqueue_job(args):
    """Enqueue a background worker job onto the Dramatiq queues."""
    from app.tasks.disparity import calculate_daily_snapshots
    from app.tasks.similarity import (
        similarity_v3_corpus_job,
        similarity_v3_pipeline_job,
        similarity_v3_publish_job,
        taxonomy_v2_backfill_job,
    )
    from app.tasks.sync import (
        match_games_to_platforms,
        sync_metacritic_scores,
        sync_opencritic_full,
        sync_opencritic_incremental,
        sync_steam_scores,
    )

    job_map = {
        "sync-opencritic-full": (
            sync_opencritic_full,
            (),
            {},
        ),
        "sync-opencritic-incremental": (
            sync_opencritic_incremental,
            (),
            {},
        ),
        "sync-steam": (
            sync_steam_scores,
            (),
            {},
        ),
        "sync-metacritic": (
            sync_metacritic_scores,
            (),
            {},
        ),
        "match-games": (
            match_games_to_platforms,
            (),
            {},
        ),
        "disparity-snapshots": (
            calculate_daily_snapshots,
            (),
            {"snapshot_date": args.snapshot_date},
        ),
        "taxonomy-v2-backfill": (
            taxonomy_v2_backfill_job,
            (),
            {"game": args.game, "limit": args.limit},
        ),
        "similarity-v3-corpus": (
            similarity_v3_corpus_job,
            (),
            {"game": args.game, "limit": args.limit, "dirty_only": args.dirty_only},
        ),
        "similarity-v3-publish": (
            similarity_v3_publish_job,
            (),
            {
                "game": args.game,
                "limit": args.limit or 10,
                "limit_games": args.limit_games,
                "dirty_only": args.dirty_only,
            },
        ),
        "similarity-v3-pipeline": (
            similarity_v3_pipeline_job,
            (),
            {
                "taxonomy_backfill": args.taxonomy_backfill,
                "corpus_dirty_only": args.dirty_only,
                "publish_dirty_only": args.publish_dirty_only,
                "game": args.game,
                "taxonomy_limit": args.taxonomy_limit,
                "corpus_limit": args.limit,
                "publish_limit": args.publish_limit,
                "publish_limit_games": args.limit_games,
                "run_gold_audit": args.run_gold_audit,
            },
        ),
    }

    actor, positional_args, keyword_args = job_map[args.job]
    filtered_kwargs = {key: value for key, value in keyword_args.items() if value is not None}
    message = actor.send(*positional_args, **filtered_kwargs)
    print(
        f"Enqueued {args.job} "
        f"(queue={getattr(message, 'queue_name', 'unknown')}, message_id={getattr(message, 'message_id', 'unknown')})"
    )
    return 0


async def cmd_disparity(args):
    """Handle disparity calculation command."""
    import time
    from app.services.disparity import DisparityCalculator

    async with async_session_maker() as db:
        calculator = DisparityCalculator(db)

        print(f"\n{'='*50}")
        print(f"Calculating disparity snapshots at {datetime.now().isoformat()}")
        print(f"{'='*50}\n")

        start = time.time()

        if args.journalists:
            count = await calculator.generate_journalist_snapshots()
            print(f"Created {count} journalist snapshots.")

        if args.outlets:
            count = await calculator.generate_outlet_snapshots()
            print(f"Created {count} outlet snapshots.")

        if args.games:
            count = await calculator.generate_game_snapshots()
            print(f"Created {count} game snapshots.")

        if not (args.journalists or args.outlets or args.games):
            results = await calculator.generate_all_snapshots()
            print(f"\n{'='*50}")
            print(f"Created snapshots: {results['journalists']} journalists, {results['outlets']} outlets, {results['games']} games")

        elapsed = time.time() - start
        print(f"Completed in {elapsed:.1f}s")
        print(f"{'='*50}")


async def cmd_refresh_images(args):
    """Fix image URLs by adding CDN base URL to relative paths."""
    from app.services.opencritic import OpenCriticService
    from app.models.models import Journalist, Outlet, Game
    from sqlalchemy import select

    CDN_URL = OpenCriticService.IMAGE_CDN_URL

    async with async_session_maker() as db:
        updated_journalists = 0
        updated_outlets = 0
        updated_games = 0

        # Fix journalist images
        print("Fixing journalist image URLs...")
        result = await db.execute(
            select(Journalist).where(
                Journalist.image_url.isnot(None),
                ~Journalist.image_url.startswith("http")
            )
        )
        journalists = result.scalars().all()

        for journalist in journalists:
            journalist.image_url = f"{CDN_URL}/{journalist.image_url}"
            updated_journalists += 1

        await db.commit()
        print(f"Fixed {updated_journalists} journalist image URLs")

        # Fix outlet logos
        print("Fixing outlet logo URLs...")
        result = await db.execute(
            select(Outlet).where(
                Outlet.logo_url.isnot(None),
                ~Outlet.logo_url.startswith("http")
            )
        )
        outlets = result.scalars().all()

        for outlet in outlets:
            outlet.logo_url = f"{CDN_URL}/{outlet.logo_url}"
            updated_outlets += 1

        await db.commit()
        print(f"Fixed {updated_outlets} outlet logo URLs")

        # Fix game images
        print("Fixing game image URLs...")
        result = await db.execute(
            select(Game).where(
                Game.image_url.isnot(None),
                ~Game.image_url.startswith("http")
            )
        )
        games = result.scalars().all()

        for game in games:
            game.image_url = f"{CDN_URL}/{game.image_url}"
            updated_games += 1

        await db.commit()
        print(f"Fixed {updated_games} game image URLs")

        print(f"\nImage URL fix complete: {updated_journalists} journalists, {updated_outlets} outlets, {updated_games} games")


async def cmd_refresh_reviews(args):
    """Handle refresh-reviews command - re-fetch reviews for recent games."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)

        days = args.days
        print(f"\n{'='*50}")
        if args.all:
            print("Refreshing reviews for ALL games")
        else:
            print(f"Refreshing reviews for games released in last {days} days")
        if args.limit:
            print(f"Limiting to {args.limit} games")
        print(f"Started at {datetime.now().isoformat()}")
        print(f"{'='*50}\n")

        try:
            stats = await orchestrator.refresh_recent_reviews(
                days=days,
                limit=args.limit,
                all_games=args.all,
                min_hours_since_last_sync=args.min_hours_since_last_sync,
            )
            print(f"\n{'='*50}")
            print("Review refresh completed successfully!")
            print(f"{'='*50}")
            return 0
        except Exception as e:
            print(f"\nRefresh failed: {e}")
            return 1


async def cmd_match(args):
    """Handle game matching command."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)

        print(f"\n{'='*50}")
        print("Matching games to Steam/Metacritic")
        print(f"{'='*50}\n")

        stats = await orchestrator.match_games_to_steam(limit=args.limit, days=args.days)

        print(f"\nMatching complete!")
        print(f"  Total games: {stats['total']}")
        print(f"  Steam IDs matched: {stats.get('steam_matched', stats.get('matched', 0))}")
        print(f"  Metacritic slugs assigned: {stats.get('metacritic_slugs_assigned', 0)}")
        print(f"  Failed: {stats['failed']}")


async def cmd_game_images(args):
    """Handle Steam game image backfill command."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)

        print(f"\n{'='*50}")
        print("Backfilling game images from Steam")
        if args.overwrite:
            print("Mode: overwrite existing image URLs")
        else:
            print("Mode: only games missing image URLs")
        if args.days is not None:
            print(f"Release-date filter: last {args.days} days")
        if args.limit:
            print(f"Limit: {args.limit} games")
        print(f"{'='*50}\n")

        stats = await orchestrator.backfill_game_images_from_steam(
            limit=args.limit,
            days=args.days,
            overwrite=args.overwrite,
        )

        print(f"\nBackfill complete!")
        print(f"  Total games: {stats['total']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")


async def cmd_clear(args):
    """Handle clear command - removes all data from database."""
    from sqlalchemy import text

    async with async_session_maker() as db:
        # Show current counts
        from app.models.models import Game, Review, Journalist, Outlet, UserScore, DisparitySnapshot, SyncState
        from sqlalchemy import select, func

        counts = {}
        for model, name in [
            (Review, "reviews"),
            (UserScore, "user_scores"),
            (DisparitySnapshot, "disparity_snapshots"),
            (Game, "games"),
            (Journalist, "journalists"),
            (Outlet, "outlets"),
        ]:
            result = await db.execute(select(func.count()).select_from(model))
            counts[name] = result.scalar() or 0

        print("\nCurrent data in database:")
        for name, count in counts.items():
            print(f"  {name}: {count:,}")

        total = sum(counts.values())
        if total == 0:
            print("\nDatabase is already empty.")
            return

        confirm = input(f"\nAre you sure you want to delete all {total:,} records? [y/N] ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return

        # Delete in order (respecting foreign keys)
        print("\nClearing data...")
        await db.execute(text("DELETE FROM disparity_snapshots"))
        await db.execute(text("DELETE FROM user_scores"))
        await db.execute(text("DELETE FROM reviews"))
        await db.execute(text("DELETE FROM games"))
        await db.execute(text("DELETE FROM journalists"))
        await db.execute(text("DELETE FROM outlets"))
        await db.execute(text("DELETE FROM sync_state"))
        await db.execute(text("DELETE FROM sync_logs"))
        await db.commit()

        print("All data cleared successfully.")


async def cmd_backfill_game_columns(args):
    """Backfill denormalized columns on Game from UserScore and Review tables."""
    from app.models.models import Game, UserScore, UserScoreSource, Review
    from sqlalchemy import select, func

    async with async_session_maker() as db:
        result = await db.execute(select(Game))
        games = result.scalars().all()

        print(f"Backfilling denormalized columns for {len(games)} games...")

        updated = 0
        for game in games:
            changed = False

            # Backfill steam_user_score and steam_sample_size
            steam_result = await db.execute(
                select(UserScore.score, UserScore.sample_size)
                .where(
                    UserScore.game_id == game.id,
                    UserScore.source == UserScoreSource.STEAM,
                )
                .order_by(UserScore.scraped_at.desc())
                .limit(1)
            )
            steam_row = steam_result.first()
            if steam_row:
                if game.steam_user_score != steam_row[0] or game.steam_sample_size != steam_row[1]:
                    game.steam_user_score = steam_row[0]
                    game.steam_sample_size = steam_row[1]
                    changed = True

            # Backfill metacritic_user_score and metacritic_sample_size
            mc_result = await db.execute(
                select(UserScore.score, UserScore.sample_size)
                .where(
                    UserScore.game_id == game.id,
                    UserScore.source == UserScoreSource.METACRITIC,
                )
                .order_by(UserScore.scraped_at.desc())
                .limit(1)
            )
            mc_row = mc_result.first()
            if mc_row:
                if game.metacritic_user_score != mc_row[0] or game.metacritic_sample_size != mc_row[1]:
                    game.metacritic_user_score = mc_row[0]
                    game.metacritic_sample_size = mc_row[1]
                    changed = True

            # Backfill avg_critic_score and critic_review_count
            review_result = await db.execute(
                select(
                    func.avg(Review.score_normalized),
                    func.count(Review.id),
                ).where(
                    Review.game_id == game.id,
                    Review.score_normalized.isnot(None),
                )
            )
            review_row = review_result.first()
            if review_row and review_row[1] > 0:
                from decimal import Decimal
                avg_score = Decimal(str(round(float(review_row[0]), 2)))
                count = review_row[1]
                if game.avg_critic_score != avg_score or game.critic_review_count != count:
                    game.avg_critic_score = avg_score
                    game.critic_review_count = count
                    changed = True

            if changed:
                updated += 1

            if updated % 100 == 0 and updated > 0:
                await db.commit()
                print(f"  Updated {updated} games...")

        await db.commit()
        print(f"\nBackfill complete: {updated} games updated")


async def cmd_recompute_scores(args):
    """Recompute review.score_normalized from score_raw/score_scale in batches."""
    from sqlalchemy import select, func, update

    from app.models.models import Review
    from app.services.score_normalizer import ScoreNormalizer

    batch_size = max(1, args.batch_size)
    max_reviews = args.max_reviews if args.max_reviews and args.max_reviews > 0 else None
    dry_run = bool(args.dry_run)
    write_all = bool(args.write_all)

    async with async_session_maker() as db:
        total_query = select(func.count()).select_from(Review)
        total_reviews = (await db.execute(total_query)).scalar() or 0
        if max_reviews is not None:
            total_reviews = min(total_reviews, max_reviews)

        if total_reviews == 0:
            print("No reviews found.")
            return

        mode_label = "dry-run" if dry_run else "write"
        write_behavior = "write-all" if write_all else "update-only-if-changed"
        print(
            f"Recomputing normalized scores for up to {total_reviews:,} reviews "
            f"({mode_label}, {write_behavior}, batch_size={batch_size})"
        )

        processed = 0
        changed = 0
        unchanged = 0
        recomputed_to_null = 0
        writes = 0
        last_id = 0

        while processed < total_reviews:
            remaining = total_reviews - processed
            current_batch_size = min(batch_size, remaining)
            rows = (
                await db.execute(
                    select(
                        Review.id,
                        Review.score_raw,
                        Review.score_scale,
                        Review.score_normalized,
                    )
                    .where(Review.id > last_id)
                    .order_by(Review.id.asc())
                    .limit(current_batch_size)
                )
            ).all()

            if not rows:
                break

            updates: list[dict[str, object]] = []
            for review_id, score_raw, score_scale, score_normalized in rows:
                recomputed_score, _ = ScoreNormalizer.normalize(score_raw or "", score_scale)
                if recomputed_score is None:
                    recomputed_to_null += 1

                is_changed = score_normalized != recomputed_score
                if is_changed:
                    changed += 1
                else:
                    unchanged += 1

                if write_all or is_changed:
                    updates.append(
                        {
                            "id": review_id,
                            "score_normalized": recomputed_score,
                        }
                    )

            if updates:
                writes += len(updates)
                if not dry_run:
                    await db.execute(update(Review), updates)
                    await db.commit()

            processed += len(rows)
            last_id = rows[-1][0]

            if processed % 10000 == 0 or processed == total_reviews:
                print(
                    f"  Processed {processed:,}/{total_reviews:,} "
                    f"(changed={changed:,}, unchanged={unchanged:,}, writes={writes:,})"
                )

        print("Recompute complete:")
        print(f"  Processed: {processed:,}")
        print(f"  Changed: {changed:,}")
        print(f"  Unchanged: {unchanged:,}")
        print(f"  Recomputed to NULL: {recomputed_to_null:,}")
        print(f"  Rows written: {writes:,}" + (" (dry-run only)" if dry_run else ""))


async def cmd_merge_games(args):
    """Merge deprecated game records into their canonical game, based on GAME_MERGES."""
    from sqlalchemy import select, func, update, delete
    from app.models.models import Game, Review, UserScore, DisparitySnapshot
    from app.services.sync_orchestrator import SyncOrchestrator

    merges = SyncOrchestrator.GAME_MERGES

    if not merges:
        print("No game merges configured in SyncOrchestrator.GAME_MERGES")
        return

    async with async_session_maker() as db:
        for deprecated_oc_id, canonical_oc_id in merges.items():
            # Find both games
            dep_result = await db.execute(
                select(Game).where(Game.opencritic_id == deprecated_oc_id)
            )
            deprecated_game = dep_result.scalar_one_or_none()

            can_result = await db.execute(
                select(Game).where(Game.opencritic_id == canonical_oc_id)
            )
            canonical_game = can_result.scalar_one_or_none()

            if not canonical_game:
                print(f"Canonical game OC {canonical_oc_id} not found, skipping")
                continue

            if not deprecated_game:
                print(f"Deprecated game OC {deprecated_oc_id} not found (already merged?), skipping")
                # Still update canonical game's cross-platform IDs
                print(f"\nUpdating canonical game: {canonical_game.title} (ID {canonical_game.id})")
                changed = False
                if not canonical_game.steam_app_id:
                    from app.services.game_matcher import GameMatcher
                    override = GameMatcher.MANUAL_OVERRIDES.get(canonical_oc_id, {})
                    if override.get("steam_app_id"):
                        canonical_game.steam_app_id = override["steam_app_id"]
                        print(f"  Set steam_app_id = {override['steam_app_id']}")
                        changed = True
                    if override.get("metacritic_slug"):
                        canonical_game.metacritic_slug = override["metacritic_slug"]
                        print(f"  Set metacritic_slug = {override['metacritic_slug']}")
                        changed = True
                if changed:
                    await db.commit()
                continue

            print(f"\n{'='*60}")
            print(f"MERGING: {deprecated_game.title} (OC {deprecated_oc_id}, ID {deprecated_game.id})")
            print(f"   INTO: {canonical_game.title} (OC {canonical_oc_id}, ID {canonical_game.id})")
            print(f"{'='*60}")

            # Count records to merge
            review_count = await db.execute(
                select(func.count()).select_from(Review).where(Review.game_id == deprecated_game.id)
            )
            score_count = await db.execute(
                select(func.count()).select_from(UserScore).where(UserScore.game_id == deprecated_game.id)
            )
            snapshot_count = await db.execute(
                select(func.count()).select_from(DisparitySnapshot).where(DisparitySnapshot.game_id == deprecated_game.id)
            )

            r_count = review_count.scalar() or 0
            s_count = score_count.scalar() or 0
            snap_count = snapshot_count.scalar() or 0

            print(f"\nRecords to migrate:")
            print(f"  Reviews: {r_count}")
            print(f"  User Scores: {s_count}")
            print(f"  Disparity Snapshots: {snap_count}")

            if not args.yes:
                confirm = input(f"\nProceed with merge? [y/N] ")
                if confirm.lower() != 'y':
                    print("Skipped.")
                    continue

            # 1. Move reviews (handle duplicate opencritic_review_ids by skipping conflicts)
            if r_count > 0:
                await db.execute(
                    update(Review)
                    .where(Review.game_id == deprecated_game.id)
                    .values(game_id=canonical_game.id)
                )
                print(f"  Moved {r_count} reviews")

            # 2. Move user scores
            if s_count > 0:
                await db.execute(
                    update(UserScore)
                    .where(UserScore.game_id == deprecated_game.id)
                    .values(game_id=canonical_game.id)
                )
                print(f"  Moved {s_count} user scores")

            # 3. Move disparity snapshots
            if snap_count > 0:
                await db.execute(
                    update(DisparitySnapshot)
                    .where(DisparitySnapshot.game_id == deprecated_game.id)
                    .values(game_id=canonical_game.id)
                )
                print(f"  Moved {snap_count} disparity snapshots")

            # 4. Transfer Steam app ID and Metacritic slug to canonical game
            if deprecated_game.steam_app_id and not canonical_game.steam_app_id:
                canonical_game.steam_app_id = deprecated_game.steam_app_id
                print(f"  Transferred steam_app_id: {deprecated_game.steam_app_id}")

            # Apply manual override values
            from app.services.game_matcher import GameMatcher
            override = GameMatcher.MANUAL_OVERRIDES.get(canonical_oc_id, {})
            if override.get("steam_app_id"):
                canonical_game.steam_app_id = override["steam_app_id"]
                print(f"  Set steam_app_id = {override['steam_app_id']} (from override)")
            if override.get("metacritic_slug"):
                canonical_game.metacritic_slug = override["metacritic_slug"]
                print(f"  Set metacritic_slug = {override['metacritic_slug']} (from override)")

            # 5. Delete the deprecated game record
            await db.execute(
                delete(Game).where(Game.id == deprecated_game.id)
            )
            print(f"  Deleted deprecated game record (ID {deprecated_game.id})")

            await db.commit()
            print(f"\nMerge complete!")

        print(f"\nAll merges processed.")


async def cmd_news(args):
    """Handle news RSS feed sync command."""
    from sqlalchemy import text, select, func, and_, or_

    from app.models.models import Game, NewsArticle
    from app.cache import close_redis
    from app.services.news_rss import NewsRSSService
    from app.services.news_matcher import NewsMatcher
    from app.services.post_sync_refresh import refresh_news_after_sync
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    async with async_session_maker() as db:
        if args.clear:
            result = await db.execute(
                select(func.count()).select_from(NewsArticle)
            )
            count = result.scalar() or 0

            if count == 0:
                print("No news articles to clear.")
                return

            confirm = input(f"Delete all {count:,} news articles? [y/N] ")
            if confirm.lower() != 'y':
                print("Cancelled.")
                return

            await db.execute(text("DELETE FROM news_articles"))
            await db.commit()
            print(f"Deleted {count:,} news articles.")
            return

        service = NewsRSSService()

        print(f"\n{'='*50}")
        print(f"Fetching gaming news RSS feeds at {datetime.now().isoformat()}")
        print(f"{'='*50}\n")

        articles = await service.fetch_all_feeds()
        print(f"Fetched {len(articles)} articles from {len(service.FEEDS)} feeds")

        # Load game titles for matching articles to games
        games_result = await db.execute(select(Game.id, Game.title))
        matcher = NewsMatcher(games_result.all())

        upserted = 0
        matched = 0
        for article in articles:
            game_id = matcher.match(article["title"], article.get("description"))
            if game_id:
                article["game_id"] = game_id
                matched += 1
            stmt = pg_insert(NewsArticle).values(**article)
            stmt = stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={"game_id": stmt.excluded.game_id},
                where=and_(
                    stmt.excluded.game_id.isnot(None),
                    or_(
                        NewsArticle.game_id.is_(None),
                        NewsArticle.game_id != stmt.excluded.game_id,
                    ),
                ),
            )
            result = await db.execute(stmt)
            if result.rowcount > 0:
                upserted += 1

        await db.commit()

        total_result = await db.execute(
            select(func.count()).select_from(NewsArticle)
        )
        total = total_result.scalar() or 0

        # Refresh backend news caches and trigger optional frontend revalidation.
        if upserted > 0:
            await refresh_news_after_sync(db)
            await close_redis()

        print(
            f"\nNews sync complete: {upserted} rows inserted/updated, "
            f"{matched} matched to games ({total} total in database)"
        )


async def cmd_news_backfill(args):
    """Backfill game_id on existing news articles by matching titles."""
    from sqlalchemy import select

    from app.models.models import Game, NewsArticle
    from app.services.news_matcher import NewsMatcher
    from app.cache import close_redis
    from app.services.post_sync_refresh import refresh_news_after_sync

    async with async_session_maker() as db:
        # Load all game titles
        games_result = await db.execute(select(Game.id, Game.title))
        games = games_result.all()
        matcher = NewsMatcher(games)
        print(f"Loaded {len(games)} game titles for matching")

        # Build article query
        query = select(NewsArticle)
        if not args.all:
            query = query.where(NewsArticle.game_id.is_(None))

        if args.days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
            query = query.where(
                NewsArticle.published_at.isnot(None),
                NewsArticle.published_at >= cutoff,
            )

        query = query.order_by(NewsArticle.published_at.desc().nulls_last())

        if args.limit:
            query = query.limit(args.limit)

        articles_result = await db.execute(query)
        articles = articles_result.scalars().all()
        mode = "all articles" if args.all else "unlinked articles"
        print(f"Found {len(articles)} {mode} to process")

        linked_new = 0
        relinked = 0
        cleared_stale = 0
        unchanged = 0
        unmatched = 0
        pending_changes = 0
        sample_changes: list[str] = []

        if args.relink and not args.all:
            print("Note: --relink has no effect without --all")

        for i, article in enumerate(articles):
            matched_game_id = matcher.match(article.title, article.description)
            if not matched_game_id:
                unmatched += 1
                if args.all and args.relink and article.game_id is not None:
                    cleared_stale += 1
                    if len(sample_changes) < 25:
                        sample_changes.append(
                            f"CLEAR article_id={article.id} old_game_id={article.game_id} "
                            f"title={article.title[:100]}"
                        )
                    if not args.dry_run:
                        article.game_id = None
                        pending_changes += 1
            elif article.game_id is None:
                linked_new += 1
                if len(sample_changes) < 25:
                    sample_changes.append(
                        f"LINK article_id={article.id} game_id={matched_game_id} "
                        f"title={article.title[:100]}"
                    )
                if not args.dry_run:
                    article.game_id = matched_game_id
                    pending_changes += 1
            elif article.game_id != matched_game_id:
                if args.all and args.relink:
                    relinked += 1
                    if len(sample_changes) < 25:
                        sample_changes.append(
                            f"RELINK article_id={article.id} old_game_id={article.game_id} "
                            f"new_game_id={matched_game_id} title={article.title[:100]}"
                        )
                    if not args.dry_run:
                        article.game_id = matched_game_id
                        pending_changes += 1
                else:
                    unchanged += 1
            else:
                unchanged += 1

            if (i + 1) % 100 == 0:
                if pending_changes and not args.dry_run:
                    await db.commit()
                    pending_changes = 0
                print(
                    f"  Processed {i + 1}/{len(articles)} "
                    f"(new links: {linked_new}, relinked: {relinked}, cleared stale: {cleared_stale})"
                )

        if pending_changes and not args.dry_run:
            await db.commit()

        changed = linked_new + relinked + cleared_stale
        if changed > 0 and not args.dry_run:
            await refresh_news_after_sync(db)
            await close_redis()

        print("\nBackfill complete:")
        print(f"  Processed: {len(articles)}")
        print(f"  Newly linked: {linked_new}")
        print(f"  Relinked: {relinked}")
        print(f"  Cleared stale links: {cleared_stale}")
        print(f"  Unchanged: {unchanged}")
        print(f"  Unmatched: {unmatched}")
        if sample_changes:
            print("  Sample changes:")
            for line in sample_changes:
                print(f"    - {line}")
        if args.dry_run:
            print("  Dry run only: no database changes were committed")


def main():
    parser = argparse.ArgumentParser(
        description="Game Journalist Review Disparity Tracker CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="OpenCritic sync operations")
    sync_parser.add_argument("--status", action="store_true", help="Show sync status")
    sync_parser.add_argument("--reset", action="store_true", help="Reset sync state")
    sync_parser.add_argument("--full-scan", action="store_true", help="Force full OpenCritic catalog sweep (slower)")
    sync_parser.add_argument("--stale-pages", type=int, default=5, help="Incremental mode: stop after N consecutive pages with no new games (default: 5, use 0 to disable)")
    sync_parser.add_argument(
        "--no-auto-review-refresh",
        action="store_true",
        help="Disable automatic post-sync refresh of recent existing games",
    )
    sync_parser.add_argument(
        "--review-refresh-days",
        type=int,
        default=SyncOrchestrator.AUTO_REVIEW_REFRESH_DAYS,
        help="Auto-refresh reviews for games released/added in last N days (default: 14)",
    )
    sync_parser.add_argument(
        "--review-refresh-limit",
        type=int,
        default=SyncOrchestrator.AUTO_REVIEW_REFRESH_LIMIT,
        help="Optional cap for auto-refresh game count (default: no cap)",
    )
    sync_parser.add_argument(
        "--review-refresh-min-hours",
        type=int,
        default=SyncOrchestrator.AUTO_REVIEW_REFRESH_MIN_HOURS,
        help="Skip auto-refresh for games synced within N hours (default: 6)",
    )

    # Match command
    match_parser = subparsers.add_parser("match", help="Match games to Steam/Metacritic IDs")
    match_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    match_parser.add_argument("--days", type=int, help="Only process games released in the last N days")

    # Steam-only import command
    import_steam_parser = subparsers.add_parser(
        "import-steam-game",
        help="Import a game directly from Steam, even without OpenCritic coverage",
    )
    import_steam_parser.add_argument("--app-id", type=int, help="Steam app ID to import")
    import_steam_parser.add_argument("--query", type=str, help="Steam store search query to resolve and import")

    # Steam command
    steam_parser = subparsers.add_parser(
        "steam",
        help="Sync Steam user scores and public Steam activity",
    )
    steam_parser.add_argument("--app-id", type=int, help="Only process a specific Steam app ID")
    steam_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    steam_parser.add_argument("--days", type=int, help="Only process games released in the last N days")
    steam_parser.add_argument(
        "--with-activity",
        action="store_true",
        help="Also write Steam activity snapshots/current players (default: scores-only to avoid overlap with player-count-scraper mirror)",
    )

    # SteamDB command
    steamdb_parser = subparsers.add_parser(
        "steamdb",
        help="Sync SteamDB peak data only",
    )
    steamdb_parser.add_argument("--app-id", type=int, help="Only process a specific Steam app ID")
    steamdb_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    steamdb_parser.add_argument("--days", type=int, help="Only process games released in the last N days")

    # Game image backfill command
    game_images_parser = subparsers.add_parser("game-images", help="Backfill game images from Steam")
    game_images_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    game_images_parser.add_argument("--days", type=int, help="Only process games released in the last N days")
    game_images_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing game image URLs with Steam header images",
    )

    # Metacritic command
    metacritic_parser = subparsers.add_parser("metacritic", help="Sync Metacritic scores (user + metascore)")
    metacritic_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    metacritic_parser.add_argument("--force", action="store_true", help="Re-sync all games, even already synced ones")
    metacritic_parser.add_argument("--backfill-counts", action="store_true", help="Only re-scrape games missing user rating counts (can combine with --recent)")
    metacritic_parser.add_argument("--status", action="store_true", help="Show sync progress status")
    metacritic_parser.add_argument("--recent", type=int, nargs="?", const=90, default=None, help="Only process games released in the last N days that still need Metacritic sync (default: 90)")
    metacritic_parser.add_argument("--new-only", type=int, nargs="?", const=60, default=None, help="Only process games released in last N days that have never been synced (default: 60)")
    metacritic_parser.add_argument("--stale-days", type=int, default=30, help="Skip games synced within the last N days (default: 30, use 0 to disable)")
    metacritic_parser.add_argument("--title", type=str, help="Only process games whose title contains this text")

    # Disparity command
    disparity_parser = subparsers.add_parser("disparity", help="Calculate disparity snapshots")
    disparity_parser.add_argument("--journalists", action="store_true", help="Only journalists")
    disparity_parser.add_argument("--outlets", action="store_true", help="Only outlets")
    disparity_parser.add_argument("--games", action="store_true", help="Only games")

    # Refresh reviews command
    refresh_parser = subparsers.add_parser("refresh-reviews", help="Re-fetch reviews for recent games")
    refresh_parser.add_argument("--days", type=int, default=90, help="Refresh games released within N days (default: 90)")
    refresh_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    refresh_parser.add_argument("--all", action="store_true", help="Refresh ALL games (full re-sync of reviews)")
    refresh_parser.add_argument(
        "--min-hours-since-last-sync",
        type=int,
        default=None,
        help="Only refresh games whose last review sync is older than N hours",
    )

    # Clear command
    subparsers.add_parser("clear", help="Clear all data from database")

    # Refresh images command
    subparsers.add_parser("refresh-images", help="Refresh image URLs from OpenCritic")

    # Backfill command
    subparsers.add_parser("backfill", help="Backfill denormalized Game columns from UserScore/Review data")

    # Recompute scores command
    recompute_parser = subparsers.add_parser(
        "recompute-scores",
        help="Recompute review score_normalized from score_raw/score_scale",
    )
    recompute_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing to the database",
    )
    recompute_parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of reviews to process per batch (default: 1000)",
    )
    recompute_parser.add_argument(
        "--max-reviews",
        type=int,
        default=None,
        help="Optional cap on number of reviews to process",
    )
    recompute_parser.add_argument(
        "--write-all",
        action="store_true",
        help="Write recomputed values even when unchanged (default is update-only-if-changed)",
    )

    # Merge games command
    merge_parser = subparsers.add_parser("merge-games", help="Merge deprecated games into canonical records (from GAME_MERGES)")
    merge_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")

    # News command
    news_parser = subparsers.add_parser("news", help="Fetch latest gaming news from RSS feeds")
    news_parser.add_argument("--clear", action="store_true", help="Clear all news articles")

    # News backfill command
    news_backfill_parser = subparsers.add_parser("news-backfill", help="Link existing news articles to games by title matching")
    news_backfill_parser.add_argument("--all", action="store_true", help="Process all articles (default: only unlinked)")
    news_backfill_parser.add_argument("--relink", action="store_true", help="With --all, update existing game links when a better match is found")
    news_backfill_parser.add_argument("--days", type=int, help="Only process articles from the last N days")
    news_backfill_parser.add_argument("--limit", type=int, help="Limit number of articles to process")
    news_backfill_parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing to DB")

    taxonomy_backfill_parser = subparsers.add_parser(
        "taxonomy-backfill",
        help="Refresh raw taxonomy labels and canonical game taxonomy",
    )
    taxonomy_backfill_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    taxonomy_backfill_parser.add_argument(
        "--source",
        choices=["opencritic", "steam", "metacritic"],
        help="Only refresh one taxonomy source",
    )
    taxonomy_backfill_parser.add_argument("--limit", type=int, help="Limit number of games processed")

    description_backfill_parser = subparsers.add_parser(
        "description-backfill",
        help="Refresh source-specific descriptions and taxonomy V2 text corpus",
    )
    description_backfill_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    description_backfill_parser.add_argument(
        "--source",
        choices=["opencritic", "steam", "metacritic"],
        help="Only refresh one source",
    )
    description_backfill_parser.add_argument("--limit", type=int, help="Limit number of games processed")

    taxonomy_audit_parser = subparsers.add_parser(
        "taxonomy-audit",
        help="Show raw taxonomy labels that do not map to canonical facets",
    )
    taxonomy_audit_parser.add_argument(
        "--source",
        choices=["opencritic", "steam", "metacritic"],
        help="Only audit one source",
    )
    taxonomy_audit_parser.add_argument("--limit", type=int, default=50, help="Max rows to print")

    similar_debug_parser = subparsers.add_parser(
        "similar-debug",
        help="Explain why a game does or does not qualify for similar games",
    )
    similar_debug_parser.add_argument("--game", required=True, help="Game public_id or numeric ID")
    similar_debug_parser.add_argument("--limit", type=int, default=10, help="Max matches to print")

    taxonomy_v2_backfill_parser = subparsers.add_parser(
        "taxonomy-v2-backfill",
        help="Compute and store Similar Games Taxonomy V2 fingerprints",
    )
    taxonomy_v2_backfill_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    taxonomy_v2_backfill_parser.add_argument("--limit", type=int, help="Limit number of games processed")

    taxonomy_v2_debug_parser = subparsers.add_parser(
        "taxonomy-v2-debug",
        help="Explain the computed Similar Games Taxonomy V2 fingerprint for a game",
    )
    taxonomy_v2_debug_parser.add_argument("--game", required=True, help="Game public_id or numeric ID")
    taxonomy_v2_debug_parser.add_argument(
        "--compare",
        type=str,
        help="Optional second game public_id, numeric ID, or title to compare pairwise similarity against",
    )
    taxonomy_v2_debug_parser.add_argument("--limit", type=int, default=5, help="Max archetype candidates to print")
    taxonomy_v2_debug_parser.add_argument(
        "--evidence-limit",
        type=int,
        default=20,
        help="Max evidence rows to print",
    )
    taxonomy_v2_debug_parser.add_argument(
        "--persist",
        action="store_true",
        help="Write the computed V2 fingerprint and evidence back to the database",
    )

    taxonomy_v2_label_audit_parser = subparsers.add_parser(
        "taxonomy-v2-label-audit",
        help="Audit grouped raw labels against the Similar Games Taxonomy V2 extractor",
    )
    taxonomy_v2_label_audit_parser.add_argument(
        "--source",
        choices=["opencritic", "steam", "metacritic"],
        help="Only audit one source",
    )
    taxonomy_v2_label_audit_parser.add_argument("--facet", help="Only audit one stored facet")
    taxonomy_v2_label_audit_parser.add_argument("--min-count", type=int, default=5, help="Min games per grouped label")
    taxonomy_v2_label_audit_parser.add_argument("--limit", type=int, default=50, help="Max rows to print")
    taxonomy_v2_label_audit_parser.add_argument(
        "--show-mapped",
        action="store_true",
        help="Also print top mapped labels and emitted signals",
    )

    taxonomy_v2_text_audit_parser = subparsers.add_parser(
        "taxonomy-v2-text-audit",
        help="Audit recurring phrases in stored Similar Games Taxonomy V2 text corpora",
    )
    taxonomy_v2_text_audit_parser.add_argument(
        "--status",
        nargs="+",
        choices=["pending", "computed", "curated", "hidden", "failed", "needs_review"],
        help="Only audit one or more V2 statuses",
    )
    taxonomy_v2_text_audit_parser.add_argument("--ngram", type=int, default=3, help="Phrase length in words")
    taxonomy_v2_text_audit_parser.add_argument("--min-count", type=int, default=10, help="Min games per phrase")
    taxonomy_v2_text_audit_parser.add_argument("--limit", type=int, default=25, help="Max phrases per status")
    taxonomy_v2_text_audit_parser.add_argument("--limit-games", type=int, help="Limit number of games scanned")
    taxonomy_v2_text_audit_parser.add_argument(
        "--include-boilerplate",
        action="store_true",
        help="Include phrases from segments that look like storefront boilerplate",
    )

    taxonomy_v2_near_miss_audit_parser = subparsers.add_parser(
        "taxonomy-v2-near-miss-audit",
        help="Audit closest archetype misses for Similar Games Taxonomy V2 fingerprints",
    )
    taxonomy_v2_near_miss_audit_parser.add_argument(
        "--status",
        nargs="+",
        default=["hidden"],
        choices=["pending", "computed", "curated", "hidden", "failed", "needs_review"],
        help="Audit one or more V2 statuses",
    )
    taxonomy_v2_near_miss_audit_parser.add_argument("--limit", type=int, default=15, help="Max summary rows to print")
    taxonomy_v2_near_miss_audit_parser.add_argument("--examples", type=int, default=10, help="Max examples to print")
    taxonomy_v2_near_miss_audit_parser.add_argument(
        "--candidate-depth",
        type=int,
        default=3,
        help="How many near-miss archetypes to evaluate per game",
    )
    taxonomy_v2_near_miss_audit_parser.add_argument("--limit-games", type=int, help="Limit number of games scanned")

    taxonomy_v2_boilerplate_audit_parser = subparsers.add_parser(
        "taxonomy-v2-boilerplate-audit",
        help="Audit recurring storefront boilerplate in Similar Games Taxonomy V2 text corpora",
    )
    taxonomy_v2_boilerplate_audit_parser.add_argument(
        "--status",
        nargs="+",
        choices=["pending", "computed", "curated", "hidden", "failed", "needs_review"],
        help="Only audit one or more V2 statuses",
    )
    taxonomy_v2_boilerplate_audit_parser.add_argument("--min-count", type=int, default=5, help="Min games per snippet")
    taxonomy_v2_boilerplate_audit_parser.add_argument("--limit", type=int, default=25, help="Max rows to print")
    taxonomy_v2_boilerplate_audit_parser.add_argument("--limit-games", type=int, help="Limit number of games scanned")

    taxonomy_v2_confusion_audit_parser = subparsers.add_parser(
        "taxonomy-v2-confusion-audit",
        help="Audit Similar Games Taxonomy V2 family/archetype coverage and common pairings",
    )
    taxonomy_v2_confusion_audit_parser.add_argument(
        "--status",
        nargs="+",
        choices=["pending", "computed", "curated", "hidden", "failed", "needs_review"],
        help="Only audit one or more V2 statuses",
    )
    taxonomy_v2_confusion_audit_parser.add_argument("--limit", type=int, default=25, help="Max rows to print")
    taxonomy_v2_confusion_audit_parser.add_argument("--limit-games", type=int, help="Limit number of games scanned")

    taxonomy_v2_gold_set_audit_parser = subparsers.add_parser(
        "taxonomy-v2-gold-set-audit",
        help="Audit live Similar Games Taxonomy V2 output against the curated gold set",
    )
    taxonomy_v2_gold_set_audit_parser.add_argument("--limit", type=int, default=5, help="Max neighbors per anchor")
    taxonomy_v2_gold_set_audit_parser.add_argument("--limit-games", type=int, help="Limit number of anchors evaluated")

    similarity_v3_corpus_parser = subparsers.add_parser(
        "similarity-v3-corpus",
        help="Build Similar Games V3 corpus rows and embeddings",
    )
    similarity_v3_corpus_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    similarity_v3_corpus_parser.add_argument("--limit", type=int, help="Limit number of games processed")
    similarity_v3_corpus_parser.add_argument(
        "--dirty-only",
        action="store_true",
        help="Only process games marked dirty or on an older V3 version",
    )

    similarity_v3_embed_parser = subparsers.add_parser(
        "similarity-v3-embed",
        help="Refresh Similar Games V3 embeddings for target games",
    )
    similarity_v3_embed_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    similarity_v3_embed_parser.add_argument("--limit", type=int, help="Limit number of games processed")
    similarity_v3_embed_parser.add_argument(
        "--dirty-only",
        action="store_true",
        help="Only process games marked dirty or on an older V3 version",
    )

    similarity_v3_neighbors_parser = subparsers.add_parser(
        "similarity-v3-neighbors",
        help="Preview Similar Games V3 ranked neighbors",
    )
    similarity_v3_neighbors_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    similarity_v3_neighbors_parser.add_argument("--limit", type=int, default=5, help="Max neighbors to print")
    similarity_v3_neighbors_parser.add_argument("--limit-games", type=int, help="Limit number of anchors evaluated")
    similarity_v3_neighbors_parser.add_argument(
        "--dirty-only",
        action="store_true",
        help="Only process games marked dirty or on an older V3 version",
    )

    similarity_v3_publish_parser = subparsers.add_parser(
        "similarity-v3-publish",
        help="Publish Similar Games V3 neighbors for serving",
    )
    similarity_v3_publish_parser.add_argument("--game", type=str, help="Specific game public_id or numeric ID")
    similarity_v3_publish_parser.add_argument("--limit", type=int, default=10, help="Max neighbors to publish")
    similarity_v3_publish_parser.add_argument("--limit-games", type=int, help="Limit number of anchors evaluated")
    similarity_v3_publish_parser.add_argument(
        "--dirty-only",
        action="store_true",
        help="Only process games marked dirty or on an older V3 version",
    )

    similarity_v3_gold_audit_parser = subparsers.add_parser(
        "similarity-v3-gold-audit",
        help="Audit Similar Games V3 against the gold set",
    )
    similarity_v3_gold_audit_parser.add_argument("--limit", type=int, default=5, help="Max neighbors per anchor")

    similarity_v3_confusion_audit_parser = subparsers.add_parser(
        "similarity-v3-confusion-audit",
        help="Audit Similar Games V3 relationship distribution",
    )
    similarity_v3_confusion_audit_parser.add_argument("--limit", type=int, default=25, help="Max rows to print")
    similarity_v3_confusion_audit_parser.add_argument(
        "--include-same",
        action="store_true",
        help="Include same-archetype rows in the confusion output",
    )

    similarity_v3_hidden_audit_parser = subparsers.add_parser(
        "similarity-v3-hidden-audit",
        help="Audit Similar Games V3 hidden states",
    )
    similarity_v3_hidden_audit_parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Include hidden rows from older Similar Games V3 versions",
    )

    queue_job_parser = subparsers.add_parser(
        "queue-job",
        help="Enqueue a background worker job onto the Dramatiq queues",
    )
    queue_job_parser.add_argument(
        "job",
        choices=[
            "sync-opencritic-full",
            "sync-opencritic-incremental",
            "sync-steam",
            "sync-metacritic",
            "match-games",
            "disparity-snapshots",
            "taxonomy-v2-backfill",
            "similarity-v3-corpus",
            "similarity-v3-publish",
            "similarity-v3-pipeline",
        ],
        help="Queued job to enqueue",
    )
    queue_job_parser.add_argument("--game", type=str, help="Specific game public_id, numeric ID, or title")
    queue_job_parser.add_argument("--limit", type=int, help="Limit number of games processed")
    queue_job_parser.add_argument("--limit-games", type=int, help="Limit number of anchors/games processed")
    queue_job_parser.add_argument("--publish-limit", type=int, default=10, help="Max neighbors to publish")
    queue_job_parser.add_argument("--taxonomy-limit", type=int, help="Limit number of games for taxonomy backfill")
    queue_job_parser.add_argument("--snapshot-date", type=str, help="Optional snapshot date for disparity jobs")
    queue_job_parser.add_argument(
        "--dirty-only",
        action="store_true",
        help="For V3 jobs, only process games marked dirty or on an older version",
    )
    queue_job_parser.add_argument(
        "--publish-dirty-only",
        action="store_true",
        help="For similarity-v3-pipeline, only publish dirty games",
    )
    queue_job_parser.add_argument(
        "--taxonomy-backfill",
        action="store_true",
        help="For similarity-v3-pipeline, run taxonomy-v2-backfill before corpus/publish",
    )
    queue_job_parser.add_argument(
        "--run-gold-audit",
        action="store_true",
        help="For similarity-v3-pipeline, run the gold audit after publish",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Run the appropriate async command
    if args.command == "sync":
        return asyncio.run(cmd_sync(args))
    elif args.command == "match":
        return asyncio.run(cmd_match(args))
    elif args.command == "import-steam-game":
        return asyncio.run(cmd_import_steam_game(args))
    elif args.command == "steam":
        return asyncio.run(cmd_steam(args))
    elif args.command == "steamdb":
        return asyncio.run(cmd_steamdb(args))
    elif args.command == "game-images":
        return asyncio.run(cmd_game_images(args))
    elif args.command == "metacritic":
        return asyncio.run(cmd_metacritic(args))
    elif args.command == "disparity":
        return asyncio.run(cmd_disparity(args))
    elif args.command == "refresh-reviews":
        return asyncio.run(cmd_refresh_reviews(args))
    elif args.command == "clear":
        return asyncio.run(cmd_clear(args))
    elif args.command == "refresh-images":
        return asyncio.run(cmd_refresh_images(args))
    elif args.command == "backfill":
        return asyncio.run(cmd_backfill_game_columns(args))
    elif args.command == "recompute-scores":
        return asyncio.run(cmd_recompute_scores(args))
    elif args.command == "merge-games":
        return asyncio.run(cmd_merge_games(args))
    elif args.command == "news":
        return asyncio.run(cmd_news(args))
    elif args.command == "news-backfill":
        return asyncio.run(cmd_news_backfill(args))
    elif args.command == "taxonomy-backfill":
        return asyncio.run(cmd_taxonomy_backfill(args))
    elif args.command == "description-backfill":
        return asyncio.run(cmd_description_backfill(args))
    elif args.command == "taxonomy-audit":
        return asyncio.run(cmd_taxonomy_audit(args))
    elif args.command == "similar-debug":
        return asyncio.run(cmd_similar_debug(args))
    elif args.command == "taxonomy-v2-backfill":
        return asyncio.run(cmd_taxonomy_v2_backfill(args))
    elif args.command == "taxonomy-v2-debug":
        return asyncio.run(cmd_taxonomy_v2_debug(args))
    elif args.command == "taxonomy-v2-label-audit":
        return asyncio.run(cmd_taxonomy_v2_label_audit(args))
    elif args.command == "taxonomy-v2-text-audit":
        return asyncio.run(cmd_taxonomy_v2_text_audit(args))
    elif args.command == "taxonomy-v2-near-miss-audit":
        return asyncio.run(cmd_taxonomy_v2_near_miss_audit(args))
    elif args.command == "taxonomy-v2-boilerplate-audit":
        return asyncio.run(cmd_taxonomy_v2_boilerplate_audit(args))
    elif args.command == "taxonomy-v2-confusion-audit":
        return asyncio.run(cmd_taxonomy_v2_confusion_audit(args))
    elif args.command == "taxonomy-v2-gold-set-audit":
        return asyncio.run(cmd_taxonomy_v2_gold_set_audit(args))
    elif args.command == "similarity-v3-corpus":
        return asyncio.run(cmd_similarity_v3_corpus(args))
    elif args.command == "similarity-v3-embed":
        return asyncio.run(cmd_similarity_v3_embed(args))
    elif args.command == "similarity-v3-neighbors":
        return asyncio.run(cmd_similarity_v3_neighbors(args))
    elif args.command == "similarity-v3-publish":
        return asyncio.run(cmd_similarity_v3_publish(args))
    elif args.command == "similarity-v3-gold-audit":
        return asyncio.run(cmd_similarity_v3_gold_audit(args))
    elif args.command == "similarity-v3-confusion-audit":
        return asyncio.run(cmd_similarity_v3_confusion_audit(args))
    elif args.command == "similarity-v3-hidden-audit":
        return asyncio.run(cmd_similarity_v3_hidden_audit(args))
    elif args.command == "queue-job":
        return cmd_enqueue_job(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)

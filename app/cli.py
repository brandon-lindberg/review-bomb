#!/usr/bin/env python3
"""
CLI for managing the Game Journalist Review Disparity Tracker.

Usage:
    python -m app sync              Run OpenCritic sync (fast incremental tail scan)
    python -m app sync --status     Show sync status and progress
    python -m app sync --reset      Reset sync state (start fresh)
    python -m app sync --full-scan  Force full OpenCritic catalog sweep
    python -m app match             Match games to Steam/Metacritic IDs
    python -m app match --days 180  Match only games released in last 180 days
    python -m app steam             Sync Steam user scores
    python -m app steam --days 30   Sync Steam scores for games released in last 30 days
    python -m app metacritic        Sync Metacritic scores (skips recently synced games)
    python -m app metacritic --recent  Sync only games released in last 90 days
    python -m app disparity         Calculate disparity snapshots
    python -m app refresh-reviews   Re-fetch reviews for recent games (last 90 days)
    python -m app clear             Clear all data from database
    python -m app backfill          Backfill denormalized Game columns from UserScore/Review data
    python -m app merge-games       Merge deprecated games into canonical records
    python -m app news              Fetch latest gaming news from RSS feeds
    python -m app news-backfill     Link existing news articles to games by title matching
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone, timedelta

from app.database import async_session_maker
from app.services.sync_orchestrator import SyncOrchestrator, run_daily_sync, get_sync_status


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
        print(f"{'='*50}\n")

        try:
            stats = await orchestrator.run_daily_sync(
                full_scan=args.full_scan,
                stale_pages_before_stop=args.stale_pages,
            )
            print(f"\n{'='*50}")
            print("Sync completed successfully!")
            print(f"{'='*50}")
            return 0
        except Exception as e:
            print(f"\nSync failed: {e}")
            return 1


async def cmd_steam(args):
    """Handle Steam sync command."""
    from app.services.steam import SteamService
    from app.models.models import Game, UserScore, UserScoreSource
    from sqlalchemy import select, and_, or_, func
    from datetime import timedelta
    from difflib import SequenceMatcher
    import re

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

    async with async_session_maker() as db:
        min_recent_add_window_days = 14
        recent_opencritic_id_window = 300
        # Get all games with Steam app IDs
        query = select(Game).where(Game.steam_app_id.isnot(None))
        mode = "with Steam IDs"
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
        result = await db.execute(query)
        games = result.scalars().all()

        print(f"Found {len(games)} games {mode}")

        if args.limit:
            games = games[:args.limit]
            print(f"Processing first {args.limit} games")

        synced = 0
        processed = 0
        failed = 0
        no_score = 0
        skipped_upcoming = 0
        skipped_invalid_app = 0
        skipped_mismatch = 0

        async with SteamService() as service:
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

                    steam_title = (app_details.get("name") or "").strip()
                    release_info = app_details.get("release_date") or {}
                    release_raw = release_info.get("date") or "unknown"

                    # Cross-reference mapped app title before pulling score.
                    if steam_title:
                        similarity = title_similarity(game.title, steam_title)
                        if similarity < 0.55:
                            print(
                                f"  Skip: likely wrong app mapping "
                                f"(similarity={similarity:.2f}, steam_title='{steam_title}')"
                            )
                            skipped_mismatch += 1

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
            f"{skipped_invalid_app} invalid app IDs, {skipped_mismatch} mapping mismatches, "
            f"{failed} failed, {processed} processed"
        )


async def cmd_metacritic(args):
    """Handle Metacritic sync command."""
    import asyncio
    import time
    from app.services.metacritic import MetacriticService
    from app.models.models import Game, UserScore, UserScoreSource
    from sqlalchemy import select, func, delete, or_, and_
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

        # Reuse "needs sync" logic across modes.
        games_with_user_score = (
            select(UserScore.game_id)
            .where(UserScore.source == UserScoreSource.METACRITIC)
            .distinct()
            .scalar_subquery()
        )
        needs_sync_condition = or_(
            Game.metacritic_score.is_(None),
            and_(
                Game.metacritic_score.isnot(None),
                Game.id.notin_(games_with_user_score),
            ),
        )
        max_opencritic_id_subq = select(func.max(Game.opencritic_id)).scalar_subquery()
        recent_opencritic_condition = and_(
            Game.opencritic_id.isnot(None),
            Game.opencritic_id >= (max_opencritic_id_subq - recent_opencritic_id_window),
        )

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
            # Only process recent games that still need Metacritic data.
            days = args.recent
            now = datetime.now(timezone.utc)
            cutoff_date = (now - timedelta(days=days)).date()
            created_cutoff_date = (now - timedelta(days=min_recent_add_window_days)).date()
            created_cutoff_dt = datetime.combine(
                created_cutoff_date,
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            query = select(Game).where(
                Game.metacritic_slug.isnot(None),
                needs_sync_condition,
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
                f'released in last {days} days, or added in last '
                f'{min_recent_add_window_days} days, or in recent OpenCritic ID window and needing'
            )
        elif args.new_only is not None:
            # Only process recently released games that have never been synced from Metacritic
            days = args.new_only
            now = datetime.now(timezone.utc)
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
            # Sync games that either: have no metascore yet, OR have a metascore but no user score
            query = select(Game).where(
                Game.metacritic_slug.isnot(None),
                needs_sync_condition,
            )

            # Apply stale-days filter: skip games synced recently
            stale_days = args.stale_days
            if stale_days > 0:
                stale_cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
                query = query.where(
                    or_(
                        Game.metacritic_synced_at.is_(None),
                        Game.metacritic_synced_at < stale_cutoff,
                    )
                )

            mode = 'needing'
        result = await db.execute(query)
        games = result.scalars().all()
        print(f"Found {len(games)} games {mode} Metacritic sync")

        if args.limit:
            games = games[:args.limit]
            print(f"Processing first {args.limit} games")

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
                        service.get_scores(game.metacritic_slug),
                        timeout=per_game_timeout_seconds,
                    )

                    if not score_data:
                        print(f"  No data returned from Metacritic")

                    if score_data:
                        updated_anything = False

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
        print(f"  Matched: {stats['matched']}")
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
                    Review.score_normalized > 0,
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
    from sqlalchemy import text, select, func

    from app.models.models import Game, NewsArticle
    from app.services.news_rss import NewsRSSService
    from app.services.news_matcher import NewsMatcher
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

        inserted = 0
        matched = 0
        for article in articles:
            game_id = matcher.match(article["title"], article.get("description"))
            if game_id:
                article["game_id"] = game_id
                matched += 1
            stmt = pg_insert(NewsArticle).values(**article)
            stmt = stmt.on_conflict_do_nothing(index_elements=["url"])
            result = await db.execute(stmt)
            if result.rowcount > 0:
                inserted += 1

        await db.commit()

        total_result = await db.execute(
            select(func.count()).select_from(NewsArticle)
        )
        total = total_result.scalar() or 0

        # Invalidate news cache so the API serves fresh data
        if inserted > 0:
            from app.cache import delete_cached, close_redis
            deleted_keys = await delete_cached("news:*")
            print(f"Cleared {deleted_keys} cached news entries")
            await close_redis()

        print(f"\nNews sync complete: {inserted} new articles inserted, {matched} matched to games ({total} total in database)")


async def cmd_news_backfill(args):
    """Backfill game_id on existing news articles by matching titles."""
    from sqlalchemy import select

    from app.models.models import Game, NewsArticle
    from app.services.news_matcher import NewsMatcher
    from app.cache import delete_cached, close_redis

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
        unchanged = 0
        unmatched = 0
        pending_changes = 0

        if args.relink and not args.all:
            print("Note: --relink has no effect without --all")

        for i, article in enumerate(articles):
            matched_game_id = matcher.match(article.title, article.description)
            if not matched_game_id:
                unmatched += 1
            elif article.game_id is None:
                linked_new += 1
                if not args.dry_run:
                    article.game_id = matched_game_id
                    pending_changes += 1
            elif article.game_id != matched_game_id:
                if args.all and args.relink:
                    relinked += 1
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
                    f"(new links: {linked_new}, relinked: {relinked})"
                )

        if pending_changes and not args.dry_run:
            await db.commit()

        changed = linked_new + relinked
        if changed > 0 and not args.dry_run:
            deleted_keys = await delete_cached("news:*")
            print(f"Cleared {deleted_keys} cached news entries")
            await close_redis()

        print("\nBackfill complete:")
        print(f"  Processed: {len(articles)}")
        print(f"  Newly linked: {linked_new}")
        print(f"  Relinked: {relinked}")
        print(f"  Unchanged: {unchanged}")
        print(f"  Unmatched: {unmatched}")
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

    # Match command
    match_parser = subparsers.add_parser("match", help="Match games to Steam/Metacritic IDs")
    match_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    match_parser.add_argument("--days", type=int, help="Only process games released in the last N days")

    # Steam command
    steam_parser = subparsers.add_parser("steam", help="Sync Steam user scores")
    steam_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    steam_parser.add_argument("--days", type=int, help="Only process games released in the last N days")

    # Metacritic command
    metacritic_parser = subparsers.add_parser("metacritic", help="Sync Metacritic scores (user + metascore)")
    metacritic_parser.add_argument("--limit", type=int, help="Limit number of games to process")
    metacritic_parser.add_argument("--force", action="store_true", help="Re-sync all games, even already synced ones")
    metacritic_parser.add_argument("--backfill-counts", action="store_true", help="Only re-scrape games missing user rating counts (can combine with --recent)")
    metacritic_parser.add_argument("--status", action="store_true", help="Show sync progress status")
    metacritic_parser.add_argument("--recent", type=int, nargs="?", const=90, default=None, help="Only process games released in the last N days that still need Metacritic sync (default: 90)")
    metacritic_parser.add_argument("--new-only", type=int, nargs="?", const=60, default=None, help="Only process games released in last N days that have never been synced (default: 60)")
    metacritic_parser.add_argument("--stale-days", type=int, default=30, help="Skip games synced within the last N days (default: 30, use 0 to disable)")

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

    # Clear command
    subparsers.add_parser("clear", help="Clear all data from database")

    # Refresh images command
    subparsers.add_parser("refresh-images", help="Refresh image URLs from OpenCritic")

    # Backfill command
    subparsers.add_parser("backfill", help="Backfill denormalized Game columns from UserScore/Review data")

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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Run the appropriate async command
    if args.command == "sync":
        return asyncio.run(cmd_sync(args))
    elif args.command == "match":
        return asyncio.run(cmd_match(args))
    elif args.command == "steam":
        return asyncio.run(cmd_steam(args))
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
    elif args.command == "merge-games":
        return asyncio.run(cmd_merge_games(args))
    elif args.command == "news":
        return asyncio.run(cmd_news(args))
    elif args.command == "news-backfill":
        return asyncio.run(cmd_news_backfill(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)

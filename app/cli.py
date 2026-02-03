#!/usr/bin/env python3
"""
CLI for managing the Game Journalist Review Disparity Tracker.

Usage:
    python -m app sync              Run OpenCritic sync (fetches all games)
    python -m app sync --status     Show sync status and progress
    python -m app sync --reset      Reset sync state (start fresh)
    python -m app match             Match games to Steam/Metacritic IDs
    python -m app steam             Sync Steam user scores
    python -m app disparity         Calculate disparity snapshots
    python -m app clear             Clear all data from database
"""

import argparse
import asyncio
import sys
from datetime import datetime

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
        print(f"{'='*50}\n")

        try:
            stats = await orchestrator.run_daily_sync()
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
    from sqlalchemy import select

    async with async_session_maker() as db:
        service = SteamService()

        # Get all games with Steam app IDs
        query = select(Game).where(Game.steam_app_id.isnot(None))
        result = await db.execute(query)
        games = result.scalars().all()

        print(f"Found {len(games)} games with Steam IDs")

        if args.limit:
            games = games[:args.limit]
            print(f"Processing first {args.limit} games")

        synced = 0
        failed = 0

        for game in games:
            try:
                print(f"Fetching Steam score for: {game.title}...")
                score_data = await service.get_user_score(game.steam_app_id)

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

                # Commit every 10 games
                if synced % 10 == 0:
                    await db.commit()

            except Exception as e:
                print(f"  Error: {e}")
                failed += 1

        await db.commit()
        print(f"\nSteam sync complete: {synced} synced, {failed} failed")


async def cmd_disparity(args):
    """Handle disparity calculation command."""
    from app.services.disparity import DisparityCalculator

    async with async_session_maker() as db:
        calculator = DisparityCalculator(db)

        print("Calculating disparity snapshots...")

        if args.journalists:
            print("\nProcessing journalists...")
            count = await calculator.generate_journalist_snapshots()
            print(f"Created {count} journalist snapshots.")

        if args.outlets:
            print("\nProcessing outlets...")
            count = await calculator.generate_outlet_snapshots()
            print(f"Created {count} outlet snapshots.")

        if args.games:
            print("\nProcessing games...")
            count = await calculator.generate_game_snapshots()
            print(f"Created {count} game snapshots.")

        if not (args.journalists or args.outlets or args.games):
            # Calculate all by default
            print("\nGenerating all snapshots...")
            results = await calculator.generate_all_snapshots()
            print(f"Created snapshots: {results['journalists']} journalists, {results['outlets']} outlets, {results['games']} games")


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


async def cmd_match(args):
    """Handle game matching command."""
    async with async_session_maker() as db:
        orchestrator = SyncOrchestrator(db)

        print(f"\n{'='*50}")
        print("Matching games to Steam/Metacritic")
        print(f"{'='*50}\n")

        stats = await orchestrator.match_games_to_steam(limit=args.limit)

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

    # Match command
    match_parser = subparsers.add_parser("match", help="Match games to Steam/Metacritic IDs")
    match_parser.add_argument("--limit", type=int, help="Limit number of games to process")

    # Steam command
    steam_parser = subparsers.add_parser("steam", help="Sync Steam user scores")
    steam_parser.add_argument("--limit", type=int, help="Limit number of games to process")

    # Disparity command
    disparity_parser = subparsers.add_parser("disparity", help="Calculate disparity snapshots")
    disparity_parser.add_argument("--journalists", action="store_true", help="Only journalists")
    disparity_parser.add_argument("--outlets", action="store_true", help="Only outlets")
    disparity_parser.add_argument("--games", action="store_true", help="Only games")

    # Clear command
    subparsers.add_parser("clear", help="Clear all data from database")

    # Refresh images command
    subparsers.add_parser("refresh-images", help="Refresh image URLs from OpenCritic")

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
    elif args.command == "disparity":
        return asyncio.run(cmd_disparity(args))
    elif args.command == "clear":
        return asyncio.run(cmd_clear(args))
    elif args.command == "refresh-images":
        return asyncio.run(cmd_refresh_images(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)

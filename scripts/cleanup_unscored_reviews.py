#!/usr/bin/env python3
"""
One-time script to clean up reviews that were incorrectly assigned scores.

Run from the backend directory:
    python scripts/cleanup_unscored_reviews.py
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import async_session_maker
from app.models.models import Review, Outlet


async def cleanup_unscored_reviews():
    """Clean up reviews with invalid scores."""
    async with async_session_maker() as db:
        print("Starting review cleanup...")

        # Outlets known to use recommendation-based scoring (not numeric scores)
        # OpenCritic converts their recommendations to fake 100 scores
        recommendation_outlets = {
            "kotaku",
            "rock paper shotgun",
            "rock, paper, shotgun",
            "eurogamer",  # Uses "Recommended" / "Essential" / "Avoid"
            "polygon",  # Uses recommendation badges
        }

        # Build a set of outlet IDs that use recommendation-based scoring
        outlet_query = select(Outlet)
        outlet_result = await db.execute(outlet_query)
        outlets = outlet_result.scalars().all()

        recommendation_outlet_ids = set()
        for outlet in outlets:
            if outlet.name.lower() in recommendation_outlets:
                recommendation_outlet_ids.add(outlet.id)
                print(f"  Found recommendation-based outlet: {outlet.name} (ID: {outlet.id})")

        # Text-based "scores" that should not be normalized
        unscored_values = {
            # Explicit unscored indicators
            "n/a", "tbd", "unscored", "-", "", "na", "none", "no score",
            # Recommendation-based systems (not numeric scores)
            "recommended", "not recommended", "yes", "no",
            "buy", "buy it", "don't buy", "skip", "skip it",
            "essential", "must-play", "must play", "avoid",
            "worth playing", "worth it", "not worth it",
            # Award/badge systems
            "editors' choice", "editor's choice", "editors choice",
            "platinum", "gold", "silver", "bronze",
            # Thumbs systems
            "thumbs up", "thumbs down",
            # Numeric values that are likely fake (10 = "Recommended" converted to score)
            "10", "10.0",
        }

        # Get all reviews with scores
        query = select(Review).where(Review.score_normalized.isnot(None))
        result = await db.execute(query)
        reviews = result.scalars().all()

        print(f"Checking {len(reviews)} reviews...")

        fixed_count = 0
        for review in reviews:
            raw = (review.score_raw or "").strip().lower()

            should_nullify = False
            reason = ""

            # Check if from a recommendation-based outlet
            if review.outlet_id in recommendation_outlet_ids:
                should_nullify = True
                reason = f"recommendation-based outlet (outlet_id={review.outlet_id})"
            # Check against known unscored values
            elif raw in unscored_values:
                should_nullify = True
                reason = f"raw='{raw}'"
            # Check if normalized score is 0 (indicates unscored)
            elif review.score_normalized == 0:
                should_nullify = True
                reason = "score_normalized=0"
            # Check for suspicious 100 scores on non-100 scales
            elif review.score_normalized == 100 and review.score_scale not in ("100", None):
                try:
                    if float(raw) == 10 and review.score_scale == "10":
                        should_nullify = True
                        reason = "suspicious 10/10 (likely 'Recommended')"
                except ValueError:
                    should_nullify = True
                    reason = f"non-numeric raw '{raw}' with score 100"

            if should_nullify:
                print(f"  Nullifying review {review.id}: {reason}")
                review.score_normalized = None
                fixed_count += 1

        await db.commit()
        print(f"\nCleanup complete: nullified scores for {fixed_count} reviews")


if __name__ == "__main__":
    asyncio.run(cleanup_unscored_reviews())

"""Stats API endpoints."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Journalist, Outlet, Game, Review, DisparitySnapshot
from app.schemas.schemas import SiteStats

router = APIRouter()


@router.get("", response_model=SiteStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get site-wide statistics."""
    # Count journalists
    journalist_count_query = select(func.count()).select_from(Journalist)
    journalist_result = await db.execute(journalist_count_query)
    total_journalists = journalist_result.scalar() or 0

    # Count outlets
    outlet_count_query = select(func.count()).select_from(Outlet)
    outlet_result = await db.execute(outlet_count_query)
    total_outlets = outlet_result.scalar() or 0

    # Count games
    game_count_query = select(func.count()).select_from(Game)
    game_result = await db.execute(game_count_query)
    total_games = game_result.scalar() or 0

    # Count reviews
    review_count_query = select(func.count()).select_from(Review)
    review_result = await db.execute(review_count_query)
    total_reviews = review_result.scalar() or 0

    # Calculate site-wide average disparity from journalist snapshots
    avg_disparity_query = (
        select(func.avg(DisparitySnapshot.avg_disparity_combined))
        .where(DisparitySnapshot.journalist_id.isnot(None))
    )
    avg_disparity_result = await db.execute(avg_disparity_query)
    avg_disparity = avg_disparity_result.scalar()

    return SiteStats(
        total_journalists=total_journalists,
        total_outlets=total_outlets,
        total_games=total_games,
        total_reviews=total_reviews,
        avg_disparity_site=Decimal(str(round(avg_disparity, 2))) if avg_disparity else None,
        last_updated=datetime.utcnow(),
    )

"""Internal endpoints consumed by sibling services (not by the public UI).

These endpoints intentionally bypass the public list filters so the
player-count-scraper can register every game with a Steam app ID, including
brand-new releases that have not yet attracted reviews.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import Game

router = APIRouter()


def verify_scraper_token(authorization: Optional[str] = Header(None)) -> None:
    settings = get_settings()
    expected = settings.scraper_api_token
    if not expected:
        # Token not configured: allow (dev/local).
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid scraper token")


@router.get("/tracked-games")
async def list_tracked_games(
    page: int = Query(1, ge=1, le=10000),
    per_page: int = Query(100, ge=1, le=500),
    sort_by: str = Query("release_date", regex="^(release_date|id)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_scraper_token),
):
    base_filter = Game.steam_app_id.isnot(None)

    total = (
        await db.execute(select(func.count()).select_from(Game).where(base_filter))
    ).scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    query = select(Game).where(base_filter)
    if sort_by == "release_date":
        if sort_order == "desc":
            query = query.order_by(
                Game.release_date.desc().nulls_last(),
                Game.id.desc(),
            )
        else:
            query = query.order_by(
                Game.release_date.asc().nulls_last(),
                Game.id.asc(),
            )
    else:
        if sort_order == "desc":
            query = query.order_by(Game.id.desc())
        else:
            query = query.order_by(Game.id.asc())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    games = result.scalars().all()

    items = [
        {
            "id": game.id,
            "public_id": game.public_id,
            "steam_app_id": game.steam_app_id,
            "title": game.title,
            "release_date": game.release_date.isoformat() if game.release_date else None,
        }
        for game in games
    ]

    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }

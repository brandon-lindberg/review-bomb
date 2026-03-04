"""Helpers to build disparity timelines from real review publication dates."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import Date, and_, asc, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.models import Game, Review
from app.schemas.schemas import DisparitySnapshot as DisparitySnapshotSchema


def _as_decimal(value: Optional[Decimal]) -> Decimal:
    if value is None:
        return Decimal("0")
    return value


def _safe_avg(total: Decimal, count: int) -> Optional[Decimal]:
    if count <= 0:
        return None
    return (total / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def build_disparity_timeline_from_reviews(
    db: AsyncSession,
    entity_filter: ColumnElement[bool],
    limit: int = 10000,
) -> list[DisparitySnapshotSchema]:
    """
    Build cumulative disparity history from review publication dates.

    This produces a timeline from first scored review date to latest scored review date,
    which is what charts should represent (instead of ingestion/snapshot run dates).
    """
    review_date_expr = cast(Review.published_at, Date)
    steam_disparity_expr = case(
        (Game.steam_user_score.isnot(None), Review.score_normalized - Game.steam_user_score),
        else_=None,
    )
    metacritic_disparity_expr = case(
        (Game.metacritic_user_score.isnot(None), Review.score_normalized - Game.metacritic_user_score),
        else_=None,
    )
    combined_for_review_expr = case(
        (
            and_(
                steam_disparity_expr.isnot(None),
                metacritic_disparity_expr.isnot(None),
            ),
            (steam_disparity_expr + metacritic_disparity_expr) / 2,
        ),
        (steam_disparity_expr.isnot(None), steam_disparity_expr),
        else_=metacritic_disparity_expr,
    )

    now_utc = datetime.now(timezone.utc)
    query = (
        select(
            review_date_expr.label("timeline_date"),
            func.count(Review.id).label("day_review_count"),
            func.sum(steam_disparity_expr).label("day_steam_sum"),
            func.count(steam_disparity_expr).label("day_steam_count"),
            func.sum(metacritic_disparity_expr).label("day_metacritic_sum"),
            func.count(metacritic_disparity_expr).label("day_metacritic_count"),
            func.sum(combined_for_review_expr).label("day_combined_sum"),
            func.count(combined_for_review_expr).label("day_combined_count"),
        )
        .join(Game, Review.game_id == Game.id)
        .where(
            entity_filter,
            Review.score_normalized.isnot(None),
            Review.published_at.isnot(None),
            Review.published_at <= now_utc,
        )
        .group_by(review_date_expr)
        .order_by(asc(review_date_expr))
    )

    rows = (await db.execute(query)).all()
    if not rows:
        return []

    total_reviews = 0
    steam_sum = Decimal("0")
    steam_count = 0
    metacritic_sum = Decimal("0")
    metacritic_count = 0
    combined_sum = Decimal("0")
    combined_count = 0

    timeline: list[DisparitySnapshotSchema] = []
    for row in rows:
        point_date = row.timeline_date
        if point_date is None:
            continue

        total_reviews += int(row.day_review_count or 0)

        steam_sum += _as_decimal(row.day_steam_sum)
        steam_count += int(row.day_steam_count or 0)

        metacritic_sum += _as_decimal(row.day_metacritic_sum)
        metacritic_count += int(row.day_metacritic_count or 0)

        combined_sum += _as_decimal(row.day_combined_sum)
        combined_count += int(row.day_combined_count or 0)

        timeline.append(
            DisparitySnapshotSchema(
                date=point_date,
                avg_disparity_steam=_safe_avg(steam_sum, steam_count),
                avg_disparity_metacritic=_safe_avg(metacritic_sum, metacritic_count),
                avg_disparity_combined=_safe_avg(combined_sum, combined_count),
                review_count=total_reviews,
            )
        )

    if len(timeline) > limit:
        timeline = timeline[-limit:]

    return timeline

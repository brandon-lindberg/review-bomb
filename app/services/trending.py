"""
Trending score aggregation services.

News is the first provider, but this module is structured so additional
providers (Google Trends, Twitch, etc.) can plug into the same aggregator.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Game, NewsArticle


RECENCY_HALF_LIFE_HOURS = 24.0
MOMENTUM_WINDOW_HOURS = 12

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TOPIC_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "announced",
    "at",
    "best",
    "big",
    "by",
    "date",
    "details",
    "dlc",
    "for",
    "from",
    "game",
    "games",
    "gets",
    "guide",
    "how",
    "in",
    "is",
    "its",
    "launch",
    "new",
    "news",
    "on",
    "our",
    "out",
    "patch",
    "preview",
    "release",
    "report",
    "review",
    "rumor",
    "rumors",
    "shows",
    "the",
    "to",
    "trailer",
    "update",
    "updates",
    "what",
    "when",
    "with",
}


@dataclass
class TrendingSignal:
    """Canonical signal emitted by a provider for one trend entity."""

    trend_key: str
    title: str
    game_id: int | None
    game_public_id: str | None
    release_date: date | None
    image_url: str | None
    is_linked: bool
    is_upcoming: bool
    latest_article_at: datetime | None
    news_mention_count: int
    news_source_count: int
    source_scores: dict[str, float] = field(default_factory=dict)


class TrendingSignalProvider(Protocol):
    """Provider contract for external/internal trend metrics."""

    provider_key: str

    async def collect(
        self,
        db: AsyncSession,
        *,
        now: datetime,
        window_hours: int,
    ) -> list[TrendingSignal]:
        """Collect provider-specific trend signals."""


@dataclass
class _NewsBucket:
    trend_key: str
    title: str
    game_id: int | None
    game_public_id: str | None
    release_date: date | None
    image_url: str | None
    is_linked: bool
    is_upcoming: bool
    latest_article_at: datetime | None = None
    source_names: set[str] = field(default_factory=set)
    mention_count: int = 0
    weighted_mentions: float = 0.0
    recent_window_mentions: int = 0
    prior_window_mentions: int = 0


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clean_article_title(title: str, source_name: str | None) -> str:
    text = (title or "").strip()
    if not text:
        return "Untitled"

    source = (source_name or "").strip()
    if source:
        text = re.sub(
            rf"\s*(?:-|\||:|–|—)\s*{re.escape(source)}\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or "Untitled"


def _topic_key_from_title(title: str) -> str:
    normalized = _NON_ALNUM_RE.sub(" ", (title or "").lower())
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    if not normalized:
        return "untitled"

    filtered_tokens = [
        token
        for token in normalized.split()
        if token not in _TOPIC_STOPWORDS and (len(token) > 2 or token.isdigit())
    ]
    tokens = filtered_tokens or normalized.split()
    return " ".join(tokens[:3]) or "untitled"


def _recency_weight(*, published_at: datetime, now: datetime) -> float:
    age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    decay_factor = math.log(2.0) * (age_hours / RECENCY_HALF_LIFE_HOURS)
    return math.exp(-decay_factor)


def _news_score(bucket: _NewsBucket) -> float:
    source_bonus = min(len(bucket.source_names), 5) * 0.35
    momentum_delta = bucket.recent_window_mentions - bucket.prior_window_mentions
    momentum_bonus = max(0.0, min(2.5, momentum_delta * 0.4))
    return bucket.weighted_mentions + source_bonus + momentum_bonus


class NewsTrendingProvider:
    """Trending provider that derives scores from RSS article activity."""

    provider_key = "news"

    async def collect(
        self,
        db: AsyncSession,
        *,
        now: datetime,
        window_hours: int,
    ) -> list[TrendingSignal]:
        cutoff = now - timedelta(hours=window_hours)
        recent_cutoff = now - timedelta(hours=MOMENTUM_WINDOW_HOURS)
        prior_cutoff = now - timedelta(hours=MOMENTUM_WINDOW_HOURS * 2)

        query = (
            select(
                NewsArticle.title.label("title"),
                NewsArticle.source_name.label("source_name"),
                NewsArticle.published_at.label("published_at"),
                NewsArticle.game_id.label("game_id"),
                NewsArticle.image_url.label("image_url"),
                Game.title.label("game_title"),
                Game.public_id.label("game_public_id"),
                Game.release_date.label("game_release_date"),
                Game.image_url.label("game_image_url"),
            )
            .outerjoin(Game, Game.id == NewsArticle.game_id)
            .where(
                NewsArticle.published_at.isnot(None),
                NewsArticle.published_at >= cutoff,
            )
            .order_by(desc(NewsArticle.published_at))
        )
        rows = (await db.execute(query)).all()

        buckets: dict[str, _NewsBucket] = {}
        today = now.date()

        for row in rows:
            published_at = _ensure_utc(row.published_at)
            if published_at is None:
                continue

            if row.game_id is not None:
                trend_key = f"game:{row.game_id}"
                title = (row.game_title or _clean_article_title(row.title, row.source_name))[:200]
                release_date = row.game_release_date
                bucket = buckets.get(trend_key)
                if bucket is None:
                    bucket = _NewsBucket(
                        trend_key=trend_key,
                        title=title,
                        game_id=row.game_id,
                        game_public_id=row.game_public_id,
                        release_date=release_date,
                        image_url=row.game_image_url or row.image_url,
                        is_linked=True,
                        is_upcoming=bool(release_date and release_date > today),
                    )
                    buckets[trend_key] = bucket
            else:
                cleaned_title = _clean_article_title(row.title, row.source_name)
                topic_key = _topic_key_from_title(cleaned_title)
                trend_key = f"topic:{topic_key}"
                bucket = buckets.get(trend_key)
                if bucket is None:
                    bucket = _NewsBucket(
                        trend_key=trend_key,
                        title=cleaned_title[:200],
                        game_id=None,
                        game_public_id=None,
                        release_date=None,
                        image_url=row.image_url,
                        is_linked=False,
                        # Unlinked trends are treated as upcoming-interest by default.
                        is_upcoming=True,
                    )
                    buckets[trend_key] = bucket

            if bucket.latest_article_at is None or published_at > bucket.latest_article_at:
                bucket.latest_article_at = published_at
                if not bucket.is_linked:
                    bucket.title = _clean_article_title(row.title, row.source_name)[:200]
                    if row.image_url:
                        bucket.image_url = row.image_url

            bucket.mention_count += 1
            bucket.weighted_mentions += _recency_weight(published_at=published_at, now=now)
            bucket.source_names.add((row.source_name or "Unknown").strip() or "Unknown")

            if published_at >= recent_cutoff:
                bucket.recent_window_mentions += 1
            elif published_at >= prior_cutoff:
                bucket.prior_window_mentions += 1

        signals: list[TrendingSignal] = []
        for bucket in buckets.values():
            news_score = round(_news_score(bucket), 4)
            if news_score <= 0:
                continue

            signals.append(
                TrendingSignal(
                    trend_key=bucket.trend_key,
                    title=bucket.title,
                    game_id=bucket.game_id,
                    game_public_id=bucket.game_public_id,
                    release_date=bucket.release_date,
                    image_url=bucket.image_url,
                    is_linked=bucket.is_linked,
                    is_upcoming=bucket.is_upcoming,
                    latest_article_at=bucket.latest_article_at,
                    news_mention_count=bucket.mention_count,
                    news_source_count=len(bucket.source_names),
                    source_scores={self.provider_key: news_score},
                )
            )

        return signals


class TrendingAggregator:
    """Combines signals from one or more providers into a ranked list."""

    def __init__(self, providers: Sequence[TrendingSignalProvider] | None = None):
        self.providers = list(providers) if providers is not None else [NewsTrendingProvider()]

    async def list_trending(
        self,
        db: AsyncSession,
        *,
        limit: int,
        window_hours: int,
        now: datetime | None = None,
    ) -> list[dict]:
        as_of = _ensure_utc(now) or datetime.now(timezone.utc)

        merged: dict[str, TrendingSignal] = {}
        for provider in self.providers:
            provider_signals = await provider.collect(
                db,
                now=as_of,
                window_hours=window_hours,
            )
            for signal in provider_signals:
                existing = merged.get(signal.trend_key)
                if existing is None:
                    merged[signal.trend_key] = signal
                    continue

                existing.source_scores.update(signal.source_scores)
                existing.news_mention_count = max(existing.news_mention_count, signal.news_mention_count)
                existing.news_source_count = max(existing.news_source_count, signal.news_source_count)

                if (
                    existing.latest_article_at is None
                    or (
                        signal.latest_article_at is not None
                        and signal.latest_article_at > existing.latest_article_at
                    )
                ):
                    existing.latest_article_at = signal.latest_article_at

                # Prefer canonical linked game metadata when available.
                if not existing.is_linked and signal.is_linked:
                    existing.title = signal.title
                    existing.game_id = signal.game_id
                    existing.game_public_id = signal.game_public_id
                    existing.release_date = signal.release_date
                    existing.image_url = signal.image_url
                    existing.is_linked = True
                    existing.is_upcoming = signal.is_upcoming

        ranked_signals = sorted(
            merged.values(),
            key=lambda signal: (
                -sum(signal.source_scores.values()),
                -(
                    signal.latest_article_at.timestamp()
                    if signal.latest_article_at is not None
                    else 0
                ),
                -signal.news_mention_count,
                signal.title.lower(),
            ),
        )

        items: list[dict] = []
        for rank, signal in enumerate(ranked_signals[:limit], start=1):
            trend_score = round(sum(signal.source_scores.values()), 4)
            items.append(
                {
                    "rank": rank,
                    "trend_key": signal.trend_key,
                    "title": signal.title,
                    "game_id": signal.game_id,
                    "game_public_id": signal.game_public_id,
                    "release_date": signal.release_date,
                    "image_url": signal.image_url,
                    "is_linked": signal.is_linked,
                    "is_upcoming": signal.is_upcoming,
                    "latest_article_at": signal.latest_article_at,
                    "news_mention_count": signal.news_mention_count,
                    "news_source_count": signal.news_source_count,
                    "trend_score": trend_score,
                    "source_scores": {
                        key: round(value, 4)
                        for key, value in signal.source_scores.items()
                    },
                }
            )

        return items

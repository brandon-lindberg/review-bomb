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
UNLINKED_MIN_MENTIONS = 2
RECENT_RELEASE_FULL_WEIGHT_DAYS = 120
OLD_RELEASE_PENALTY_BUCKETS = (
    (180, 0.75),
    (365, 0.25),
    (365 * 2, 0.2),
    (365 * 5, 0.15),
    (None, 0.1),
)
OLD_RELEASE_OUTLIER_BOOSTS = (
    (10, 5, 0.15),
    (16, 6, 0.2),
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_ROMAN_TOKEN_RE = re.compile(r"^[ivxlcdm]+$")
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
_UNLINKED_TITLE_BREAK_TOKENS = {
    "a",
    "after",
    "adds",
    "an",
    "announced",
    "announces",
    "arrives",
    "before",
    "can",
    "check",
    "coming",
    "confirms",
    "could",
    "day",
    "details",
    "drops",
    "during",
    "explained",
    "explains",
    "gets",
    "guide",
    "has",
    "have",
    "if",
    "is",
    "launch",
    "launches",
    "launched",
    "launching",
    "latest",
    "next",
    "officially",
    "old",
    "preview",
    "promises",
    "release",
    "released",
    "retires",
    "revealed",
    "reveals",
    "review",
    "say",
    "says",
    "shows",
    "things",
    "trailer",
    "update",
    "updates",
    "walkthrough",
    "while",
    "was",
    "will",
    "won",
    "wont",
}
_UNLINKED_INVALID_START_TOKENS = {
    "a",
    "all",
    "and",
    "from",
    "how",
    "if",
    "is",
    "new",
    "one",
    "our",
    "rockstar",
    "sony",
    "the",
    "these",
    "this",
    "those",
    "today",
    "xbox",
    "what",
    "when",
    "where",
    "why",
}
_UNLINKED_REJECT_TOKENS = {
    "actor",
    "director",
    "episode",
    "fans",
    "full",
    "hate",
    "hbo",
    "leaker",
    "legal",
    "movie",
    "season",
    "team",
}
_TITLE_CASE_MINOR_TOKENS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "vs",
    "with",
}
_TITLE_CASE_ACRONYMS = {
    "dlc",
    "fps",
    "gta",
    "mmo",
    "pc",
    "ps4",
    "ps5",
    "rpg",
    "vr",
    "xbox",
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


def _format_inferred_title_tokens(tokens: list[str]) -> str:
    formatted: list[str] = []
    for idx, token in enumerate(tokens):
        if not token:
            continue
        if token.isdigit():
            formatted.append(token)
            continue
        if token in _TITLE_CASE_ACRONYMS:
            formatted.append(token.upper())
            continue
        if _ROMAN_TOKEN_RE.match(token):
            formatted.append(token.upper())
            continue
        if idx > 0 and token in _TITLE_CASE_MINOR_TOKENS:
            formatted.append(token)
            continue
        formatted.append(token.capitalize())

    return " ".join(formatted).strip()


def _infer_unlinked_game_title(title: str, source_name: str | None) -> str | None:
    """
    Infer a concise game-title candidate from an unlinked article headline.
    Returns None when confidence is low to avoid showing noisy topic headlines.
    """
    cleaned = _clean_article_title(title, source_name)
    normalized = _NON_ALNUM_RE.sub(" ", cleaned.lower())
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    if not normalized:
        return None

    raw_tokens = normalized.split()
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        if index + 1 < len(raw_tokens) and token == "pok" and raw_tokens[index + 1] == "mon":
            tokens.append("pokemon")
            index += 2
            continue

        # Remove apostrophe artifact tokens (e.g. "HBO's" -> "hbo s").
        if token == "s" and tokens:
            index += 1
            continue

        tokens.append(token)
        index += 1

    if not tokens:
        return None
    if tokens[0] in _UNLINKED_INVALID_START_TOKENS and len(tokens) > 2:
        return None

    cut_index = len(tokens)
    for index in range(1, len(tokens)):
        if tokens[index] in _UNLINKED_TITLE_BREAK_TOKENS:
            cut_index = index
            break

    candidate_tokens = tokens[:cut_index]
    while candidate_tokens and candidate_tokens[-1] in _TOPIC_STOPWORDS:
        candidate_tokens.pop()

    if not candidate_tokens:
        return None
    if len(candidate_tokens) > 8:
        candidate_tokens = candidate_tokens[:8]
    if candidate_tokens[0].isdigit():
        return None
    if candidate_tokens[0] in _UNLINKED_INVALID_START_TOKENS:
        return None
    if any(token in _UNLINKED_REJECT_TOKENS for token in candidate_tokens):
        return None

    meaningful_tokens = [token for token in candidate_tokens if token not in _TOPIC_STOPWORDS]
    if not meaningful_tokens:
        return None
    if len(candidate_tokens) < 2:
        return None

    inferred = _format_inferred_title_tokens(candidate_tokens)
    return inferred or None


def _recency_weight(*, published_at: datetime, now: datetime) -> float:
    age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    decay_factor = math.log(2.0) * (age_hours / RECENCY_HALF_LIFE_HOURS)
    return math.exp(-decay_factor)


def _news_score(bucket: _NewsBucket) -> float:
    source_bonus = min(len(bucket.source_names), 5) * 0.35
    momentum_delta = bucket.recent_window_mentions - bucket.prior_window_mentions
    momentum_bonus = max(0.0, min(2.5, momentum_delta * 0.4))
    return bucket.weighted_mentions + source_bonus + momentum_bonus


def _release_age_multiplier(signal: TrendingSignal, *, today: date) -> float:
    if signal.release_date is None or signal.release_date >= today:
        return 1.0

    age_days = (today - signal.release_date).days
    if age_days <= RECENT_RELEASE_FULL_WEIGHT_DAYS:
        return 1.0

    multiplier = OLD_RELEASE_PENALTY_BUCKETS[-1][1]
    for max_age_days, bucket_multiplier in OLD_RELEASE_PENALTY_BUCKETS:
        if max_age_days is None or age_days <= max_age_days:
            multiplier = bucket_multiplier
            break

    # Allow rare older-game outliers if they have meaningful present momentum.
    for min_mentions, min_sources, boost in OLD_RELEASE_OUTLIER_BOOSTS:
        if signal.news_mention_count >= min_mentions and signal.news_source_count >= min_sources:
            multiplier += boost

    return min(multiplier, 1.0)


def _effective_trend_score(signal: TrendingSignal, *, today: date) -> float:
    return sum(signal.source_scores.values()) * _release_age_multiplier(signal, today=today)


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
                inferred_title = _infer_unlinked_game_title(row.title, row.source_name)
                if not inferred_title:
                    continue

                topic_key = _topic_key_from_title(inferred_title)
                trend_key = f"topic:{topic_key}"
                bucket = buckets.get(trend_key)
                if bucket is None:
                    bucket = _NewsBucket(
                        trend_key=trend_key,
                        title=inferred_title[:200],
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
                    inferred_latest_title = _infer_unlinked_game_title(row.title, row.source_name)
                    if inferred_latest_title:
                        bucket.title = inferred_latest_title[:200]
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
            if not bucket.is_linked and bucket.mention_count < UNLINKED_MIN_MENTIONS:
                continue

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
        today = as_of.date()

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
                -_effective_trend_score(signal, today=today),
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
            trend_score = round(_effective_trend_score(signal, today=today), 4)
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

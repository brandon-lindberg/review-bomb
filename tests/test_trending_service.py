from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
from types import SimpleNamespace

import pytest

os.environ["DEBUG"] = "false"

from app.services.trending import NewsTrendingProvider, TrendingAggregator, TrendingSignal


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeAsyncSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _statement):
        return FakeResult(self._rows)


@pytest.mark.asyncio
async def test_news_provider_groups_unlinked_topics_and_marks_as_upcoming():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            title="Hollow Knight: Silksong release date rumor - IGN",
            source_name="IGN",
            published_at=now - timedelta(hours=2),
            article_url="https://example.com/silksong-rumor",
            game_id=None,
            image_url="https://img/1.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
        SimpleNamespace(
            title="Hollow Knight Silksong gets new trailer | GameSpot",
            source_name="GameSpot",
            published_at=now - timedelta(hours=7),
            article_url="https://example.com/silksong-trailer",
            game_id=None,
            image_url="https://img/2.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
        SimpleNamespace(
            title="Ghost of Yotei gets major story update - IGN",
            source_name="IGN",
            published_at=now - timedelta(hours=1),
            article_url="https://example.com/ghost-yotei-update",
            game_id=42,
            image_url="https://img/3.jpg",
            game_title="Ghost of Yotei",
            game_public_id="g_ghost_yotei",
            game_release_date=date(2026, 7, 2),
            game_image_url="https://img/game.jpg",
        ),
    ]
    db = FakeAsyncSession(rows)

    provider = NewsTrendingProvider()
    signals = await provider.collect(db, now=now, window_hours=48)

    assert len(signals) == 2

    unlinked = next(item for item in signals if not item.is_linked)
    assert unlinked.trend_key == "topic:hollow knight silksong"
    assert unlinked.is_upcoming is True
    assert unlinked.news_mention_count == 2
    assert unlinked.news_source_count == 2
    assert "Silksong" in unlinked.title
    assert unlinked.source_scores["news"] > 0
    assert unlinked.latest_article_url == "https://example.com/silksong-rumor"

    linked = next(item for item in signals if item.is_linked)
    assert linked.trend_key == "game:42"
    assert linked.game_public_id == "g_ghost_yotei"
    assert linked.is_upcoming is True
    assert linked.news_mention_count == 1
    assert linked.latest_article_url == "https://example.com/ghost-yotei-update"


@dataclass
class _Provider:
    provider_key: str
    signals: list[TrendingSignal]

    async def collect(self, db, *, now, window_hours):  # pragma: no cover - trivial passthrough
        return self.signals


@pytest.mark.asyncio
async def test_trending_aggregator_combines_multi_source_scores():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    base_signal = TrendingSignal(
        trend_key="game:7",
        title="Example Game",
        game_id=7,
        game_public_id="g_example",
        release_date=date(2026, 5, 1),
        image_url=None,
        is_linked=True,
        is_upcoming=True,
        latest_article_at=now - timedelta(hours=1),
        latest_article_url="https://example.com/example-game-1",
        news_mention_count=3,
        news_source_count=2,
        source_scores={"news": 2.25},
    )
    google_signal = TrendingSignal(
        trend_key="game:7",
        title="Example Game",
        game_id=7,
        game_public_id="g_example",
        release_date=date(2026, 5, 1),
        image_url=None,
        is_linked=True,
        is_upcoming=True,
        latest_article_at=now - timedelta(hours=1),
        latest_article_url=None,
        news_mention_count=3,
        news_source_count=2,
        source_scores={"google_trends": 1.5},
    )
    other_signal = TrendingSignal(
        trend_key="topic:unknown teaser",
        title="Unknown Teaser",
        game_id=None,
        game_public_id=None,
        release_date=None,
        image_url=None,
        is_linked=False,
        is_upcoming=True,
        latest_article_at=now - timedelta(hours=2),
        latest_article_url="https://example.com/unknown-teaser",
        news_mention_count=1,
        news_source_count=1,
        source_scores={"news": 1.1},
    )

    aggregator = TrendingAggregator(
        providers=[
            _Provider(provider_key="news", signals=[base_signal, other_signal]),
            _Provider(provider_key="google_trends", signals=[google_signal]),
        ]
    )
    items = await aggregator.list_trending(
        FakeAsyncSession([]),
        limit=5,
        window_hours=48,
        now=now,
    )

    assert len(items) == 2
    assert items[0]["trend_key"] == "game:7"
    assert items[0]["trend_score"] == 3.75
    assert items[0]["source_scores"] == {"news": 2.25, "google_trends": 1.5}
    assert items[0]["latest_article_url"] == "https://example.com/example-game-1"


@pytest.mark.asyncio
async def test_trending_aggregator_penalizes_old_release_dates():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    old_game = TrendingSignal(
        trend_key="game:2017",
        title="Everything",
        game_id=2017,
        game_public_id="g_everything",
        release_date=date(2017, 4, 21),
        image_url=None,
        is_linked=True,
        is_upcoming=False,
        latest_article_at=now - timedelta(hours=1),
        latest_article_url="https://example.com/everything",
        news_mention_count=2,
        news_source_count=1,
        source_scores={"news": 4.0},
    )
    upcoming_game = TrendingSignal(
        trend_key="game:9001",
        title="Marathon",
        game_id=9001,
        game_public_id="g_marathon",
        release_date=date(2026, 9, 1),
        image_url=None,
        is_linked=True,
        is_upcoming=True,
        latest_article_at=now - timedelta(hours=2),
        latest_article_url="https://example.com/marathon",
        news_mention_count=2,
        news_source_count=1,
        source_scores={"news": 2.2},
    )

    aggregator = TrendingAggregator(
        providers=[_Provider(provider_key="news", signals=[old_game, upcoming_game])]
    )
    items = await aggregator.list_trending(
        FakeAsyncSession([]),
        limit=5,
        window_hours=48,
        now=now,
    )

    assert len(items) == 2
    assert items[0]["trend_key"] == "game:9001"
    assert items[1]["trend_key"] == "game:2017"
    assert items[1]["trend_score"] == 0.4


@pytest.mark.asyncio
async def test_trending_aggregator_allows_old_outlier_with_strong_momentum():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    old_outlier = TrendingSignal(
        trend_key="game:90",
        title="Classic Comeback",
        game_id=90,
        game_public_id="g_classic_comeback",
        release_date=date(2012, 10, 1),
        image_url=None,
        is_linked=True,
        is_upcoming=False,
        latest_article_at=now - timedelta(hours=1),
        latest_article_url="https://example.com/classic-comeback",
        news_mention_count=16,
        news_source_count=6,
        source_scores={"news": 8.0},
    )
    newer_game = TrendingSignal(
        trend_key="game:91",
        title="New Hotness",
        game_id=91,
        game_public_id="g_new_hotness",
        release_date=date(2025, 12, 1),
        image_url=None,
        is_linked=True,
        is_upcoming=False,
        latest_article_at=now - timedelta(hours=2),
        latest_article_url="https://example.com/new-hotness",
        news_mention_count=3,
        news_source_count=2,
        source_scores={"news": 3.2},
    )

    aggregator = TrendingAggregator(
        providers=[_Provider(provider_key="news", signals=[old_outlier, newer_game])]
    )
    items = await aggregator.list_trending(
        FakeAsyncSession([]),
        limit=5,
        window_hours=48,
        now=now,
    )

    assert len(items) == 2
    assert items[0]["trend_key"] == "game:90"
    assert items[0]["trend_score"] == 3.6


@pytest.mark.asyncio
async def test_news_provider_uses_inferred_unlinked_game_title_not_headline():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            title="Slay The Spire 2 Has Slayed Steam As Rush To Download Leads To Storefront Crashes",
            source_name="PC Gamer",
            published_at=now - timedelta(hours=2),
            article_url="https://example.com/slay-2-pcgamer",
            game_id=None,
            image_url="https://img/1.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
        SimpleNamespace(
            title="Slay the Spire 2 launch times and release date - IGN",
            source_name="IGN",
            published_at=now - timedelta(hours=1),
            article_url="https://example.com/slay-2-ign",
            game_id=None,
            image_url="https://img/2.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
    ]
    provider = NewsTrendingProvider()
    signals = await provider.collect(FakeAsyncSession(rows), now=now, window_hours=48)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.is_linked is False
    assert signal.title == "Slay the Spire 2"
    assert signal.trend_key == "topic:slay spire 2"
    assert signal.news_mention_count == 2
    assert signal.latest_article_url == "https://example.com/slay-2-ign"


@pytest.mark.asyncio
async def test_news_provider_skips_unlinked_rows_without_game_title_candidate():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            title="From next week, Australians will need to verify their age for Google Play and Steam",
            source_name="The Verge",
            published_at=now - timedelta(hours=1),
            article_url="https://example.com/australia-age-verification",
            game_id=None,
            image_url="https://img/1.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
    ]
    provider = NewsTrendingProvider()
    signals = await provider.collect(FakeAsyncSession(rows), now=now, window_hours=48)

    assert signals == []


@pytest.mark.asyncio
async def test_news_provider_requires_multiple_mentions_for_unlinked_topic():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            title="Crimson Desert launch trailer revealed",
            source_name="IGN",
            published_at=now - timedelta(hours=1),
            article_url="https://example.com/crimson-desert",
            game_id=None,
            image_url="https://img/1.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
    ]
    provider = NewsTrendingProvider()
    signals = await provider.collect(FakeAsyncSession(rows), now=now, window_hours=48)

    assert signals == []


@pytest.mark.asyncio
async def test_news_provider_skips_unlinked_role_or_people_headlines():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            title="Leon Kennedy Actor Won't Say If He's Team Ada Or Team Claire",
            source_name="GameSpot",
            published_at=now - timedelta(hours=1),
            article_url="https://example.com/leon-kennedy-actor",
            game_id=None,
            image_url="https://img/1.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
        SimpleNamespace(
            title="Call of Duty Leaker Retires After Receiving Legal Threats",
            source_name="IGN",
            published_at=now - timedelta(hours=2),
            article_url="https://example.com/cod-leaker-retires",
            game_id=None,
            image_url="https://img/2.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
    ]
    provider = NewsTrendingProvider()
    signals = await provider.collect(FakeAsyncSession(rows), now=now, window_hours=48)

    assert signals == []


@pytest.mark.asyncio
async def test_news_provider_skips_unlinked_hardware_device_topics():
    now = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            title="OBSBOT Tiny 3 review: AI webcam for streamers",
            source_name="TechRadar",
            published_at=now - timedelta(hours=1),
            article_url="https://example.com/obsbot-tiny-3-review",
            game_id=None,
            image_url="https://img/obsbot-1.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
        SimpleNamespace(
            title="OBSBOT Tiny 3 adds better low-light tracking",
            source_name="The Verge",
            published_at=now - timedelta(hours=2),
            article_url="https://example.com/obsbot-tiny-3-update",
            game_id=None,
            image_url="https://img/obsbot-2.jpg",
            game_title=None,
            game_public_id=None,
            game_release_date=None,
            game_image_url=None,
        ),
    ]
    provider = NewsTrendingProvider()
    signals = await provider.collect(FakeAsyncSession(rows), now=now, window_hours=48)

    assert signals == []

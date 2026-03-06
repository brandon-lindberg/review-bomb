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

    linked = next(item for item in signals if item.is_linked)
    assert linked.trend_key == "game:42"
    assert linked.game_public_id == "g_ghost_yotei"
    assert linked.is_upcoming is True
    assert linked.news_mention_count == 1


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

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.middleware import SecurityHeadersMiddleware
from app.routers import stats as stats_router
from app.schemas.schemas import SiteStats
from app.services import site_stats


def _snapshot() -> SiteStats:
    return SiteStats(
        total_journalists=10,
        total_outlets=3,
        total_games=20,
        total_reviews=200,
        avg_disparity_site=1.25,
        last_updated=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_current_stats_uses_published_snapshot_without_live_aggregation(monkeypatch):
    snapshot = _snapshot()
    stored = AsyncMock(return_value=snapshot)
    refresh = AsyncMock()
    monkeypatch.setattr(site_stats, "get_stored_site_stats_snapshot", stored)
    monkeypatch.setattr(site_stats, "refresh_site_stats_snapshot", refresh)

    result = await site_stats.get_current_site_stats_snapshot(SimpleNamespace())

    assert result is snapshot
    stored.assert_awaited_once()
    refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_stats_computes_and_persists_only_when_snapshot_is_missing(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(
        site_stats,
        "get_stored_site_stats_snapshot",
        AsyncMock(return_value=None),
    )
    refresh = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(site_stats, "refresh_site_stats_snapshot", refresh)

    result = await site_stats.get_current_site_stats_snapshot(SimpleNamespace())

    assert result is snapshot
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_stats_route_reads_current_published_snapshot(monkeypatch):
    snapshot = _snapshot()
    loader = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(stats_router, "get_current_site_stats_snapshot", loader)
    db = SimpleNamespace()

    result = await stats_router.get_stats(db=db)

    assert result is snapshot
    loader.assert_awaited_once_with(db)


def test_stats_endpoint_is_not_http_cached():
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/api/v1/stats"),
    )
    response = SimpleNamespace(status_code=200)

    assert (
        SecurityHeadersMiddleware._cache_control_for(request, response)
        == "no-store, no-cache, must-revalidate"
    )

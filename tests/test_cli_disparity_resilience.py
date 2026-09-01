"""`disparity` is the pipeline's final stage and must fail loudly, not fatally.

Both `disparity` invocations in the scheduled pipeline previously ran with no
error handling at all: one transient Postgres blip (the scraper fleet shares
this database) raised straight out of the command. The stage is the only writer
of the published site-stats snapshot, so losing it silently stalls dataset
freshness for the whole site.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import cli


class _FakeSession:
    """Stands in for the AsyncSession `async_session_maker()` hands out."""

    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


class _FakeSessionMaker:
    def __init__(self, session: _FakeSession):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


TRANSIENT = "connection was closed in the middle of operation"


@pytest.fixture
def disparity_env(monkeypatch):
    """Wire cmd_disparity to fakes and neuter retry backoff sleeps."""
    from app.services import disparity as disparity_service
    from app.services import site_stats as site_stats_service

    session = _FakeSession()
    monkeypatch.setattr(cli, "async_session_maker", _FakeSessionMaker(session))
    monkeypatch.setattr(cli, "engine", SimpleNamespace(dispose=AsyncMock()))
    monkeypatch.setattr(cli.asyncio, "sleep", AsyncMock())

    stats = SimpleNamespace(total_games=1, total_reviews=2)
    monkeypatch.setattr(
        site_stats_service,
        "refresh_site_stats_snapshot",
        AsyncMock(return_value=stats),
    )

    calculator = SimpleNamespace(
        generate_journalist_snapshots=AsyncMock(return_value=1),
        generate_outlet_snapshots=AsyncMock(return_value=2),
        generate_game_snapshots=AsyncMock(return_value=3),
        generate_all_snapshots=AsyncMock(
            return_value={"journalists": 1, "outlets": 2, "games": 3}
        ),
    )
    monkeypatch.setattr(
        disparity_service, "DisparityCalculator", lambda db: calculator
    )
    return calculator


def _args(**overrides):
    base = {"journalists": False, "outlets": False, "games": False}
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_disparity_returns_failure_code_instead_of_raising(disparity_env):
    disparity_env.generate_journalist_snapshots.side_effect = RuntimeError(
        "violates unique constraint"
    )

    result = await cli.cmd_disparity(_args(journalists=True))

    assert result == 1


@pytest.mark.asyncio
async def test_disparity_retries_transient_database_failure(disparity_env):
    disparity_env.generate_outlet_snapshots.side_effect = [
        RuntimeError(TRANSIENT),
        7,
    ]

    result = await cli.cmd_disparity(_args(outlets=True))

    assert result in (0, None)
    assert disparity_env.generate_outlet_snapshots.await_count == 2


@pytest.mark.asyncio
async def test_disparity_gives_up_on_persistently_transient_failure(disparity_env):
    disparity_env.generate_game_snapshots.side_effect = RuntimeError(TRANSIENT)

    result = await cli.cmd_disparity(_args(games=True))

    assert result == 1
    assert disparity_env.generate_game_snapshots.await_count > 1


@pytest.mark.asyncio
async def test_disparity_publishes_site_stats_after_game_stage(disparity_env):
    from app.services import site_stats as site_stats_service

    result = await cli.cmd_disparity(_args(games=True))

    assert result in (0, None)
    site_stats_service.refresh_site_stats_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_disparity_reports_failure_when_site_stats_publish_fails(disparity_env):
    from app.services import site_stats as site_stats_service

    site_stats_service.refresh_site_stats_snapshot.side_effect = RuntimeError(
        "violates unique constraint"
    )

    result = await cli.cmd_disparity(_args(games=True))

    assert result == 1

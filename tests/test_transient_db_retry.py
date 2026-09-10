"""Retry behaviour for stages that share one long-lived session.

On 2026-09-10 `disparity --games` lost its connection mid-flush while writing
journalist/outlet pair snapshots. The retry helper then burned all four
remaining attempts in a few seconds without touching the database, because a
failed flush leaves the session in a pending-rollback state:

    This Session's transaction has been rolled back due to a previous exception
    during flush. To begin a new transaction with this Session, first issue
    Session.rollback().

That wrapper quotes the original error, so it still matched the transient
markers and looked retryable while being permanently fatal. The fix is to roll
the session back between attempts; these tests pin that.
"""

import pytest

import app.cli as cli


class FakeSession:
    """Mimics the part of AsyncSession state that broke the retry loop."""

    def __init__(self, *, rollback_raises: bool = False):
        self.needs_rollback = False
        self.rollback_calls = 0
        self._rollback_raises = rollback_raises

    async def rollback(self):
        self.rollback_calls += 1
        if self._rollback_raises:
            raise RuntimeError("connection already gone")
        self.needs_rollback = False


class FakeEngine:
    def __init__(self):
        self.dispose_calls = 0

    async def dispose(self):
        self.dispose_calls += 1


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    """No real backoff, and a stub engine so nothing touches a real pool."""

    async def _no_sleep(_seconds):
        return None

    engine = FakeEngine()
    monkeypatch.setattr(cli.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(cli, "engine", engine)
    return engine


DROPPED = "connection was closed in the middle of operation"
POISONED = (
    "This Session's transaction has been rolled back due to a previous exception "
    "during flush. To begin a new transaction with this Session, first issue "
    f"Session.rollback(). Original exception was: {DROPPED}"
)


def _stage(session: FakeSession, *, fail_times: int):
    """A stage that drops its connection `fail_times` times, then succeeds.

    Faithful to SQLAlchemy: once the flush fails the session stays poisoned, and
    every later call raises PendingRollbackError until someone rolls it back.
    """
    state = {"calls": 0}

    async def run():
        state["calls"] += 1
        if session.needs_rollback:
            raise RuntimeError(POISONED)
        if state["calls"] <= fail_times:
            session.needs_rollback = True
            raise RuntimeError(DROPPED)
        return "snapshots written"

    return run, state


@pytest.mark.asyncio
async def test_retry_recovers_when_the_session_is_rolled_back():
    session = FakeSession()
    stage, state = _stage(session, fail_times=1)

    result = await cli._retry_transient_db_operation("Game disparity stage", stage, session=session)

    assert result == "snapshots written"
    assert state["calls"] == 2
    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_without_the_session_every_later_attempt_is_dead_on_arrival():
    """Reproduces the production failure: 5 attempts, 4 of them no-ops."""
    session = FakeSession()
    stage, state = _stage(session, fail_times=1)

    with pytest.raises(RuntimeError) as excinfo:
        await cli._retry_transient_db_operation("Game disparity stage", stage)

    # The stage was entered all 5 times but only the first reached the database;
    # the rest bounced off the poisoned session.
    assert state["calls"] == cli._TRANSIENT_DB_RETRY_LIMIT
    assert "previous exception during flush" in str(excinfo.value)
    assert session.rollback_calls == 0


@pytest.mark.asyncio
async def test_retries_survive_several_drops():
    session = FakeSession()
    stage, state = _stage(session, fail_times=3)

    result = await cli._retry_transient_db_operation("Game disparity stage", stage, session=session)

    assert result == "snapshots written"
    assert state["calls"] == 4
    assert session.rollback_calls == 3


@pytest.mark.asyncio
async def test_gives_up_after_the_retry_limit(fast_retries):
    session = FakeSession()
    stage, state = _stage(session, fail_times=99)

    with pytest.raises(RuntimeError) as excinfo:
        await cli._retry_transient_db_operation("Game disparity stage", stage, session=session)

    assert state["calls"] == cli._TRANSIENT_DB_RETRY_LIMIT
    assert DROPPED in str(excinfo.value)
    assert fast_retries.dispose_calls == cli._TRANSIENT_DB_RETRY_LIMIT - 1


@pytest.mark.asyncio
async def test_rollback_runs_before_the_pool_is_disposed(fast_retries):
    """Order matters: the session still holds its connection at rollback time."""
    order = []

    class OrderedSession(FakeSession):
        async def rollback(self):
            order.append("rollback")
            await super().rollback()

    async def _dispose():
        order.append("dispose")

    fast_retries.dispose = _dispose
    session = OrderedSession()
    stage, _ = _stage(session, fail_times=1)

    await cli._retry_transient_db_operation("Game disparity stage", stage, session=session)

    assert order == ["rollback", "dispose"]


@pytest.mark.asyncio
async def test_a_failing_rollback_does_not_mask_the_real_error():
    session = FakeSession(rollback_raises=True)
    stage, _ = _stage(session, fail_times=99)

    with pytest.raises(RuntimeError) as excinfo:
        await cli._retry_transient_db_operation("Game disparity stage", stage, session=session)

    assert DROPPED in str(excinfo.value)


@pytest.mark.asyncio
async def test_permanent_errors_still_fail_on_the_first_attempt():
    session = FakeSession()
    state = {"calls": 0}

    async def broken():
        state["calls"] += 1
        raise ValueError("column does not exist")

    with pytest.raises(ValueError):
        await cli._retry_transient_db_operation("Game disparity stage", broken, session=session)

    assert state["calls"] == 1
    assert session.rollback_calls == 0

"""Targeted game refresh: the CLI flag and the manual workflow that runs it.

Workflow checks are text-level for the same reason as
test_review_pipeline_workflow.py: CI installs only requirements.txt, which has
no YAML parser.
"""

from __future__ import annotations

import json
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.cli
from app.services.disparity import DisparityCalculator
from app.services.opencritic import OpenCriticQuotaError
from app.services.sync_orchestrator import SyncOrchestrator

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "refresh-games.yml"
)


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text()


def _steps(text: str) -> list[str]:
    return re.split(r"\n      - ", text)


def test_workflow_is_manual_only(workflow_text: str):
    assert "workflow_dispatch:" in workflow_text
    assert "schedule:" not in workflow_text


def test_inputs_never_reach_a_shell_script_directly(workflow_text: str):
    # `${{ inputs.x }}` inside `run:` is substituted before bash parses the
    # script, so a crafted input would execute. They must go through env.
    allowed_prefixes = (
        "OPENCRITIC_IDS:", "METACRITIC_TITLE:", "METACRITIC_FOR_IDS:",
        "CATALOG_AUDIT_FROM:", "if:", "playwright:",
    )
    for line in workflow_text.splitlines():
        if "${{ inputs." in line:
            assert line.strip().startswith(allowed_prefixes), line


def test_schema_is_migrated_before_refreshing(workflow_text: str):
    assert workflow_text.index("alembic upgrade head") < workflow_text.index(
        "app refresh-reviews"
    )


@pytest.mark.parametrize("command", ["app refresh-reviews", "app metacritic"])
def test_each_command_step_is_named_and_time_boxed(workflow_text: str, command: str):
    owning = [step for step in _steps(workflow_text) if command in step]

    assert len(owning) == 1
    assert owning[0].lstrip().startswith("name:")
    assert "timeout-minutes:" in owning[0]


def _run_refresh_reviews(monkeypatch, argv, stats):
    calls = []

    # Subclass rather than a bare stub: the argument parser reads its defaults
    # off SyncOrchestrator's class attributes.
    class FakeOrchestrator(SyncOrchestrator):
        def __init__(self, db):
            pass

        async def refresh_recent_reviews(self, **kwargs):
            calls.append(kwargs)
            return stats

    @asynccontextmanager
    async def fake_session():
        yield object()

    monkeypatch.setattr(app.cli, "async_session_maker", fake_session)
    monkeypatch.setattr(app.cli, "SyncOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(sys, "argv", ["app", "refresh-reviews", *argv])
    return app.cli.main(), calls


def test_opencritic_id_flag_targets_those_games(monkeypatch):
    code, calls = _run_refresh_reviews(
        monkeypatch,
        ["--opencritic-id", "17842", "--opencritic-id", "17741"],
        {"games_refreshed": 2, "reviews_synced": 62, "games_failed": 0},
    )

    assert code == 0
    assert calls[0]["opencritic_ids"] == [17842, 17741]


def test_targeted_refresh_fails_when_a_requested_game_is_not_refreshed(monkeypatch):
    # Missing from the catalog, or errored mid-refresh: either way the person
    # who asked for this game has to see a failed run.
    code, _ = _run_refresh_reviews(
        monkeypatch,
        ["--opencritic-id", "17842", "--opencritic-id", "99999999"],
        {"games_refreshed": 1, "reviews_synced": 62, "games_failed": 0},
    )

    assert code == 1


def test_window_refresh_is_unchanged_without_opencritic_ids(monkeypatch):
    code, calls = _run_refresh_reviews(
        monkeypatch,
        ["--days", "14"],
        {"games_refreshed": 0, "reviews_synced": 0, "games_failed": 0},
    )

    assert code == 0
    assert calls[0]["opencritic_ids"] is None
    assert calls[0]["days"] == 14


@pytest.mark.asyncio
async def test_release_feeds_find_missing_old_ids_and_deduplicate():
    game = {"id": 15398, "name": "Grand Theft Auto VI"}
    already_stored = {"id": 21711, "name": "Pikmin 4"}
    db = AsyncMock()
    db.scalars.return_value = [SimpleNamespace(opencritic_id=21711)]
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = db
    orchestrator.service = AsyncMock()
    orchestrator._request_count = 0
    orchestrator.service.get_release_feed.side_effect = [
        [game, already_stored], [game], []
    ]
    orchestrator.service.get_game.return_value = game
    orchestrator._import_opencritic_game = AsyncMock(return_value=75)

    assert await orchestrator._discover_release_games() == {
        "games_synced": 1, "reviews_synced": 75,
    }
    orchestrator.service.get_game.assert_awaited_once_with(
        15398, quiet_missing=True, strict=True, max_retries=6
    )
    orchestrator._import_opencritic_game.assert_awaited_once_with(game)


@pytest.mark.asyncio
async def test_release_feed_recovers_reviews_for_an_existing_unscored_game():
    stored_game = SimpleNamespace(
        opencritic_id=21344, critic_review_count=0, last_review_sync_at=None
    )
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = AsyncMock(spec=AsyncSession)
    orchestrator.db.scalars.return_value = [stored_game]
    orchestrator.service = AsyncMock()
    orchestrator._request_count = 0
    orchestrator.service.get_release_feed.return_value = [{
        "id": 21344, "name": "The Legend of Zelda: Ocarina of Time", "topCriticScore": 95.6,
    }]
    orchestrator._refresh_games_reviews = AsyncMock(return_value={"reviews_synced": 105})

    assert await orchestrator._discover_release_games() == {
        "games_synced": 0, "reviews_synced": 105,
    }
    orchestrator._refresh_games_reviews.assert_awaited_once_with([stored_game])


@pytest.mark.asyncio
async def test_targeted_disparity_populates_metacritic_review_cache():
    review = SimpleNamespace(score_normalized=Decimal("98"))
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = Mock()
    db.execute.return_value.scalars.return_value.all.return_value = [review]
    calculator = DisparityCalculator(db)
    calculator.get_game_user_scores = AsyncMock(
        return_value={"steam_score": None, "metacritic_score": Decimal("54")}
    )

    stats = await calculator.calculate_game_disparity(1, refresh_review_cache=True)

    assert stats["avg_disparity_metacritic"] == Decimal("44")
    assert review.cached_metacritic_user_score == Decimal("54")
    assert review.cached_disparity_metacritic == Decimal("44")
    assert review.cached_steam_user_score is None


@pytest.mark.asyncio
async def test_targeted_refresh_imports_missing_game():
    game = {"id": 15398, "name": "Grand Theft Auto VI"}
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = AsyncMock(spec=AsyncSession)
    orchestrator.service = AsyncMock()
    orchestrator._get_recent_review_refresh_games = AsyncMock(return_value=[])
    orchestrator._get_discovery_game = AsyncMock(return_value=game)
    orchestrator._import_opencritic_game = AsyncMock(return_value=75)

    result = await orchestrator.refresh_recent_reviews(opencritic_ids=[15398])

    assert result["games_refreshed"] == 1
    assert result["reviews_synced"] == 75
    orchestrator._import_opencritic_game.assert_awaited_once_with(game)


@pytest.mark.asyncio
async def test_catalog_gap_audit_distinguishes_missing_and_importable_ids():
    game = {"id": 4, "name": "Missing game"}
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = AsyncMock(spec=AsyncSession)
    orchestrator.db.scalars.return_value = [1, 5]
    orchestrator.service = AsyncMock()
    orchestrator._get_discovery_game = AsyncMock(side_effect=[None, game])
    orchestrator._import_opencritic_game = AsyncMock(return_value=0)

    assert await orchestrator.audit_catalog_gaps(start_id=3) == {
        "ids_checked": 2, "games_synced": 1, "reviews_synced": 0, "malformed": 0,
    }
    assert [call.args[0] for call in orchestrator._get_discovery_game.await_args_list] == [3, 4]
    orchestrator._import_opencritic_game.assert_awaited_once_with(game)


@pytest.mark.asyncio
async def test_catalog_audit_saves_first_unchecked_id_when_quota_runs_out():
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = AsyncMock(spec=AsyncSession)
    orchestrator.db.scalars.return_value = [1, 5]
    orchestrator._get_discovery_game = AsyncMock(side_effect=[
        None, OpenCriticQuotaError("daily quota exhausted"), None,
    ])
    orchestrator._set_state = AsyncMock()

    stats = await orchestrator.audit_catalog_gaps(start_id=2)

    assert stats["ids_checked"] == 1
    orchestrator._set_state.assert_awaited_once_with(
        SyncOrchestrator.STATE_CATALOG_GAP_START, "3"
    )


@pytest.mark.asyncio
async def test_recent_reconciliation_retries_only_expired_misses():
    now = datetime.now(timezone.utc)
    orchestrator = object.__new__(SyncOrchestrator)
    orchestrator.db = AsyncMock(spec=AsyncSession)
    orchestrator.db.scalars.return_value = [3]
    orchestrator._get_state = AsyncMock(return_value=json.dumps({
        "1": now.timestamp(),
        "2": (now - timedelta(hours=25)).timestamp(),
    }))
    orchestrator._set_state = AsyncMock()
    orchestrator._get_discovery_game = AsyncMock(return_value=None)

    await orchestrator._reconcile_recent_id_window({4})

    orchestrator._get_discovery_game.assert_awaited_once_with(2)
    key, data = orchestrator._set_state.await_args.args
    assert key == SyncOrchestrator.STATE_RECENT_ID_MISSES
    assert json.loads(data)["2"] >= now.timestamp()

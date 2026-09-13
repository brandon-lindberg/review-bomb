"""Targeted game refresh: the CLI flag and the manual workflow that runs it.

Workflow checks are text-level for the same reason as
test_review_pipeline_workflow.py: CI installs only requirements.txt, which has
no YAML parser.
"""

from __future__ import annotations

import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

import app.cli
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
    allowed_prefixes = ("OPENCRITIC_IDS:", "METACRITIC_TITLE:", "if:", "playwright:")
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

"""Structural guards for the scheduled review-data workflow.

The pipeline previously ran all five CLI commands inside one shell step, so a
failure reported only "exit code 1" with no indication of which stage died.
These are deliberately text-level checks: the workflow's own runtime installs
only `requirements.txt`, which has no YAML parser, so this test must not add an
import that would pass locally and fail in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "review-data-pipeline.yml"
)

PIPELINE_COMMANDS = (
    "app sync",
    "app match",
    "app metacritic",
    "app disparity --journalists --outlets",
    "app disparity --games",
)


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text()


def test_workflow_exists(workflow_text: str):
    assert workflow_text.strip()


def test_schema_is_migrated_before_the_pipeline_runs(workflow_text: str):
    assert "alembic upgrade head" in workflow_text

    migrate_at = workflow_text.index("alembic upgrade head")
    first_command_at = min(
        workflow_text.index(command) for command in PIPELINE_COMMANDS
    )
    assert migrate_at < first_command_at


def test_sync_does_not_disable_its_incremental_stop(workflow_text: str):
    # `--stale-pages 0` disables the early stop entirely, turning every run into
    # a full catalog sweep that consumes the whole step budget.
    assert "--stale-pages 0" not in workflow_text


@pytest.mark.parametrize("command", PIPELINE_COMMANDS)
def test_each_pipeline_command_is_its_own_named_step(
    workflow_text: str, command: str
):
    steps = re.split(r"\n      - ", workflow_text)
    owning = [step for step in steps if command in step]

    assert len(owning) == 1, f"{command!r} should appear in exactly one step"
    assert owning[0].lstrip().startswith("name:"), (
        f"the step running {command!r} needs a name so a failure is attributable"
    )


def test_no_step_chains_multiple_pipeline_commands(workflow_text: str):
    steps = re.split(r"\n      - ", workflow_text)
    for step in steps:
        matched = [command for command in PIPELINE_COMMANDS if command in step]
        assert len(matched) <= 1, f"one step runs several stages: {matched}"


def test_every_pipeline_step_carries_its_own_timeout(workflow_text: str):
    steps = re.split(r"\n      - ", workflow_text)
    for step in steps:
        if any(command in step for command in PIPELINE_COMMANDS):
            assert "timeout-minutes:" in step, (
                "a stage without its own timeout can consume the whole job budget"
            )


MONITOR_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "sitemap-monitor.yml"
)

# Minutes the player-count-scraper's high-frequency workers already occupy.
# `hot` runs every 5 minutes, `maintenance` at 5/20/35/50, `scores` at
# 12/27/42/57 -- all of them writing into this project's database.
SCRAPER_BUSY_MINUTES = (
    set(range(0, 60, 5)) | {5, 20, 35, 50} | {12, 27, 42, 57}
)


@pytest.fixture(scope="module")
def monitor_text() -> str:
    return MONITOR_WORKFLOW.read_text()


def _cron_fields(text: str) -> tuple[str, str]:
    match = re.search(r'cron:\s*"([^"]+)"', text)
    assert match, "monitor workflow must declare a cron schedule"
    minute, hour = match.group(1).split()[:2]
    return minute, hour


def test_monitor_does_not_start_on_a_scraper_worker_minute(monitor_text: str):
    minute, _ = _cron_fields(monitor_text)

    assert int(minute) not in SCRAPER_BUSY_MINUTES, (
        "the monitor starts in the same minute a scraper worker fires, so it "
        "samples the site at its least available moment"
    )


def test_monitor_runs_after_the_pipeline_can_finish(
    monitor_text: str, workflow_text: str
):
    _, monitor_hours = _cron_fields(monitor_text)

    pipeline_cron = re.search(r"cron:\s*'([^']+)'", workflow_text)
    assert pipeline_cron
    pipeline_minute, pipeline_hour = pipeline_cron.group(1).split()[:2]

    budget_minutes = sum(
        int(value) for value in re.findall(r"timeout-minutes:\s*(\d+)", workflow_text)
    )
    earliest_finish = (
        int(pipeline_hour.split(",")[0]) * 60
        + int(pipeline_minute)
        + budget_minutes
    )

    first_monitor_hour = int(monitor_hours.split(",")[0])
    assert first_monitor_hour * 60 >= earliest_finish, (
        "the monitor must not sample while the pipeline it validates is still "
        "writing; it would read a half-refreshed dataset"
    )

"""The migration chain must stay linear and must cover what production runs.

The scheduled pipeline runs `alembic upgrade head`. Alembic resolves the
revision the database is stamped at *before* planning any work, so if that
revision is missing from this repo the command dies with "Can't locate revision
identified by X" and the whole pipeline fails -- which is exactly what happened
when migrations 025/026 were applied to production from an unmerged branch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

# The revision production's database is stamped at. `alembic upgrade head` can
# only run if this revision exists in the chain below. Bump it when production
# is migrated -- deliberately, so a schema change is never an accident.
DEPLOYED_REVISION = "026"

REVISION_RE = re.compile(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
DOWN_RE = re.compile(
    r"^down_revision(?::\s*[^=]+)?=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M
)


def _migrations() -> dict[str, str | None]:
    """Map revision id -> down_revision id for every migration file."""
    chain: dict[str, str | None] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text()
        revision = REVISION_RE.search(text)
        assert revision, f"{path.name} declares no revision id"
        down = DOWN_RE.search(text)
        chain[revision.group(1)] = down.group(1) if down and down.group(1) else None
    return chain


@pytest.fixture(scope="module")
def chain() -> dict[str, str | None]:
    return _migrations()


def test_migration_files_are_discovered(chain):
    assert len(chain) >= 24


def test_chain_covers_the_revision_production_is_stamped_at(chain):
    assert DEPLOYED_REVISION in chain, (
        f"production is stamped at {DEPLOYED_REVISION!r}, which this repo does "
        "not define; `alembic upgrade head` cannot resolve it and every "
        "pipeline run will fail at the migrate step"
    )


def test_chain_has_exactly_one_head(chain):
    referenced = {down for down in chain.values() if down}
    heads = sorted(set(chain) - referenced)

    assert len(heads) == 1, f"expected a single head, found {heads}"


def test_no_migration_points_at_a_missing_parent(chain):
    for revision, down in chain.items():
        if down is not None:
            assert down in chain, (
                f"migration {revision!r} descends from {down!r}, which is absent"
            )


def test_exactly_one_root_migration(chain):
    roots = sorted(rev for rev, down in chain.items() if down is None)

    assert roots == ["001"], f"expected a single root 001, found {roots}"


def test_revision_ids_match_their_filename_prefix():
    for path in sorted(VERSIONS.glob("*.py")):
        prefix = path.name.split("_", 1)[0]
        revision = REVISION_RE.search(path.read_text())
        assert revision and revision.group(1) == prefix, (
            f"{path.name} declares revision {revision.group(1) if revision else None!r}, "
            f"which does not match its filename prefix {prefix!r}"
        )


def test_head_is_at_least_the_deployed_revision(chain):
    referenced = {down for down in chain.values() if down}
    head = next(iter(set(chain) - referenced))

    assert head >= DEPLOYED_REVISION, (
        f"head {head!r} is behind production's {DEPLOYED_REVISION!r}"
    )

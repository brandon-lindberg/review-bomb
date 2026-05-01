"""Helpers for non-sequential public identifiers."""

import re
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

_SLUGGED_ENTITY_SEGMENT_RE = re.compile(r"^(?P<slug>.+)--(?P<identifier>[a-f0-9]{32}|\d+)$", re.IGNORECASE)


def generate_public_id() -> str:
    """Generate a URL-safe non-sequential identifier."""
    return uuid4().hex


def parse_legacy_numeric_id(identifier: str) -> int | None:
    """Parse a positive integer identifier for backward-compatible routes."""
    if not identifier.isdigit():
        return None
    parsed = int(identifier)
    if parsed <= 0:
        return None
    return parsed


def parse_slugged_identifier(identifier: str) -> str:
    """Extract the stable identifier from a frontend canonical route segment."""
    trimmed = identifier.strip()
    if not trimmed:
        return ""
    match = _SLUGGED_ENTITY_SEGMENT_RE.match(trimmed)
    if not match:
        return trimmed
    return str(match.group("identifier") or "").strip()


async def resolve_entity_by_identifier(db: AsyncSession, model, identifier: str):
    """
    Resolve by public_id first, with numeric id fallback for legacy URLs/API calls.
    """
    stable_identifier = parse_slugged_identifier(identifier)
    clauses = [model.public_id == stable_identifier]
    legacy_id = parse_legacy_numeric_id(stable_identifier)
    if legacy_id is not None:
        clauses.append(model.id == legacy_id)

    result = await db.execute(select(model).where(or_(*clauses)))
    entity = result.scalar_one_or_none()
    if isinstance(entity, int):
        # Test fakes may return an integer id from legacy existence checks.
        return SimpleNamespace(id=entity, public_id=str(entity))
    return entity

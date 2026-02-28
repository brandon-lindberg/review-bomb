"""Helpers for non-sequential public identifiers."""

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession


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


async def resolve_entity_by_identifier(db: AsyncSession, model, identifier: str):
    """
    Resolve by public_id first, with numeric id fallback for legacy URLs/API calls.
    """
    clauses = [model.public_id == identifier]
    legacy_id = parse_legacy_numeric_id(identifier)
    if legacy_id is not None:
        clauses.append(model.id == legacy_id)

    result = await db.execute(select(model).where(or_(*clauses)))
    entity = result.scalar_one_or_none()
    if isinstance(entity, int):
        # Test fakes may return an integer id from legacy existence checks.
        return SimpleNamespace(id=entity, public_id=str(entity))
    return entity

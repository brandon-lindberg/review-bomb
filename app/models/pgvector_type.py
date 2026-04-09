"""Minimal pgvector SQLAlchemy type helpers.

This repo uses pgvector as a PostgreSQL extension, but we keep the Python-side
dependency surface small by defining a lightweight custom SQLAlchemy type here.
The live API reads precomputed neighbors and does not depend on vector
operators in hot paths, so this implementation only needs basic bind/result
support plus optional cosine-distance SQL emission for offline jobs.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.sql import expression
from sqlalchemy.types import UserDefinedType


def _serialize_vector(value: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(component):.8f}" for component in value) + "]"


class PGVector(UserDefinedType):
    """PostgreSQL vector(N) type for pgvector-backed columns."""

    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:  # noqa: ANN003 - SQLAlchemy signature
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect):  # noqa: ANN001 - SQLAlchemy protocol
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return _serialize_vector(value)

        return process

    def result_processor(self, dialect, coltype):  # noqa: ANN001 - SQLAlchemy protocol
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return [float(component) for component in value]
            if isinstance(value, tuple):
                return [float(component) for component in value]
            if not isinstance(value, str):
                return value
            stripped = value.strip().strip("[]")
            if not stripped:
                return []
            return [float(component) for component in stripped.split(",")]

        return process

    class comparator_factory(UserDefinedType.Comparator):
        def cosine_distance(self, other):
            return expression.BinaryExpression(
                self.expr,
                expression.bindparam(None, other, type_=self.type),
                expression.custom_op("<=>"),
            )


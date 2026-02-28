"""Add non-sequential public IDs for public-facing entity routes.

Revision ID: 017
Revises: 016
Create Date: 2026-02-28
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_public_ids(bind, table) -> None:
    rows = bind.execute(
        sa.select(table.c.id).where(table.c.public_id.is_(None))
    ).fetchall()
    for row in rows:
        bind.execute(
            table.update().where(table.c.id == row[0]).values(public_id=uuid4().hex)
        )


def upgrade() -> None:
    op.add_column("journalists", sa.Column("public_id", sa.String(length=32), nullable=True))
    op.add_column("outlets", sa.Column("public_id", sa.String(length=32), nullable=True))
    op.add_column("games", sa.Column("public_id", sa.String(length=32), nullable=True))

    bind = op.get_bind()

    journalists_table = sa.table(
        "journalists",
        sa.column("id", sa.Integer()),
        sa.column("public_id", sa.String(length=32)),
    )
    outlets_table = sa.table(
        "outlets",
        sa.column("id", sa.Integer()),
        sa.column("public_id", sa.String(length=32)),
    )
    games_table = sa.table(
        "games",
        sa.column("id", sa.Integer()),
        sa.column("public_id", sa.String(length=32)),
    )

    _backfill_public_ids(bind, journalists_table)
    _backfill_public_ids(bind, outlets_table)
    _backfill_public_ids(bind, games_table)

    op.alter_column("journalists", "public_id", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("outlets", "public_id", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("games", "public_id", existing_type=sa.String(length=32), nullable=False)

    op.create_index(op.f("ix_journalists_public_id"), "journalists", ["public_id"], unique=True)
    op.create_index(op.f("ix_outlets_public_id"), "outlets", ["public_id"], unique=True)
    op.create_index(op.f("ix_games_public_id"), "games", ["public_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_games_public_id"), table_name="games")
    op.drop_index(op.f("ix_outlets_public_id"), table_name="outlets")
    op.drop_index(op.f("ix_journalists_public_id"), table_name="journalists")

    op.drop_column("games", "public_id")
    op.drop_column("outlets", "public_id")
    op.drop_column("journalists", "public_id")

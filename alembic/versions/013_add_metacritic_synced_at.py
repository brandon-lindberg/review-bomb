"""Add metacritic_synced_at to games for tracking when each game was last scraped.

Revision ID: 013
Revises: 012
Create Date: 2026-02-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("metacritic_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("games", "metacritic_synced_at")

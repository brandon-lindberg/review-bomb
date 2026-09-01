"""Add normalized title prefix index for generic series recall.

Revision ID: 026
Revises: 025
"""

from typing import Union

from alembic import op


revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_games_lower_title_prefix
        ON games (lower(title) text_pattern_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_games_lower_title_prefix")

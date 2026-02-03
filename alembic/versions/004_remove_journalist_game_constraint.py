"""Remove uq_journalist_game constraint

A journalist can legitimately review the same game multiple times
(e.g., different platforms, updated reviews). The opencritic_review_id
unique constraint is sufficient to prevent duplicate reviews.

Revision ID: 004
Revises: 003
Create Date: 2026-02-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique constraint on journalist_id + game_id
    op.drop_constraint('uq_journalist_game', 'reviews', type_='unique')


def downgrade() -> None:
    # Re-add the constraint (note: this may fail if data now violates it)
    op.create_unique_constraint('uq_journalist_game', 'reviews', ['journalist_id', 'game_id'])

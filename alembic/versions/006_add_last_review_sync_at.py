"""Add last_review_sync_at field to games table

Tracks when reviews were last fetched from OpenCritic for each game.
Used by the refresh-reviews command to identify games needing re-sync.

Revision ID: 006
Revises: 005
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('games', sa.Column('last_review_sync_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('games', 'last_review_sync_at')

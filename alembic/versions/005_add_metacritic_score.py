"""Add metacritic_score field to games table

Stores the Metacritic critic aggregate score (Metascore) for games.
This is separate from user scores which are stored in user_scores table.

Revision ID: 005
Revises: 004
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add metacritic_score column to games table
    op.add_column('games', sa.Column('metacritic_score', sa.Numeric(precision=5, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('games', 'metacritic_score')

"""Add denormalized columns to games for instant queries.

Revision ID: 009
Revises: 008
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add denormalized columns to games
    op.add_column('games', sa.Column('avg_critic_score', sa.Numeric(5, 2), nullable=True))
    op.add_column('games', sa.Column('critic_review_count', sa.Integer(), nullable=True, default=0))
    op.add_column('games', sa.Column('steam_user_score', sa.Numeric(5, 2), nullable=True))
    op.add_column('games', sa.Column('steam_sample_size', sa.Integer(), nullable=True))
    op.add_column('games', sa.Column('metacritic_user_score', sa.Numeric(5, 2), nullable=True))
    op.add_column('games', sa.Column('metacritic_sample_size', sa.Integer(), nullable=True))
    op.add_column('games', sa.Column('disparity_steam', sa.Numeric(5, 2), nullable=True))
    op.add_column('games', sa.Column('disparity_metacritic', sa.Numeric(5, 2), nullable=True))
    
    # Create indexes for fast sorting
    op.create_index('idx_games_avg_critic_score', 'games', ['avg_critic_score'], unique=False)
    op.create_index('idx_games_disparity_steam', 'games', ['disparity_steam'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_games_disparity_steam', table_name='games')
    op.drop_index('idx_games_avg_critic_score', table_name='games')
    
    op.drop_column('games', 'disparity_metacritic')
    op.drop_column('games', 'disparity_steam')
    op.drop_column('games', 'metacritic_sample_size')
    op.drop_column('games', 'metacritic_user_score')
    op.drop_column('games', 'steam_sample_size')
    op.drop_column('games', 'steam_user_score')
    op.drop_column('games', 'critic_review_count')
    op.drop_column('games', 'avg_critic_score')

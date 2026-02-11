"""Add denormalized disparity columns to journalists and outlets.

This allows instant leaderboard queries by storing pre-calculated values.

Revision ID: 008
Revises: 007
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add denormalized columns to journalists
    op.add_column('journalists', sa.Column('avg_disparity', sa.Numeric(6, 2), nullable=True))
    op.add_column('journalists', sa.Column('review_count_scored', sa.Integer(), nullable=True, default=0))
    op.add_column('journalists', sa.Column('score_std_dev', sa.Numeric(6, 2), nullable=True))
    op.add_column('journalists', sa.Column('last_review_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('journalists', sa.Column('primary_outlet', sa.String(255), nullable=True))
    
    # Add denormalized columns to outlets
    op.add_column('outlets', sa.Column('avg_disparity', sa.Numeric(6, 2), nullable=True))
    op.add_column('outlets', sa.Column('review_count_scored', sa.Integer(), nullable=True, default=0))
    op.add_column('outlets', sa.Column('journalist_count', sa.Integer(), nullable=True, default=0))
    op.add_column('outlets', sa.Column('score_std_dev', sa.Numeric(6, 2), nullable=True))
    op.add_column('outlets', sa.Column('last_review_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create indexes for fast sorting
    op.create_index('idx_journalists_avg_disparity', 'journalists', ['avg_disparity'], unique=False)
    op.create_index('idx_journalists_last_review_at', 'journalists', ['last_review_at'], unique=False)
    op.create_index('idx_journalists_review_count', 'journalists', ['review_count_scored'], unique=False)
    
    op.create_index('idx_outlets_avg_disparity', 'outlets', ['avg_disparity'], unique=False)
    op.create_index('idx_outlets_last_review_at', 'outlets', ['last_review_at'], unique=False)
    op.create_index('idx_outlets_review_count', 'outlets', ['review_count_scored'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_outlets_review_count', table_name='outlets')
    op.drop_index('idx_outlets_last_review_at', table_name='outlets')
    op.drop_index('idx_outlets_avg_disparity', table_name='outlets')
    
    op.drop_index('idx_journalists_review_count', table_name='journalists')
    op.drop_index('idx_journalists_last_review_at', table_name='journalists')
    op.drop_index('idx_journalists_avg_disparity', table_name='journalists')
    
    # Drop columns from outlets
    op.drop_column('outlets', 'last_review_at')
    op.drop_column('outlets', 'score_std_dev')
    op.drop_column('outlets', 'journalist_count')
    op.drop_column('outlets', 'review_count_scored')
    op.drop_column('outlets', 'avg_disparity')
    
    # Drop columns from journalists
    op.drop_column('journalists', 'primary_outlet')
    op.drop_column('journalists', 'last_review_at')
    op.drop_column('journalists', 'score_std_dev')
    op.drop_column('journalists', 'review_count_scored')
    op.drop_column('journalists', 'avg_disparity')

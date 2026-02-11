"""Add performance indexes for leaderboard queries.

Revision ID: 007
Revises: 006
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite index for user_scores queries (game_id + source + scraped_at)
    op.create_index(
        'idx_user_scores_game_source_scraped',
        'user_scores',
        ['game_id', 'source', 'scraped_at'],
        unique=False
    )
    
    # Composite index for reviews queries (journalist_id + score_normalized)
    op.create_index(
        'idx_reviews_journalist_score',
        'reviews',
        ['journalist_id', 'score_normalized'],
        unique=False
    )
    
    # Composite index for reviews queries (outlet_id + score_normalized)
    op.create_index(
        'idx_reviews_outlet_score',
        'reviews',
        ['outlet_id', 'score_normalized'],
        unique=False
    )
    
    # Composite index for reviews queries (game_id + score_normalized)
    op.create_index(
        'idx_reviews_game_score',
        'reviews',
        ['game_id', 'score_normalized'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_reviews_game_score', table_name='reviews')
    op.drop_index('idx_reviews_outlet_score', table_name='reviews')
    op.drop_index('idx_reviews_journalist_score', table_name='reviews')
    op.drop_index('idx_user_scores_game_source_scraped', table_name='user_scores')

"""Add targeted indexes for games/journalists/outlets list endpoint sorts.

Revision ID: 014
Revises: 013
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Games list: release-date and disparity sorts with identical list filters.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_games_list_release_filtered
        ON games (release_date DESC NULLS LAST, created_at DESC NULLS LAST)
        WHERE avg_critic_score IS NOT NULL
          AND (
            steam_sample_size >= 50
            OR (
              metacritic_user_score IS NOT NULL
              AND (metacritic_sample_size IS NULL OR metacritic_sample_size >= 20)
            )
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_games_list_disparity_filtered
        ON games ((ABS(COALESCE((disparity_steam + disparity_metacritic) / 2.0, disparity_steam, disparity_metacritic))))
        WHERE avg_critic_score IS NOT NULL
          AND (
            steam_sample_size >= 50
            OR (
              metacritic_user_score IS NOT NULL
              AND (metacritic_sample_size IS NULL OR metacritic_sample_size >= 20)
            )
          )
        """
    )

    # Journalists list: default and most-used sorts with scored-review guard.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_journalists_list_last_review
        ON journalists (last_review_at DESC)
        WHERE review_count_scored IS NOT NULL AND review_count_scored > 0
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_journalists_list_review_count
        ON journalists (review_count_scored DESC)
        WHERE review_count_scored IS NOT NULL AND review_count_scored > 0
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reviews_journalist_scored_recent
        ON reviews (journalist_id, published_at DESC, game_id)
        WHERE score_normalized IS NOT NULL
          AND score_normalized > 0
          AND published_at IS NOT NULL
        """
    )

    # Outlets list: disparity magnitude sort and recent sort with list guards.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outlets_list_abs_disparity
        ON outlets ((ABS(avg_disparity)))
        WHERE avg_disparity IS NOT NULL
          AND review_count_scored >= 10
          AND COALESCE(score_std_dev, 0) >= 10
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outlets_list_last_review
        ON outlets (last_review_at DESC)
        WHERE review_count_scored IS NOT NULL AND review_count_scored >= 10
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_outlets_list_last_review")
    op.execute("DROP INDEX IF EXISTS idx_outlets_list_abs_disparity")
    op.execute("DROP INDEX IF EXISTS idx_reviews_journalist_scored_recent")
    op.execute("DROP INDEX IF EXISTS idx_journalists_list_review_count")
    op.execute("DROP INDEX IF EXISTS idx_journalists_list_last_review")
    op.execute("DROP INDEX IF EXISTS idx_games_list_disparity_filtered")
    op.execute("DROP INDEX IF EXISTS idx_games_list_release_filtered")

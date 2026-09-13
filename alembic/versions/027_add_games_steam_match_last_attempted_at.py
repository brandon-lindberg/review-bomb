"""Track when the match stage last searched Steam for each game.

Console exclusives never get a Steam ID, so the match stage re-searched them on
every run and filled its 300-game batch with guaranteed misses. This timestamp
lets it retry those weekly instead.

Revision ID: 027
Revises: 026
Create Date: 2026-09-13
"""

from typing import Union

from alembic import op


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # ADD COLUMN needs a brief exclusive lock on games. Waiting on it behind a
    # long transaction would queue every site read of games behind this
    # statement, so give up instead; the next pipeline run retries.
    op.execute("SET LOCAL lock_timeout = '15s'")
    # Nullable with no default: a catalog-only change, no table rewrite.
    op.execute(
        """
        ALTER TABLE games
        ADD COLUMN IF NOT EXISTS steam_match_last_attempted_at TIMESTAMP WITH TIME ZONE
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS steam_match_last_attempted_at")

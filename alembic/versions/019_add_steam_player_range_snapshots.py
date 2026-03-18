"""Add stored Steam player 24-hour range snapshots.

Revision ID: 019
Revises: 018
Create Date: 2026-03-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "steam_player_range_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("players_24h_high", sa.Integer(), nullable=False),
        sa.Column("players_24h_low", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "sampled_at", name="uq_steam_player_range_snapshots_game_sampled"),
    )
    op.create_index(
        "idx_steam_player_range_snapshots_game_sampled",
        "steam_player_range_snapshots",
        ["game_id", "sampled_at"],
        unique=False,
    )
    op.create_index(
        "idx_steam_player_range_snapshots_sampled_at",
        "steam_player_range_snapshots",
        ["sampled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_steam_player_range_snapshots_sampled_at", table_name="steam_player_range_snapshots")
    op.drop_index("idx_steam_player_range_snapshots_game_sampled", table_name="steam_player_range_snapshots")
    op.drop_table("steam_player_range_snapshots")

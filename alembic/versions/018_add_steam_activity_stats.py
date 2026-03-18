"""Add Steam activity stats and snapshots.

Revision ID: 018
Revises: 017
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("games", sa.Column("steam_current_players", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("steam_current_players_sampled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("games", sa.Column("steam_player_24h_peak", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("steam_player_24h_low_observed", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("steam_player_all_time_peak", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("steam_player_all_time_peak_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("games", sa.Column("steam_player_stats_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("games", sa.Column("steam_achievement_count", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("steam_achievement_count_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "steam_player_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concurrent_players", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_steam_player_snapshots_game_sampled",
        "steam_player_snapshots",
        ["game_id", "sampled_at"],
        unique=False,
    )
    op.create_index(
        "idx_steam_player_snapshots_sampled_at",
        "steam_player_snapshots",
        ["sampled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_steam_player_snapshots_sampled_at", table_name="steam_player_snapshots")
    op.drop_index("idx_steam_player_snapshots_game_sampled", table_name="steam_player_snapshots")
    op.drop_table("steam_player_snapshots")

    op.drop_column("games", "steam_achievement_count_synced_at")
    op.drop_column("games", "steam_achievement_count")
    op.drop_column("games", "steam_player_stats_synced_at")
    op.drop_column("games", "steam_player_all_time_peak_at")
    op.drop_column("games", "steam_player_all_time_peak")
    op.drop_column("games", "steam_player_24h_low_observed")
    op.drop_column("games", "steam_player_24h_peak")
    op.drop_column("games", "steam_current_players_sampled_at")
    op.drop_column("games", "steam_current_players")

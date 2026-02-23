"""Add pipeline-cached review disparities and journalist-outlet snapshots.

Revision ID: 015
Revises: 014
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("cached_steam_user_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("reviews", sa.Column("cached_metacritic_user_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("reviews", sa.Column("cached_disparity_steam", sa.Numeric(6, 2), nullable=True))
    op.add_column("reviews", sa.Column("cached_disparity_metacritic", sa.Numeric(6, 2), nullable=True))
    op.add_column("reviews", sa.Column("cached_disparity_combined", sa.Numeric(6, 2), nullable=True))

    op.create_table(
        "journalist_outlet_disparity_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("journalist_id", sa.Integer(), nullable=False),
        sa.Column("outlet_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("avg_disparity_steam", sa.Numeric(6, 2), nullable=True),
        sa.Column("avg_disparity_metacritic", sa.Numeric(6, 2), nullable=True),
        sa.Column("avg_disparity_combined", sa.Numeric(6, 2), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("std_deviation", sa.Numeric(6, 2), nullable=True),
        sa.Column("min_disparity", sa.Numeric(6, 2), nullable=True),
        sa.Column("max_disparity", sa.Numeric(6, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["journalist_id"], ["journalists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_journalist_outlet_disparity_pair",
        "journalist_outlet_disparity_snapshots",
        ["journalist_id", "outlet_id", "snapshot_date"],
        unique=False,
    )
    op.create_index(
        "idx_journalist_outlet_disparity_journalist",
        "journalist_outlet_disparity_snapshots",
        ["journalist_id", "snapshot_date"],
        unique=False,
    )
    op.create_index(
        "idx_journalist_outlet_disparity_outlet",
        "journalist_outlet_disparity_snapshots",
        ["outlet_id", "snapshot_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_journalist_outlet_disparity_outlet", table_name="journalist_outlet_disparity_snapshots")
    op.drop_index("idx_journalist_outlet_disparity_journalist", table_name="journalist_outlet_disparity_snapshots")
    op.drop_index("idx_journalist_outlet_disparity_pair", table_name="journalist_outlet_disparity_snapshots")
    op.drop_table("journalist_outlet_disparity_snapshots")

    op.drop_column("reviews", "cached_disparity_combined")
    op.drop_column("reviews", "cached_disparity_metacritic")
    op.drop_column("reviews", "cached_disparity_steam")
    op.drop_column("reviews", "cached_metacritic_user_score")
    op.drop_column("reviews", "cached_steam_user_score")

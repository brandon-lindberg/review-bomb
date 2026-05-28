"""Add OpenCritic malformed game quarantine.

Revision ID: 024
Revises: 023
Create Date: 2026-05-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opencritic_malformed_games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opencritic_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=1024), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opencritic_id"),
    )
    op.create_index(
        op.f("ix_opencritic_malformed_games_opencritic_id"),
        "opencritic_malformed_games",
        ["opencritic_id"],
        unique=False,
    )
    op.create_index(
        "idx_opencritic_malformed_games_reason",
        "opencritic_malformed_games",
        ["reason", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_opencritic_malformed_games_reason", table_name="opencritic_malformed_games")
    op.drop_index(op.f("ix_opencritic_malformed_games_opencritic_id"), table_name="opencritic_malformed_games")
    op.drop_table("opencritic_malformed_games")

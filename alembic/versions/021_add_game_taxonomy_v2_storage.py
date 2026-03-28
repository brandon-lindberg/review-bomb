"""Add Similar Games Taxonomy V2 storage.

Revision ID: 021
Revises: 020
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    empty_text_array = sa.text("'{}'::text[]")

    op.add_column("games", sa.Column("taxonomy_v2_version", sa.String(length=64), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_v2_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column("games", sa.Column("taxonomy_v2_primary_family", sa.String(length=64), nullable=True))
    op.add_column("games", sa.Column("taxonomy_v2_primary_archetype", sa.String(length=128), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_v2_secondary_archetypes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_v2_hard_exclusions",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_v2_soft_penalties",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column("games", sa.Column("taxonomy_v2_confidence", sa.Numeric(4, 2), nullable=True))
    op.add_column("games", sa.Column("taxonomy_v2_fingerprint", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("games", sa.Column("taxonomy_v2_computed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_v2_curated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("games", sa.Column("taxonomy_v2_debug_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_index(
        "idx_games_taxonomy_v2_primary_family",
        "games",
        ["taxonomy_v2_primary_family"],
        unique=False,
    )
    op.create_index(
        "idx_games_taxonomy_v2_primary_archetype",
        "games",
        ["taxonomy_v2_primary_archetype"],
        unique=False,
    )
    op.create_index(
        "idx_games_taxonomy_v2_status",
        "games",
        ["taxonomy_v2_status"],
        unique=False,
    )
    op.create_index(
        "idx_games_taxonomy_v2_secondary_archetypes_gin",
        "games",
        ["taxonomy_v2_secondary_archetypes"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_games_taxonomy_v2_hard_exclusions_gin",
        "games",
        ["taxonomy_v2_hard_exclusions"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "game_taxonomy_v2_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=64), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_field", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("curated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("weight", sa.Numeric(5, 2), nullable=True),
        sa.Column("conflict_group", sa.String(length=64), nullable=True),
        sa.Column("suppressed_by_rule", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_game_taxonomy_v2_evidence_game_id",
        "game_taxonomy_v2_evidence",
        ["game_id"],
        unique=False,
    )
    op.create_index(
        "idx_game_taxonomy_v2_evidence_version_field_value",
        "game_taxonomy_v2_evidence",
        ["taxonomy_version", "field", "value"],
        unique=False,
    )
    op.create_index(
        "idx_game_taxonomy_v2_evidence_source_source_field",
        "game_taxonomy_v2_evidence",
        ["source", "source_field"],
        unique=False,
    )
    op.create_index(
        "idx_game_taxonomy_v2_evidence_game_field",
        "game_taxonomy_v2_evidence",
        ["game_id", "field"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_game_taxonomy_v2_evidence_game_field", table_name="game_taxonomy_v2_evidence")
    op.drop_index(
        "idx_game_taxonomy_v2_evidence_source_source_field",
        table_name="game_taxonomy_v2_evidence",
    )
    op.drop_index(
        "idx_game_taxonomy_v2_evidence_version_field_value",
        table_name="game_taxonomy_v2_evidence",
    )
    op.drop_index("idx_game_taxonomy_v2_evidence_game_id", table_name="game_taxonomy_v2_evidence")
    op.drop_table("game_taxonomy_v2_evidence")

    op.drop_index("idx_games_taxonomy_v2_hard_exclusions_gin", table_name="games")
    op.drop_index("idx_games_taxonomy_v2_secondary_archetypes_gin", table_name="games")
    op.drop_index("idx_games_taxonomy_v2_status", table_name="games")
    op.drop_index("idx_games_taxonomy_v2_primary_archetype", table_name="games")
    op.drop_index("idx_games_taxonomy_v2_primary_family", table_name="games")

    op.drop_column("games", "taxonomy_v2_debug_payload")
    op.drop_column("games", "taxonomy_v2_curated")
    op.drop_column("games", "taxonomy_v2_computed_at")
    op.drop_column("games", "taxonomy_v2_fingerprint")
    op.drop_column("games", "taxonomy_v2_confidence")
    op.drop_column("games", "taxonomy_v2_soft_penalties")
    op.drop_column("games", "taxonomy_v2_hard_exclusions")
    op.drop_column("games", "taxonomy_v2_secondary_archetypes")
    op.drop_column("games", "taxonomy_v2_primary_archetype")
    op.drop_column("games", "taxonomy_v2_primary_family")
    op.drop_column("games", "taxonomy_v2_status")
    op.drop_column("games", "taxonomy_v2_version")

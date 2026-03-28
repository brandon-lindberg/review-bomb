"""Add game taxonomy storage for similar-games support.

Revision ID: 020
Revises: 019
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    empty_text_array = sa.text("'{}'::text[]")

    op.add_column(
        "games",
        sa.Column(
            "taxonomy_genres",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_themes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_modes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_perspectives",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_studios",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_publishers",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_sources",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column("games", sa.Column("taxonomy_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        "idx_games_taxonomy_genres_gin",
        "games",
        ["taxonomy_genres"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_games_taxonomy_themes_gin",
        "games",
        ["taxonomy_themes"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_games_taxonomy_modes_gin",
        "games",
        ["taxonomy_modes"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_games_taxonomy_perspectives_gin",
        "games",
        ["taxonomy_perspectives"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_games_taxonomy_sources_gin",
        "games",
        ["taxonomy_sources"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "game_source_taxonomy_labels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("facet", sa.String(length=32), nullable=False),
        sa.Column("raw_label", sa.String(length=255), nullable=False),
        sa.Column("normalized_label", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_id",
            "source",
            "facet",
            "normalized_label",
            name="uq_game_source_taxonomy_labels_game_source_facet_label",
        ),
    )
    op.create_index(
        "idx_game_source_taxonomy_labels_game_source",
        "game_source_taxonomy_labels",
        ["game_id", "source"],
        unique=False,
    )
    op.create_index(
        "idx_game_source_taxonomy_labels_source_facet_normalized",
        "game_source_taxonomy_labels",
        ["source", "facet", "normalized_label"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_game_source_taxonomy_labels_source_facet_normalized",
        table_name="game_source_taxonomy_labels",
    )
    op.drop_index("idx_game_source_taxonomy_labels_game_source", table_name="game_source_taxonomy_labels")
    op.drop_table("game_source_taxonomy_labels")

    op.drop_index("idx_games_taxonomy_sources_gin", table_name="games")
    op.drop_index("idx_games_taxonomy_perspectives_gin", table_name="games")
    op.drop_index("idx_games_taxonomy_modes_gin", table_name="games")
    op.drop_index("idx_games_taxonomy_themes_gin", table_name="games")
    op.drop_index("idx_games_taxonomy_genres_gin", table_name="games")

    op.drop_column("games", "taxonomy_synced_at")
    op.drop_column("games", "taxonomy_sources")
    op.drop_column("games", "taxonomy_publishers")
    op.drop_column("games", "taxonomy_studios")
    op.drop_column("games", "taxonomy_perspectives")
    op.drop_column("games", "taxonomy_modes")
    op.drop_column("games", "taxonomy_themes")
    op.drop_column("games", "taxonomy_genres")

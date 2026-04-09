"""Add source descriptions and taxonomy V2 text corpus storage.

Revision ID: 022
Revises: 021
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    empty_text_array = sa.text("'{}'::text[]")

    op.add_column("games", sa.Column("opencritic_description", sa.Text(), nullable=True))
    op.add_column("games", sa.Column("steam_short_description", sa.Text(), nullable=True))
    op.add_column("games", sa.Column("steam_detailed_description", sa.Text(), nullable=True))
    op.add_column("games", sa.Column("metacritic_description", sa.Text(), nullable=True))
    op.add_column("games", sa.Column("taxonomy_v2_text_corpus", sa.Text(), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "taxonomy_v2_text_sources",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column("games", sa.Column("taxonomy_v2_text_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("games", "taxonomy_v2_text_synced_at")
    op.drop_column("games", "taxonomy_v2_text_sources")
    op.drop_column("games", "taxonomy_v2_text_corpus")
    op.drop_column("games", "metacritic_description")
    op.drop_column("games", "steam_detailed_description")
    op.drop_column("games", "steam_short_description")
    op.drop_column("games", "opencritic_description")

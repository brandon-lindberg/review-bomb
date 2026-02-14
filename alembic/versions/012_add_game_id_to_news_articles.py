"""Add game_id FK to news_articles for linking articles to games.

Revision ID: 012
Revises: 011
Create Date: 2026-02-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news_articles",
        sa.Column(
            "game_id",
            sa.Integer(),
            sa.ForeignKey("games.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_news_game_published",
        "news_articles",
        ["game_id", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_news_game_published", table_name="news_articles")
    op.drop_column("news_articles", "game_id")

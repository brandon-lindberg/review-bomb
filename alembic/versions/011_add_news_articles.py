"""Add news_articles table for gaming news RSS feed aggregation.

Revision ID: 011
Revises: 010
Create Date: 2026-02-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(1024), nullable=False, unique=True),
        sa.Column("image_url", sa.String(1024), nullable=True),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_news_source_published",
        "news_articles",
        ["source_name", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_news_source_published", table_name="news_articles")
    op.drop_table("news_articles")

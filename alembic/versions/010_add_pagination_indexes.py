"""Add composite indexes for review pagination queries.

The paginated review endpoints filter by entity_id + score_normalized
and ORDER BY published_at DESC. These composite indexes cover both
the filter and sort to avoid expensive filesorts on deep pages.

Revision ID: 010
Revises: 009
Create Date: 2026-02-12

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_reviews_outlet_published",
        "reviews",
        ["outlet_id", "published_at"],
    )
    op.create_index(
        "idx_reviews_journalist_published",
        "reviews",
        ["journalist_id", "published_at"],
    )
    op.create_index(
        "idx_reviews_game_published",
        "reviews",
        ["game_id", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_reviews_game_published", table_name="reviews")
    op.drop_index("idx_reviews_journalist_published", table_name="reviews")
    op.drop_index("idx_reviews_outlet_published", table_name="reviews")

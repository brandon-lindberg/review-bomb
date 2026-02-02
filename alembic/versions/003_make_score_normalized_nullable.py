"""Make score_normalized nullable for unscored reviews

Reviews from outlets that don't use numeric scores (e.g., Rock Paper Shotgun,
Kotaku's recommendation system) should have NULL score_normalized rather than
a fake 0 or 100 value.

Revision ID: 003
Revises: 002
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make score_normalized nullable to allow unscored reviews
    op.alter_column('reviews', 'score_normalized',
                    existing_type=sa.Numeric(precision=5, scale=2),
                    nullable=True)


def downgrade() -> None:
    # First, set any NULL values to 0 before making NOT NULL again
    op.execute("UPDATE reviews SET score_normalized = 0 WHERE score_normalized IS NULL")
    op.alter_column('reviews', 'score_normalized',
                    existing_type=sa.Numeric(precision=5, scale=2),
                    nullable=False)

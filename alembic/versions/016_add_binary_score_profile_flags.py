"""Add binary score profile flags for journalists and outlets.

Revision ID: 016
Revises: 015
Create Date: 2026-02-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "journalists",
        sa.Column(
            "is_binary_reviewer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "outlets",
        sa.Column(
            "is_binary_scorer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("outlets", "is_binary_scorer")
    op.drop_column("journalists", "is_binary_reviewer")

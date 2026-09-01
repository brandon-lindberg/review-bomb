"""Add HNSW index for Similar Games V3 prototype-vector recall.

Revision ID: 025
Revises: 024
"""

from typing import Union

from alembic import op


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_similarity_v3_documents_prototype_embedding
        ON game_similarity_v3_documents
        USING hnsw (prototype_embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_game_similarity_v3_documents_prototype_embedding")

"""Add Similar Games V3 pgvector-backed storage.

Revision ID: 023
Revises: 022
Create Date: 2026-04-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models.pgvector_type import PGVector


# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    empty_text_array = sa.text("'{}'::text[]")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column("games", sa.Column("similarity_v3_version", sa.String(length=64), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "similarity_v3_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'hidden'"),
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "similarity_v3_dirty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "games",
        sa.Column(
            "similarity_v3_dirty_reasons",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=empty_text_array,
        ),
    )
    op.add_column("games", sa.Column("similarity_v3_computed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("games", sa.Column("similarity_v3_debug_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "game_similarity_v3_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("similarity_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_backend", sa.String(length=64), nullable=False),
        sa.Column("provider_text_doc", sa.Text(), nullable=True),
        sa.Column("structured_label_doc", sa.Text(), nullable=True),
        sa.Column("fingerprint_doc", sa.Text(), nullable=True),
        sa.Column("synthetic_summary_doc", sa.Text(), nullable=True),
        sa.Column("fused_doc", sa.Text(), nullable=True),
        sa.Column("fused_doc_hash", sa.String(length=64), nullable=True),
        sa.Column("fingerprint_doc_hash", sa.String(length=64), nullable=True),
        sa.Column("fused_embedding", PGVector(384), nullable=True),
        sa.Column("fingerprint_embedding", PGVector(384), nullable=True),
        sa.Column("prototype_embedding", PGVector(384), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id"),
    )
    op.create_index(
        "idx_game_similarity_v3_documents_version_backend",
        "game_similarity_v3_documents",
        ["similarity_version", "embedding_backend"],
        unique=False,
    )

    op.create_table(
        "game_similarity_v3_neighbors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("anchor_game_id", sa.Integer(), nullable=False),
        sa.Column("candidate_game_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("final_score", sa.Numeric(8, 4), nullable=False),
        sa.Column("taxonomy_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("text_vector_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("facet_vector_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("prototype_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("rerank_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("quality_prior", sa.Numeric(8, 4), nullable=True),
        sa.Column("relationship_type", sa.String(length=64), nullable=True),
        sa.Column(
            "used_vector_exception",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("explanation_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("similarity_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["anchor_game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "anchor_game_id",
            "candidate_game_id",
            "similarity_version",
            name="uq_game_similarity_v3_neighbors_anchor_candidate_version",
        ),
    )
    op.create_index(
        "idx_game_similarity_v3_neighbors_anchor_rank",
        "game_similarity_v3_neighbors",
        ["anchor_game_id", "rank"],
        unique=False,
    )
    op.create_index(
        "idx_game_similarity_v3_neighbors_anchor_version",
        "game_similarity_v3_neighbors",
        ["anchor_game_id", "similarity_version"],
        unique=False,
    )

    op.create_table(
        "game_similarity_v3_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("similarity_version", sa.String(length=64), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=64), nullable=True),
        sa.Column("embedding_backend", sa.String(length=64), nullable=True),
        sa.Column("reranker_backend", sa.String(length=64), nullable=True),
        sa.Column("gold_set_version", sa.String(length=64), nullable=True),
        sa.Column("corpus_hash", sa.String(length=64), nullable=True),
        sa.Column("summary_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_game_similarity_v3_runs_similarity_version"),
        "game_similarity_v3_runs",
        ["similarity_version"],
        unique=False,
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_similarity_v3_documents_fused_embedding
        ON game_similarity_v3_documents
        USING hnsw (fused_embedding vector_cosine_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_game_similarity_v3_documents_fingerprint_embedding
        ON game_similarity_v3_documents
        USING hnsw (fingerprint_embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_game_similarity_v3_documents_fingerprint_embedding")
    op.execute("DROP INDEX IF EXISTS idx_game_similarity_v3_documents_fused_embedding")
    op.drop_index(op.f("ix_game_similarity_v3_runs_similarity_version"), table_name="game_similarity_v3_runs")
    op.drop_table("game_similarity_v3_runs")
    op.drop_index("idx_game_similarity_v3_neighbors_anchor_version", table_name="game_similarity_v3_neighbors")
    op.drop_index("idx_game_similarity_v3_neighbors_anchor_rank", table_name="game_similarity_v3_neighbors")
    op.drop_table("game_similarity_v3_neighbors")
    op.drop_index("idx_game_similarity_v3_documents_version_backend", table_name="game_similarity_v3_documents")
    op.drop_table("game_similarity_v3_documents")
    op.drop_column("games", "similarity_v3_debug_payload")
    op.drop_column("games", "similarity_v3_computed_at")
    op.drop_column("games", "similarity_v3_dirty_reasons")
    op.drop_column("games", "similarity_v3_dirty")
    op.drop_column("games", "similarity_v3_status")
    op.drop_column("games", "similarity_v3_version")

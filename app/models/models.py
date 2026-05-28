"""
SQLAlchemy models for the Game Journalist Review Disparity Tracker.

Key design decisions:
- Outlet is associated per-review (not per-journalist) since journalists change jobs
- All scores normalized to 0-100 scale
- Date cutoff: January 1, 2015
"""

import enum
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional, List

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    Text,
    Numeric,
    Date,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
    Enum,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.public_ids import generate_public_id
from app.models.pgvector_type import PGVector


class Base(DeclarativeBase):
    pass


# Enums
class UserScoreSource(enum.Enum):
    STEAM = "steam"
    METACRITIC = "metacritic"


class SyncSource(enum.Enum):
    OPENCRITIC = "opencritic"
    STEAM = "steam"
    METACRITIC = "metacritic"


class SyncType(enum.Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class SyncStatus(enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Outlet(Base):
    """
    Gaming publications/outlets (IGN, GameSpot, Polygon, etc.)
    """
    __tablename__ = "outlets"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False, default=generate_public_id
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    opencritic_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(512))
    logo_url: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Denormalized stats for fast leaderboard queries
    avg_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    review_count_scored: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    journalist_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    score_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    is_binary_scorer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    reviews: Mapped[List["Review"]] = relationship(back_populates="outlet")
    disparity_snapshots: Mapped[List["DisparitySnapshot"]] = relationship(
        back_populates="outlet"
    )

    __table_args__ = (
        Index("idx_outlets_name", "name"),
    )


class Journalist(Base):
    """
    Individual game journalists/critics.
    Note: outlet is NOT stored here - it's per-review since journalists change jobs.
    """
    __tablename__ = "journalists"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False, default=generate_public_id
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    opencritic_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    
    # Denormalized stats for fast leaderboard queries
    avg_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    review_count_scored: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    score_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    is_binary_reviewer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    primary_outlet: Mapped[Optional[str]] = mapped_column(String(255))
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    reviews: Mapped[List["Review"]] = relationship(back_populates="journalist")
    disparity_snapshots: Mapped[List["DisparitySnapshot"]] = relationship(
        back_populates="journalist"
    )

    __table_args__ = (
        Index("idx_journalists_name", "name"),
    )


class Game(Base):
    """
    Video games being tracked.
    """
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False, default=generate_public_id
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    opencritic_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    steam_app_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    metacritic_slug: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    opencritic_description: Mapped[Optional[str]] = mapped_column(Text)
    steam_short_description: Mapped[Optional[str]] = mapped_column(Text)
    steam_detailed_description: Mapped[Optional[str]] = mapped_column(Text)
    metacritic_description: Mapped[Optional[str]] = mapped_column(Text)
    release_date: Mapped[Optional[date]] = mapped_column(Date, index=True)

    # OpenCritic aggregate scores (for reference)
    top_critic_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    percent_recommended: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    tier: Mapped[Optional[str]] = mapped_column(String(50))  # 'Mighty', 'Strong', etc.

    # Metacritic critic aggregate score (0-100)
    metacritic_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    # Denormalized stats for fast queries
    avg_critic_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    critic_review_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    steam_user_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    steam_sample_size: Mapped[Optional[int]] = mapped_column(Integer)
    metacritic_user_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    metacritic_sample_size: Mapped[Optional[int]] = mapped_column(Integer)
    disparity_steam: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    disparity_metacritic: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    # Steam activity snapshots and denormalized stats
    steam_current_players: Mapped[Optional[int]] = mapped_column(Integer)
    steam_current_players_sampled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    steam_player_24h_peak: Mapped[Optional[int]] = mapped_column(Integer)
    steam_player_24h_low_observed: Mapped[Optional[int]] = mapped_column(Integer)
    steam_player_all_time_peak: Mapped[Optional[int]] = mapped_column(Integer)
    steam_player_all_time_peak_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    steam_player_stats_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    steam_achievement_count: Mapped[Optional[int]] = mapped_column(Integer)
    steam_achievement_count_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    taxonomy_genres: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_themes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_modes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_perspectives: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_studios: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_publishers: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    taxonomy_v2_version: Mapped[Optional[str]] = mapped_column(String(64))
    taxonomy_v2_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    taxonomy_v2_primary_family: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    taxonomy_v2_primary_archetype: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    taxonomy_v2_secondary_archetypes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_v2_hard_exclusions: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_v2_soft_penalties: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_v2_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    taxonomy_v2_text_corpus: Mapped[Optional[str]] = mapped_column(Text)
    taxonomy_v2_text_sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    taxonomy_v2_text_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    taxonomy_v2_fingerprint: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    taxonomy_v2_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    taxonomy_v2_curated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    taxonomy_v2_debug_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    similarity_v3_version: Mapped[Optional[str]] = mapped_column(String(64))
    similarity_v3_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="hidden",
        server_default=text("'hidden'"),
    )
    similarity_v3_dirty: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    similarity_v3_dirty_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    similarity_v3_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    similarity_v3_debug_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)

    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    last_review_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metacritic_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    reviews: Mapped[List["Review"]] = relationship(back_populates="game")
    user_scores: Mapped[List["UserScore"]] = relationship(back_populates="game")
    disparity_snapshots: Mapped[List["DisparitySnapshot"]] = relationship(
        back_populates="game"
    )
    news_articles: Mapped[List["NewsArticle"]] = relationship(back_populates="game")
    steam_player_snapshots: Mapped[List["SteamPlayerSnapshot"]] = relationship(
        back_populates="game"
    )
    steam_player_range_snapshots: Mapped[List["SteamPlayerRangeSnapshot"]] = relationship(
        back_populates="game"
    )
    source_taxonomy_labels: Mapped[List["GameSourceTaxonomyLabel"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    taxonomy_v2_evidence_rows: Mapped[List["GameTaxonomyV2Evidence"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    similarity_v3_document: Mapped[Optional["GameSimilarityV3Document"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index("idx_games_release_date", "release_date"),
    )


class GameSimilarityV3Document(Base):
    """Precomputed V3 corpus artifacts and embeddings for one game."""

    __tablename__ = "game_similarity_v3_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    similarity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_backend: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_text_doc: Mapped[Optional[str]] = mapped_column(Text)
    structured_label_doc: Mapped[Optional[str]] = mapped_column(Text)
    fingerprint_doc: Mapped[Optional[str]] = mapped_column(Text)
    synthetic_summary_doc: Mapped[Optional[str]] = mapped_column(Text)
    fused_doc: Mapped[Optional[str]] = mapped_column(Text)
    fused_doc_hash: Mapped[Optional[str]] = mapped_column(String(64))
    fingerprint_doc_hash: Mapped[Optional[str]] = mapped_column(String(64))
    fused_embedding: Mapped[Optional[list[float]]] = mapped_column(PGVector(384))
    fingerprint_embedding: Mapped[Optional[list[float]]] = mapped_column(PGVector(384))
    prototype_embedding: Mapped[Optional[list[float]]] = mapped_column(PGVector(384))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    game: Mapped["Game"] = relationship(back_populates="similarity_v3_document")

    __table_args__ = (
        Index(
            "idx_game_similarity_v3_documents_version_backend",
            "similarity_version",
            "embedding_backend",
        ),
    )


class GameSimilarityV3Neighbor(Base):
    """Published Similar Games V3 neighbors served by the live API."""

    __tablename__ = "game_similarity_v3_neighbors"

    id: Mapped[int] = mapped_column(primary_key=True)
    anchor_game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    taxonomy_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    text_vector_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    facet_vector_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    prototype_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    rerank_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    quality_prior: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    relationship_type: Mapped[Optional[str]] = mapped_column(String(64))
    used_vector_exception: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    explanation_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    similarity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "anchor_game_id",
            "candidate_game_id",
            "similarity_version",
            name="uq_game_similarity_v3_neighbors_anchor_candidate_version",
        ),
        Index(
            "idx_game_similarity_v3_neighbors_anchor_rank",
            "anchor_game_id",
            "rank",
        ),
        Index(
            "idx_game_similarity_v3_neighbors_anchor_version",
            "anchor_game_id",
            "similarity_version",
        ),
    )


class GameSimilarityV3Run(Base):
    """Metadata for a published Similar Games V3 batch."""

    __tablename__ = "game_similarity_v3_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    similarity_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    taxonomy_version: Mapped[Optional[str]] = mapped_column(String(64))
    embedding_backend: Mapped[Optional[str]] = mapped_column(String(64))
    reranker_backend: Mapped[Optional[str]] = mapped_column(String(64))
    gold_set_version: Mapped[Optional[str]] = mapped_column(String(64))
    corpus_hash: Mapped[Optional[str]] = mapped_column(String(64))
    summary_metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Review(Base):
    """
    Individual critic reviews.

    Key design: outlet_id is here (not on journalist) because journalists
    move between outlets over their careers.
    """
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    journalist_id: Mapped[int] = mapped_column(
        ForeignKey("journalists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outlet_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("outlets.id", ondelete="SET NULL"), index=True
    )

    # Score information
    score_raw: Mapped[str] = mapped_column(String(50), nullable=False)  # "8.5", "4/5", "B+"
    score_scale: Mapped[Optional[str]] = mapped_column(String(50))  # "10", "5", "100", "letter"
    score_normalized: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))  # 0-100, NULL for unscored
    # Pipeline-cached user scores/disparities used by review endpoints to avoid live disparity math
    cached_steam_user_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    cached_metacritic_user_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    cached_disparity_steam: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    cached_disparity_metacritic: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    cached_disparity_combined: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    # Citation (link to original article)
    review_url: Mapped[Optional[str]] = mapped_column(String(1024))
    snippet: Mapped[Optional[str]] = mapped_column(Text)  # First 200-300 chars of review

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    opencritic_review_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    journalist: Mapped["Journalist"] = relationship(back_populates="reviews")
    game: Mapped["Game"] = relationship(back_populates="reviews")
    outlet: Mapped[Optional["Outlet"]] = relationship(back_populates="reviews")

    __table_args__ = (
        # Note: uq_journalist_game was removed - journalists can review
        # the same game multiple times (different platforms, updated reviews).
        # The opencritic_review_id unique constraint prevents true duplicates.
        Index("idx_reviews_published_at", "published_at"),
        Index("idx_reviews_score_normalized", "score_normalized"),
        Index("idx_reviews_outlet_published", "outlet_id", "published_at"),
        Index("idx_reviews_journalist_published", "journalist_id", "published_at"),
        Index("idx_reviews_game_published", "game_id", "published_at"),
    )


class UserScore(Base):
    """
    User/player scores from Steam and Metacritic.
    Stored separately and updated periodically.
    """
    __tablename__ = "user_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[UserScoreSource] = mapped_column(
        Enum(UserScoreSource), nullable=False, index=True
    )

    # Score normalized to 0-100
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    score_raw: Mapped[Optional[str]] = mapped_column(String(50))  # Original format

    # Sample size and breakdown
    sample_size: Mapped[Optional[int]] = mapped_column(Integer)  # Total reviews
    positive_count: Mapped[Optional[int]] = mapped_column(Integer)  # Steam: thumbs up
    negative_count: Mapped[Optional[int]] = mapped_column(Integer)  # Steam: thumbs down
    review_score_desc: Mapped[Optional[str]] = mapped_column(String(100))  # "Very Positive"

    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    game: Mapped["Game"] = relationship(back_populates="user_scores")

    __table_args__ = (
        Index("idx_user_scores_scraped_at", "scraped_at"),
    )


class SteamPlayerSnapshot(Base):
    """
    Time-series snapshots of Steam concurrent players.
    """
    __tablename__ = "steam_player_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrent_players: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    game: Mapped["Game"] = relationship(back_populates="steam_player_snapshots")

    __table_args__ = (
        Index("idx_steam_player_snapshots_game_sampled", "game_id", "sampled_at"),
        Index("idx_steam_player_snapshots_sampled_at", "sampled_at"),
    )


class SteamPlayerRangeSnapshot(Base):
    """
    Time-series 24-hour high/low range points derived from tracked Steam history.
    """
    __tablename__ = "steam_player_range_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    players_24h_high: Mapped[int] = mapped_column(Integer, nullable=False)
    players_24h_low: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    game: Mapped["Game"] = relationship(back_populates="steam_player_range_snapshots")

    __table_args__ = (
        UniqueConstraint("game_id", "sampled_at", name="uq_steam_player_range_snapshots_game_sampled"),
        Index("idx_steam_player_range_snapshots_game_sampled", "game_id", "sampled_at"),
        Index("idx_steam_player_range_snapshots_sampled_at", "sampled_at"),
    )


class GameSourceTaxonomyLabel(Base):
    """Raw source taxonomy labels captured per game/source/facet."""

    __tablename__ = "game_source_taxonomy_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    facet: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_label: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    game: Mapped["Game"] = relationship(back_populates="source_taxonomy_labels")

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "source",
            "facet",
            "normalized_label",
            name="uq_game_source_taxonomy_labels_game_source_facet_label",
        ),
        Index("idx_game_source_taxonomy_labels_game_source", "game_id", "source"),
        Index(
            "idx_game_source_taxonomy_labels_source_facet_normalized",
            "source",
            "facet",
            "normalized_label",
        ),
    )


class GameTaxonomyV2Evidence(Base):
    """Per-field evidence rows that explain V2 fingerprint assignments."""

    __tablename__ = "game_taxonomy_v2_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_field: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    curated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    conflict_group: Mapped[Optional[str]] = mapped_column(String(64))
    suppressed_by_rule: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    game: Mapped["Game"] = relationship(back_populates="taxonomy_v2_evidence_rows")

    __table_args__ = (
        Index("idx_game_taxonomy_v2_evidence_game_id", "game_id"),
        Index(
            "idx_game_taxonomy_v2_evidence_version_field_value",
            "taxonomy_version",
            "field",
            "value",
        ),
        Index(
            "idx_game_taxonomy_v2_evidence_source_source_field",
            "source",
            "source_field",
        ),
        Index("idx_game_taxonomy_v2_evidence_game_field", "game_id", "field"),
    )


class DisparitySnapshot(Base):
    """
    Precomputed disparity statistics for fast leaderboard queries.
    Computed daily for journalists, outlets, and games.
    """
    __tablename__ = "disparity_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Only one of these should be set per row
    journalist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journalists.id", ondelete="CASCADE")
    )
    outlet_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("outlets.id", ondelete="CASCADE")
    )
    game_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE")
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Disparity metrics
    avg_disparity_steam: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    avg_disparity_metacritic: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    avg_disparity_combined: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    std_deviation: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    min_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    max_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    journalist: Mapped[Optional["Journalist"]] = relationship(back_populates="disparity_snapshots")
    outlet: Mapped[Optional["Outlet"]] = relationship(back_populates="disparity_snapshots")
    game: Mapped[Optional["Game"]] = relationship(back_populates="disparity_snapshots")

    __table_args__ = (
        # Ensure only one entity type per row
        CheckConstraint(
            """
            (journalist_id IS NOT NULL AND outlet_id IS NULL AND game_id IS NULL) OR
            (journalist_id IS NULL AND outlet_id IS NOT NULL AND game_id IS NULL) OR
            (journalist_id IS NULL AND outlet_id IS NULL AND game_id IS NOT NULL)
            """,
            name="ck_single_entity_type"
        ),
        Index("idx_disparity_journalist", "journalist_id", "snapshot_date"),
        Index("idx_disparity_outlet", "outlet_id", "snapshot_date"),
        Index("idx_disparity_game", "game_id", "snapshot_date"),
    )


class JournalistOutletDisparitySnapshot(Base):
    """
    Precomputed disparity statistics for a journalist at a specific outlet.
    Used to avoid live disparity math on journalist outlet breakdowns.
    """
    __tablename__ = "journalist_outlet_disparity_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    journalist_id: Mapped[int] = mapped_column(
        ForeignKey("journalists.id", ondelete="CASCADE"),
        nullable=False,
    )
    outlet_id: Mapped[int] = mapped_column(
        ForeignKey("outlets.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    avg_disparity_steam: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    avg_disparity_metacritic: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    avg_disparity_combined: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    std_deviation: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    min_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    max_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_journalist_outlet_disparity_pair",
            "journalist_id",
            "outlet_id",
            "snapshot_date",
        ),
        Index("idx_journalist_outlet_disparity_journalist", "journalist_id", "snapshot_date"),
        Index("idx_journalist_outlet_disparity_outlet", "outlet_id", "snapshot_date"),
    )


class SyncState(Base):
    """
    Persistent sync state for budget-aware daily syncing.
    Tracks which games have been synced and daily API request counts.
    """
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_sync_state_key", "key"),
    )


class OpenCriticMalformedGame(Base):
    """
    Quarantined OpenCritic game payloads that are not safe to publish as games.
    """
    __tablename__ = "opencritic_malformed_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    opencritic_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(1024))
    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_opencritic_malformed_games_reason", "reason", "last_seen_at"),
    )


class NewsArticle(Base):
    """
    Gaming news articles fetched from RSS feeds.
    Users can preview articles and click through to the original source.
    """
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1024))
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    game_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    game: Mapped[Optional["Game"]] = relationship(back_populates="news_articles")

    __table_args__ = (
        Index("idx_news_source_published", "source_name", "published_at"),
        Index("idx_news_game_published", "game_id", "published_at"),
    )


class SyncLog(Base):
    """
    Tracks data synchronization jobs for monitoring and debugging.
    """
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[SyncSource] = mapped_column(Enum(SyncSource), nullable=False)
    sync_type: Mapped[SyncType] = mapped_column(Enum(SyncType), nullable=False)
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus), nullable=False, default=SyncStatus.RUNNING
    )

    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[Optional[str]] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_sync_logs_source", "source", "started_at"),
    )

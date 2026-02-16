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
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    opencritic_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(512))
    logo_url: Mapped[Optional[str]] = mapped_column(String(512))
    
    # Denormalized stats for fast leaderboard queries
    avg_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    review_count_scored: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    journalist_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    score_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    opencritic_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    
    # Denormalized stats for fast leaderboard queries
    avg_disparity: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    review_count_scored: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    score_std_dev: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
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
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    opencritic_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    steam_app_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    metacritic_slug: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
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

    __table_args__ = (
        Index("idx_games_release_date", "release_date"),
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

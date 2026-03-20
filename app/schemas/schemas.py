"""
Pydantic schemas for API request/response validation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Generic, TypeVar, List

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


# =============================================================================
# Pagination
# =============================================================================


class PaginationParams(BaseModel):
    """Common pagination parameters."""
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: List[T]
    total: int
    page: int
    per_page: int
    total_pages: int


# =============================================================================
# Outlet Schemas
# =============================================================================


class OutletBase(BaseModel):
    """Base outlet fields."""
    name: str
    website_url: Optional[str] = None
    logo_url: Optional[str] = None


class OutletCreate(OutletBase):
    """Schema for creating an outlet."""
    opencritic_id: Optional[int] = None


class OutletSummary(OutletBase):
    """Summary outlet info for lists."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    opencritic_id: Optional[int] = None
    is_binary_scorer: bool = False


class OutletWithStats(OutletSummary):
    """Outlet with aggregated statistics."""
    journalist_count: int = 0
    review_count: int = 0
    avg_disparity: Optional[Decimal] = None
    avg_disparity_steam: Optional[Decimal] = None
    avg_disparity_metacritic: Optional[Decimal] = None
    avg_disparity_combined: Optional[Decimal] = None
    avg_score: Optional[Decimal] = None
    # Transparency metrics - timing
    early_review_count: int = 0
    launch_window_review_count: int = 0
    late_review_count: int = 0
    # Transparency metrics - scoring patterns
    min_score_given: Optional[Decimal] = None
    max_score_given: Optional[Decimal] = None
    score_std_deviation: Optional[Decimal] = None  # Std dev of scores given
    latest_review: Optional["ReviewWithJournalist"] = None


class OutletDetail(OutletSummary):
    """Full outlet details."""
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Journalist Schemas
# =============================================================================


class JournalistBase(BaseModel):
    """Base journalist fields."""
    name: str
    image_url: Optional[str] = None
    bio: Optional[str] = None


class JournalistCreate(JournalistBase):
    """Schema for creating a journalist."""
    opencritic_id: Optional[int] = None


class JournalistLatestReview(BaseModel):
    """Most recent scored review summary for journalist list pages."""
    review_id: int
    game_id: int
    game_public_id: str
    game_title: str
    game_release_date: Optional[date] = None
    outlet_name: Optional[str] = None
    snippet: Optional[str] = None
    score_normalized: Optional[Decimal] = None
    published_at: Optional[datetime] = None
    review_timing: str = "unknown"  # "early" | "launch_window" | "late" | "unknown"


class JournalistSummary(JournalistBase):
    """Summary journalist info for lists."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    opencritic_id: Optional[int] = None
    is_binary_reviewer: bool = False
    review_count: int = 0
    avg_disparity: Optional[Decimal] = None
    latest_review: Optional[JournalistLatestReview] = None


class JournalistStats(BaseModel):
    """Aggregated statistics for a journalist."""
    total_reviews: int
    avg_score_given: Optional[Decimal] = None

    # Launch window disparity (reviews within 60 days of game release)
    avg_disparity_steam: Optional[Decimal] = None
    avg_disparity_metacritic: Optional[Decimal] = None
    avg_disparity_combined: Optional[Decimal] = None

    # Overall disparity (all reviews, including late ones)
    overall_disparity_steam: Optional[Decimal] = None
    overall_disparity_metacritic: Optional[Decimal] = None
    overall_disparity_combined: Optional[Decimal] = None

    std_deviation: Optional[Decimal] = None
    alignment_rating: Optional[Decimal] = None  # Percentage aligned with users

    # Transparency metrics - timing
    early_review_count: int = 0  # Reviews before game release
    launch_window_review_count: int = 0  # Reviews within 60 days of release
    late_review_count: int = 0  # Reviews after 60 days

    # Transparency metrics - scoring patterns
    min_score_given: Optional[Decimal] = None
    max_score_given: Optional[Decimal] = None
    score_std_deviation: Optional[Decimal] = None  # Std dev of scores given (not disparity)


class JournalistOutletBreakdown(BaseModel):
    """Journalist's stats at a specific outlet."""
    outlet_id: int
    outlet_public_id: str
    outlet_name: str
    review_count: int
    avg_disparity: Optional[Decimal] = None
    date_range_start: Optional[date] = None
    date_range_end: Optional[date] = None


class JournalistDetail(JournalistSummary):
    """Full journalist details with stats."""
    stats: JournalistStats
    outlet_breakdown: List[JournalistOutletBreakdown] = []
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Game Schemas
# =============================================================================


class GameBase(BaseModel):
    """Base game fields."""
    title: str
    release_date: Optional[date] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class GameCreate(GameBase):
    """Schema for creating a game."""
    opencritic_id: Optional[int] = None
    steam_app_id: Optional[int] = None
    metacritic_slug: Optional[str] = None


class GameSummary(GameBase):
    """Summary game info for lists."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    public_id: str
    opencritic_id: Optional[int] = None
    steam_app_id: Optional[int] = None
    critic_review_count: int = 0


class GameWithScores(GameSummary):
    """Game with all score information."""
    opencritic_score: Optional[Decimal] = None
    steam_user_score: Optional[Decimal] = None
    steam_sample_size: Optional[int] = None
    steam_current_players: Optional[int] = None
    steam_current_players_sampled_at: Optional[datetime] = None
    steam_activity_preview: List[int] = Field(default_factory=list)
    steam_player_24h_peak: Optional[int] = None
    steam_player_24h_low_observed: Optional[int] = None
    steam_player_all_time_peak: Optional[int] = None
    steam_player_all_time_peak_at: Optional[datetime] = None
    steam_player_stats_synced_at: Optional[datetime] = None
    steam_achievement_count: Optional[int] = None
    steam_achievement_count_synced_at: Optional[datetime] = None
    metacritic_user_score: Optional[Decimal] = None
    metacritic_sample_size: Optional[int] = None
    avg_critic_score: Optional[Decimal] = None
    disparity_steam: Optional[Decimal] = None
    disparity_metacritic: Optional[Decimal] = None
    latest_review: Optional["ReviewWithJournalist"] = None


class GameDetail(GameWithScores):
    """Full game details."""
    tier: Optional[str] = None
    percent_recommended: Optional[Decimal] = None
    early_review_count: int = 0
    launch_window_review_count: int = 0
    late_review_count: int = 0
    created_at: datetime
    updated_at: datetime
    recent_news: list["NewsArticleSummary"] = []


class SteamPlayerPoint(BaseModel):
    """Single observed 24-hour high/low chart point."""
    sampled_at: datetime
    observed_24h_high: int
    observed_24h_low: int
    latest_players: Optional[int] = None


class SteamPlayerMarker(BaseModel):
    """Curated player milestone marker."""
    marker_type: str
    sampled_at: datetime
    concurrent_players: int
    label: str
    detail: Optional[str] = None


class SteamActivityResponse(BaseModel):
    """Steam activity payload for charts and timelines."""
    summary: GameWithScores
    points: list[SteamPlayerPoint] = []
    markers: list[SteamPlayerMarker] = []


# =============================================================================
# Review Schemas
# =============================================================================


class ReviewBase(BaseModel):
    """Base review fields."""
    score_raw: str
    score_scale: Optional[str] = None
    score_normalized: Decimal
    review_url: Optional[str] = None
    snippet: Optional[str] = None
    published_at: Optional[datetime] = None


class ReviewCreate(ReviewBase):
    """Schema for creating a review."""
    journalist_id: int
    game_id: int
    outlet_id: Optional[int] = None
    opencritic_review_id: Optional[str] = None


class ReviewSummary(ReviewBase):
    """Summary review info."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    journalist_id: int
    journalist_public_id: Optional[str] = None
    game_id: int
    game_public_id: Optional[str] = None
    outlet_id: Optional[int] = None
    outlet_public_id: Optional[str] = None


class ReviewWithDisparity(ReviewSummary):
    """Review with calculated disparity."""
    game_title: str
    game_release_date: Optional[date] = None  # For review timing tooltip
    outlet_name: Optional[str] = None
    steam_user_score: Optional[Decimal] = None
    metacritic_user_score: Optional[Decimal] = None
    disparity_steam: Optional[Decimal] = None
    disparity_metacritic: Optional[Decimal] = None
    is_launch_window: bool = False  # Deprecated - use review_timing instead
    review_timing: str = "unknown"  # "early" | "launch_window" | "late" | "unknown"


class ReviewWithJournalist(ReviewSummary):
    """Review with journalist info (for game/outlet detail pages)."""
    journalist_name: str
    journalist_image_url: Optional[str] = None
    outlet_name: Optional[str] = None
    game_title: Optional[str] = None  # For outlet pages
    game_release_date: Optional[date] = None  # For review timing tooltip
    disparity_steam: Optional[Decimal] = None
    disparity_metacritic: Optional[Decimal] = None
    is_launch_window: bool = False  # Deprecated - use review_timing instead
    review_timing: str = "unknown"  # "early" | "launch_window" | "late" | "unknown"


# =============================================================================
# User Score Schemas
# =============================================================================


class UserScoreBase(BaseModel):
    """Base user score fields."""
    score: Decimal
    score_raw: Optional[str] = None
    sample_size: Optional[int] = None


class UserScoreCreate(UserScoreBase):
    """Schema for creating a user score."""
    game_id: int
    source: str  # "steam" or "metacritic"
    positive_count: Optional[int] = None
    negative_count: Optional[int] = None
    review_score_desc: Optional[str] = None
    scraped_at: datetime


class UserScoreSummary(UserScoreBase):
    """Summary user score info."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    source: str
    scraped_at: datetime


# =============================================================================
# Disparity Schemas
# =============================================================================


class DisparitySnapshot(BaseModel):
    """Disparity data point for charts."""
    date: date
    avg_disparity_steam: Optional[Decimal] = None
    avg_disparity_metacritic: Optional[Decimal] = None
    avg_disparity_combined: Optional[Decimal] = None
    review_count: int


# =============================================================================
# Leaderboard Schemas
# =============================================================================


class JournalistRanking(BaseModel):
    """Journalist in leaderboard."""
    rank: int
    journalist_id: int
    journalist_public_id: str
    journalist_name: str
    journalist_image_url: Optional[str] = None
    outlet_name: Optional[str] = None  # Most recent outlet
    avg_disparity: Decimal
    review_count: int


class OutletRanking(BaseModel):
    """Outlet in leaderboard."""
    rank: int
    outlet_id: int
    outlet_public_id: str
    outlet_name: str
    outlet_logo_url: Optional[str] = None
    avg_disparity: Decimal
    journalist_count: int
    review_count: int


class GameRanking(BaseModel):
    """Game in leaderboard (most divisive)."""
    rank: int
    game_id: int
    game_public_id: str
    game_title: str
    game_image_url: Optional[str] = None
    release_date: Optional[date] = None
    avg_critic_score: Decimal
    steam_user_score: Optional[Decimal] = None
    metacritic_user_score: Optional[Decimal] = None
    disparity: Decimal
    disparity_steam: Optional[Decimal] = None
    disparity_metacritic: Optional[Decimal] = None
    critic_review_count: int


# =============================================================================
# Search Schemas
# =============================================================================


class SearchResult(BaseModel):
    """Combined search results."""
    journalists: List[JournalistSummary] = []
    outlets: List[OutletSummary] = []
    games: List[GameSummary] = []


# =============================================================================
# Stats Schemas
# =============================================================================


class SiteStats(BaseModel):
    """Site-wide statistics."""
    total_journalists: int
    total_outlets: int
    total_games: int
    total_reviews: int
    avg_disparity_site: Optional[Decimal] = None
    last_updated: datetime


class TrendingGameItem(BaseModel):
    """Trending game/topic entry for the home page."""

    rank: int
    trend_key: str
    title: str
    game_id: Optional[int] = None
    game_public_id: Optional[str] = None
    release_date: Optional[date] = None
    image_url: Optional[str] = None
    is_linked: bool
    is_upcoming: bool
    latest_article_at: Optional[datetime] = None
    latest_article_url: Optional[str] = None
    news_mention_count: int
    news_source_count: int
    trend_score: float
    source_scores: dict[str, float] = Field(default_factory=dict)


class TrendingGamesResponse(BaseModel):
    """Trending games response envelope."""

    as_of: datetime
    window_hours: int
    items: list[TrendingGameItem]


# =============================================================================
# News Article Schemas
# =============================================================================


class NewsArticleSummary(BaseModel):
    """News article preview for lists."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    source_name: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None

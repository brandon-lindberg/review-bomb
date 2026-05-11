"""
Application configuration using pydantic-settings.
"""

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Game Journalist Review Disparity Tracker"
    debug: bool = False
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/review_disparity"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # External APIs
    rapidapi_key: Optional[str] = None
    opencritic_api_host: str = "opencritic-api.p.rapidapi.com"
    player_scraper_base_url: Optional[str] = None
    player_scraper_api_token: Optional[str] = None
    player_scraper_timeout_seconds: float = 15.0

    # Token the player-count-scraper presents when reading the internal registry endpoint.
    # Keep separate from player_scraper_api_token (which is for outbound calls).
    scraper_api_token: Optional[str] = None

    # Rate limiting
    rate_limit_per_minute: int = 100
    search_rate_limit_per_minute: int = 10

    # Data constraints
    data_cutoff_date: str = "2015-01-01"  # Only track reviews from this date

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Sentry (optional)
    sentry_dsn: Optional[str] = None

    # Security
    allowed_hosts: list[str] = []  # Empty = allow all (dev), set in production

    # Optional frontend on-demand revalidation webhook (Next.js app route)
    frontend_revalidate_url: Optional[str] = None
    frontend_revalidate_secret: Optional[str] = None

    @field_validator("debug", mode="before")
    @classmethod
    def coerce_debug_value(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "debug", "development", "dev"}:
            return True
        if normalized in {"false", "0", "no", "off", "release", "production", "prod"}:
            return False
        return value


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

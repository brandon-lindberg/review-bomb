"""
OpenCritic API service.

Fetches critics, outlets, games, and reviews from OpenCritic via RapidAPI.
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal

import httpx
from aiolimiter import AsyncLimiter

from app.config import get_settings
from app.services.score_normalizer import ScoreNormalizer

settings = get_settings()

# Rate limit: 100 requests per second (Premium plan - expires after 1 month)
# TODO: Revert to 10 requests/second after premium plan expires
rate_limiter = AsyncLimiter(100, 1)


class OpenCriticAuthError(RuntimeError):
    """Raised when OpenCritic API credentials are missing or invalid."""


class OpenCriticService:
    """Service for interacting with the OpenCritic API."""

    BASE_URL = "https://opencritic-api.p.rapidapi.com"
    IMAGE_CDN_URL = "https://img.opencritic.com"

    def __init__(self):
        api_key = (settings.rapidapi_key or "").strip()
        if not api_key:
            raise OpenCriticAuthError(
                "RAPIDAPI_KEY is not configured. Set the environment secret before running sync."
            )

        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": settings.opencritic_api_host,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Make a rate-limited request to the OpenCritic API with retry logic."""
        retryable_status_codes = {429, 500, 502, 503, 504}
        
        for attempt in range(max_retries):
            async with rate_limiter:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    try:
                        response = await client.request(
                            method,
                            f"{self.BASE_URL}{endpoint}",
                            headers=self.headers,
                            params=params,
                        )
                        response.raise_for_status()

                        # Handle empty responses
                        if not response.content:
                            print(f"Empty response from {endpoint}")
                            return None

                        return response.json()
                    except httpx.HTTPStatusError as e:
                        status_code = e.response.status_code
                        if status_code in {401, 403}:
                            raise OpenCriticAuthError(
                                f"OpenCritic API authentication failed ({status_code}). "
                                "Check RAPIDAPI_KEY and RapidAPI subscription status."
                            ) from e
                        if status_code in retryable_status_codes and attempt < max_retries - 1:
                            wait_time = (2 ** attempt) + 1  # 2, 3, 5 seconds
                            print(f"HTTP {status_code} error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            await asyncio.sleep(wait_time)
                            continue
                        print(f"HTTP error {status_code}: {e.response.text[:200]}")
                        return None
                    except httpx.RequestError as e:
                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) + 1
                            print(f"Request error, retrying in {wait_time}s: {e}")
                            await asyncio.sleep(wait_time)
                            continue
                        print(f"Request error after {max_retries} attempts: {e}")
                        return None
                    except ValueError as e:
                        # JSON decode error - don't retry
                        print(f"JSON decode error for {endpoint}: {e}")
                        return None
        
        return None

    # =========================================================================
    # Critics (Journalists)
    # =========================================================================

    async def get_critics(self, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch list of critics from OpenCritic.

        Args:
            skip: Number of records to skip (pagination)
            limit: Number of records to return

        Returns:
            List of critic data dictionaries
        """
        data = await self._request(
            "GET",
            "/critic",
            params={"skip": skip, "limit": limit},
        )
        return data if isinstance(data, list) else []

    async def get_critic(self, critic_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single critic by ID."""
        return await self._request("GET", f"/critic/{critic_id}")

    async def get_all_critics(self) -> List[Dict[str, Any]]:
        """Fetch all critics with pagination."""
        all_critics = []
        skip = 0
        limit = 50

        while True:
            critics = await self.get_critics(skip=skip, limit=limit)
            if not critics:
                break
            all_critics.extend(critics)
            if len(critics) < limit:
                break
            skip += limit
            # Minimal delay with premium plan (100 req/s limit)
            await asyncio.sleep(0.01)

        return all_critics

    # =========================================================================
    # Outlets
    # =========================================================================

    async def get_outlets(self, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch list of outlets from OpenCritic."""
        data = await self._request(
            "GET",
            "/outlet",
            params={"skip": skip, "limit": limit},
        )
        return data if isinstance(data, list) else []

    async def get_outlet(self, outlet_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single outlet by ID."""
        return await self._request("GET", f"/outlet/{outlet_id}")

    async def get_all_outlets(self) -> List[Dict[str, Any]]:
        """Fetch all outlets with pagination."""
        all_outlets = []
        skip = 0
        limit = 50

        while True:
            outlets = await self.get_outlets(skip=skip, limit=limit)
            if not outlets:
                break
            all_outlets.extend(outlets)
            if len(outlets) < limit:
                break
            skip += limit
            # Minimal delay with premium plan (100 req/s limit)
            await asyncio.sleep(0.01)

        return all_outlets

    # =========================================================================
    # Games
    # =========================================================================

    async def get_games(
        self,
        skip: int = 0,
        limit: int = 50,
        sort: str = "date",
    ) -> List[Dict[str, Any]]:
        """Fetch list of games from OpenCritic."""
        data = await self._request(
            "GET",
            "/game",
            params={"skip": skip, "limit": limit, "sort": sort},
        )
        return data if isinstance(data, list) else []

    async def get_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single game by ID with full details."""
        return await self._request("GET", f"/game/{game_id}")

    async def search_games(self, query: str) -> List[Dict[str, Any]]:
        """Search for games by title."""
        data = await self._request(
            "GET",
            "/game/search",
            params={"criteria": query},
        )
        return data if isinstance(data, list) else []

    async def get_all_games(
        self,
        batch_size: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all games from OpenCritic.

        Uses descending date sort to get newest games first.
        """
        all_games = []
        skip = 0

        while True:
            # Fetch games batch
            games = await self.get_games(skip=skip, limit=batch_size, sort="date")
            if not games:
                break
            all_games.extend(games)

            # Advance by the number of records actually returned.
            skip += len(games)
            # Minimal delay with premium plan (100 req/s limit)
            await asyncio.sleep(0.01)

        return all_games

    # =========================================================================
    # Reviews
    # =========================================================================

    async def get_game_reviews(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetch all reviews for a specific game."""
        data = await self._request("GET", f"/reviews/game/{game_id}")
        return data if isinstance(data, list) else []

    async def get_critic_reviews(
        self,
        critic_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch reviews by a specific critic."""
        data = await self._request(
            "GET",
            f"/reviews/critic/{critic_id}",
            params={"skip": skip, "limit": limit},
        )
        return data if isinstance(data, list) else []

    # =========================================================================
    # Data Transformation Helpers
    # =========================================================================

    @classmethod
    def transform_critic(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenCritic critic data to our model format."""
        # Handle image_url which can be a string or dict with size variants
        image_url = data.get("imageSrc")
        if isinstance(image_url, dict):
            image_url = image_url.get("og") or image_url.get("lg") or image_url.get("sm")

        # Convert relative path to full URL
        if image_url and not image_url.startswith("http"):
            image_url = f"{cls.IMAGE_CDN_URL}/{image_url}"

        return {
            "opencritic_id": data.get("id"),
            "name": data.get("name", "Unknown"),
            "image_url": image_url,
            "bio": None,  # OpenCritic doesn't provide bios
        }

    @classmethod
    def transform_outlet(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenCritic outlet data to our model format."""
        # Handle logo_url which can be a string or dict with size variants
        logo_url = data.get("imageSrc")
        if isinstance(logo_url, dict):
            # Prefer 'og' (original), then 'lg', then 'sm'
            logo_url = logo_url.get("og") or logo_url.get("lg") or logo_url.get("sm")

        # Convert relative path to full URL
        if logo_url and not logo_url.startswith("http"):
            logo_url = f"{cls.IMAGE_CDN_URL}/{logo_url}"

        return {
            "opencritic_id": data.get("id"),
            "name": data.get("name", "Unknown"),
            "website_url": data.get("externalUrl"),
            "logo_url": logo_url,
        }

    @classmethod
    def transform_game(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenCritic game data to our model format."""
        release_date = None
        release_date_str = data.get("firstReleaseDate")
        if release_date_str:
            try:
                release_date = datetime.fromisoformat(
                    release_date_str.replace("Z", "+00:00")
                ).date()
            except (ValueError, TypeError):
                pass

        # Handle image_url which can be a string or dict with size variants
        image_url = data.get("imageSrc")
        if isinstance(image_url, dict):
            image_url = image_url.get("og") or image_url.get("lg") or image_url.get("sm")
        if not image_url:
            banner = data.get("bannerScreenshot")
            if isinstance(banner, dict):
                image_url = banner.get("fullRes") or banner.get("og")

        # Convert relative path to full URL
        if image_url and not image_url.startswith("http"):
            image_url = f"{cls.IMAGE_CDN_URL}/{image_url}"

        return {
            "opencritic_id": data.get("id"),
            "title": data.get("name", "Unknown"),
            "description": data.get("description"),
            "release_date": release_date,
            "top_critic_score": Decimal(str(round(data["topCriticScore"], 2)))
                if data.get("topCriticScore") else None,
            "percent_recommended": Decimal(str(round(data["percentRecommended"], 2)))
                if data.get("percentRecommended") else None,
            "tier": data.get("tier"),
            "image_url": image_url,
        }

    @staticmethod
    def transform_review(data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenCritic review data to our model format."""
        # Parse publication date
        published_at = None
        pub_date_str = data.get("publishedDate")
        if pub_date_str:
            try:
                published_at = datetime.fromisoformat(
                    pub_date_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Normalize score
        score_raw = str(data.get("score", ""))
        score_scale = None
        normalized_score = None
        detected_scale = None

        # OpenCritic provides scoreFormat which indicates the scale
        score_format = data.get("scoreFormat", {})

        # Check if this is a recommendation-based format (not a real numeric score)
        # These outlets don't give numeric scores, so we shouldn't normalize them
        is_recommendation_format = False
        if score_format:
            format_type = score_format.get("type", "").lower()
            format_name = score_format.get("name", "").lower()

            # Detect recommendation-based formats
            recommendation_indicators = [
                "recommend", "binary", "thumbs", "buy", "skip",
                "essential", "award", "badge", "yes/no",
            ]
            if any(ind in format_type or ind in format_name for ind in recommendation_indicators):
                is_recommendation_format = True

            # Also check if base is 0 or 1 (binary) or if there's no real scale
            base = score_format.get("base")
            if base in (0, 1, "0", "1", None):
                is_recommendation_format = True
            elif base:
                score_scale = str(base)

        # Only normalize if this is NOT a recommendation-based format
        if not is_recommendation_format and score_raw:
            normalized_score, detected_scale = ScoreNormalizer.normalize(
                score_raw, score_scale
            )

        return {
            "opencritic_review_id": str(data.get("_id") or data.get("id")),
            "opencritic_critic_id": data.get("Authors", [{}])[0].get("id")
                if data.get("Authors") else None,
            "opencritic_outlet_id": data.get("Outlet", {}).get("id")
                if data.get("Outlet") else None,
            "opencritic_game_id": data.get("game", {}).get("id")
                if isinstance(data.get("game"), dict) else data.get("game"),
            "score_raw": score_raw,
            "score_scale": detected_scale or score_scale,
            "score_normalized": normalized_score,
            "review_url": data.get("externalUrl"),
            "snippet": data.get("snippet"),
            "published_at": published_at,
        }

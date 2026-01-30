"""
Steam API service.

Fetches user review data from Steam Web API.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

import httpx
from aiolimiter import AsyncLimiter

from app.services.score_normalizer import ScoreNormalizer

# Rate limit: 10 requests per second (Steam is fairly generous)
rate_limiter = AsyncLimiter(10, 1)


class SteamService:
    """Service for interacting with the Steam Web API."""

    STORE_API_URL = "https://store.steampowered.com/api"
    COMMUNITY_API_URL = "https://api.steampowered.com"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Steam service.

        Args:
            api_key: Optional Steam Web API key for extended access
        """
        self.api_key = api_key

    async def _request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Make a rate-limited request to Steam API."""
        async with rate_limiter:
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as e:
                    print(f"HTTP error {e.response.status_code}: {e.response.text}")
                    return None
                except httpx.RequestError as e:
                    print(f"Request error: {e}")
                    return None

    async def get_app_details(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        Get game details from Steam Store API.

        Args:
            app_id: Steam application ID

        Returns:
            Game details including name, description, release date, etc.
        """
        data = await self._request(
            f"{self.STORE_API_URL}/appdetails",
            params={"appids": str(app_id)},
        )

        if not data:
            return None

        app_data = data.get(str(app_id), {})
        if not app_data.get("success"):
            return None

        return app_data.get("data")

    async def get_review_summary(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        Get review summary for a game.

        This endpoint provides aggregated review data without requiring an API key.

        Args:
            app_id: Steam application ID

        Returns:
            Review summary including positive/negative counts and review score
        """
        data = await self._request(
            f"{self.STORE_API_URL}/appreviews/{app_id}",
            params={
                "json": "1",
                "language": "all",
                "purchase_type": "all",
                "num_per_page": "0",  # We only need the summary
            },
        )

        if not data or not data.get("success"):
            return None

        return data.get("query_summary")

    async def get_user_score(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        Get normalized user score for a game.

        Args:
            app_id: Steam application ID

        Returns:
            Dictionary with score data ready for database storage
        """
        summary = await self.get_review_summary(app_id)
        if not summary:
            return None

        total_reviews = summary.get("total_reviews", 0)
        if total_reviews == 0:
            return None

        positive = summary.get("total_positive", 0)
        negative = summary.get("total_negative", 0)

        # Calculate percentage score
        score = ScoreNormalizer.normalize_steam_score(positive, negative)
        if score is None:
            return None

        # Get review description
        review_desc = summary.get("review_score_desc", "")
        if not review_desc:
            review_desc = ScoreNormalizer.get_steam_review_description(score)

        return {
            "source": "STEAM",
            "score": score,
            "score_raw": f"{positive}/{total_reviews}",
            "sample_size": total_reviews,
            "positive_count": positive,
            "negative_count": negative,
            "review_score_desc": review_desc,
            "scraped_at": datetime.utcnow(),
        }

    async def search_games(self, query: str) -> list[Dict[str, Any]]:
        """
        Search for games on Steam by name.

        Note: Steam doesn't have a public search API, so this uses
        the store search endpoint which may have limitations.

        Args:
            query: Search query string

        Returns:
            List of matching games with basic info
        """
        # Steam store search (unofficial, may break)
        data = await self._request(
            "https://store.steampowered.com/api/storesearch",
            params={
                "term": query,
                "l": "english",
                "cc": "US",
            },
        )

        if not data:
            return []

        items = data.get("items", [])
        return [
            {
                "steam_app_id": item.get("id"),
                "name": item.get("name"),
                "tiny_image": item.get("tiny_image"),
            }
            for item in items
        ]

    async def get_app_list(self) -> list[Dict[str, Any]]:
        """
        Get complete list of all Steam apps.

        This is a large list (~150k apps) and should be cached.

        Returns:
            List of all apps with app_id and name
        """
        data = await self._request(
            f"{self.COMMUNITY_API_URL}/ISteamApps/GetAppList/v2/",
        )

        if not data:
            return []

        return data.get("applist", {}).get("apps", [])

    @staticmethod
    def transform_app_details(data: Dict[str, Any], app_id: int) -> Dict[str, Any]:
        """Transform Steam app details to our game model format."""
        release_date = None
        release_info = data.get("release_date", {})
        if release_info and not release_info.get("coming_soon"):
            date_str = release_info.get("date")
            if date_str:
                # Steam dates are in various formats, try common ones
                for fmt in ["%b %d, %Y", "%d %b, %Y", "%Y"]:
                    try:
                        release_date = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue

        return {
            "steam_app_id": app_id,
            "title": data.get("name"),
            "description": data.get("short_description"),
            "release_date": release_date,
            "image_url": data.get("header_image"),
        }

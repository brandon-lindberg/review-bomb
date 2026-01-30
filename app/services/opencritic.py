"""
OpenCritic API service.

Fetches critics, outlets, games, and reviews from OpenCritic via RapidAPI.
"""

import asyncio
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from decimal import Decimal

import httpx
from aiolimiter import AsyncLimiter

from app.config import get_settings
from app.services.score_normalizer import ScoreNormalizer

settings = get_settings()

# Rate limit: 10 requests per second (adjust based on your RapidAPI plan)
rate_limiter = AsyncLimiter(10, 1)


class OpenCriticService:
    """Service for interacting with the OpenCritic API."""

    BASE_URL = "https://opencritic-api.p.rapidapi.com"
    DATA_CUTOFF = date(2015, 1, 1)

    def __init__(self):
        self.headers = {
            "X-RapidAPI-Key": settings.rapidapi_key or "",
            "X-RapidAPI-Host": settings.opencritic_api_host,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Make a rate-limited request to the OpenCritic API."""
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
                    return response.json()
                except httpx.HTTPStatusError as e:
                    print(f"HTTP error {e.response.status_code}: {e.response.text}")
                    return None
                except httpx.RequestError as e:
                    print(f"Request error: {e}")
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
            await asyncio.sleep(0.1)  # Be nice to the API

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
            await asyncio.sleep(0.1)

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

    async def get_games_since_date(
        self,
        since_date: date,
        batch_size: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all games released since a specific date.

        Filters out games before DATA_CUTOFF (2015-01-01).
        """
        all_games = []
        skip = 0

        while True:
            games = await self.get_games(skip=skip, limit=batch_size, sort="date")
            if not games:
                break

            for game in games:
                # Parse release date
                release_date_str = game.get("firstReleaseDate")
                if release_date_str:
                    try:
                        release_date = datetime.fromisoformat(
                            release_date_str.replace("Z", "+00:00")
                        ).date()

                        # Skip games before cutoff
                        if release_date < self.DATA_CUTOFF:
                            continue

                        # Stop if we've gone past our since_date
                        if release_date < since_date:
                            return all_games

                        all_games.append(game)
                    except (ValueError, TypeError):
                        continue
                else:
                    # Include games without release date if they have reviews
                    if game.get("numReviews", 0) > 0:
                        all_games.append(game)

            if len(games) < batch_size:
                break

            skip += batch_size
            await asyncio.sleep(0.1)

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

    @staticmethod
    def transform_critic(data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenCritic critic data to our model format."""
        return {
            "opencritic_id": data.get("id"),
            "name": data.get("name", "Unknown"),
            "image_url": data.get("imageSrc"),
            "bio": None,  # OpenCritic doesn't provide bios
        }

    @staticmethod
    def transform_outlet(data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform OpenCritic outlet data to our model format."""
        return {
            "opencritic_id": data.get("id"),
            "name": data.get("name", "Unknown"),
            "website_url": data.get("externalUrl"),
            "logo_url": data.get("imageSrc"),
        }

    @staticmethod
    def transform_game(data: Dict[str, Any]) -> Dict[str, Any]:
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
            "image_url": data.get("imageSrc") or data.get("bannerScreenshot", {}).get("fullRes"),
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

        # OpenCritic provides scoreFormat which indicates the scale
        score_format = data.get("scoreFormat", {})
        if score_format:
            # Try to determine scale from format
            base = score_format.get("base")
            if base:
                score_scale = str(base)

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

"""
Steam API service.

Fetches user review data from Steam Web API.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from decimal import Decimal
from html import unescape

import httpx
from aiolimiter import AsyncLimiter

from app.services.score_normalizer import ScoreNormalizer

# General Steam traffic can stay moderately paced.
rate_limiter = AsyncLimiter(5, 1)

# Store appdetails is more sensitive and will 429 during long crawls unless we
# intentionally slow it down. This paces those requests to roughly one every
# 2.5 seconds in sequential flows when combined with the small anti-bot delay.
app_details_rate_limiter = AsyncLimiter(1, 2)

# Headers that mimic a real browser - Steam blocks requests without proper headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

# Cookies for bypassing Steam age verification and other checks
DEFAULT_COOKIES = {
    "birthtime": "0",  # Age verification bypass (epoch = over 18)
    "mature_content": "1",  # Allow mature content
    "lastagecheckage": "1-0-1990",  # Age check bypass
    "wants_mature_content": "1",
}


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
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self):
        """Close underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and reuse a single AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers=DEFAULT_HEADERS,
                cookies=DEFAULT_COOKIES,
                follow_redirects=True,
            )
        return self._client

    async def _request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        log_http_error: bool = True,
        limiter: AsyncLimiter = rate_limiter,
        delay_seconds: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        """Make a rate-limited request to Steam API with retry logic."""
        async with limiter:
            # Small delay to avoid triggering anti-bot measures
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

            for attempt in range(max_retries):
                try:
                    client = await self._get_client()
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    response_text = (e.response.text or "").strip()[:200]
                    if not response_text:
                        response_text = "<empty>"
                    server = e.response.headers.get("server")
                    cf_ray = e.response.headers.get("cf-ray")

                    if e.response.status_code == 403:
                        # Access denied - try with longer delay
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                            print(f"  Access denied, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            await asyncio.sleep(wait_time)
                            continue
                    elif e.response.status_code == 429:
                        # Rate limited - wait longer
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                            print(f"  Rate limited, waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                    if log_http_error:
                        print(
                            f"HTTP error {status_code} for {url} params={params} "
                            f"(server={server}, cf-ray={cf_ray}): {response_text}"
                        )
                    return None
                except httpx.RequestError as e:
                    if "closed" in str(e).lower():
                        await self.aclose()
                    if attempt < max_retries - 1:
                        print(f"  Request error, retrying...")
                        await asyncio.sleep(1)
                        continue
                    print(f"Request error: {e}")
                    return None
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
            max_retries=4,
            limiter=app_details_rate_limiter,
            delay_seconds=0.5,
        )

        if not data:
            return None

        app_data = data.get(str(app_id), {})
        if not app_data.get("success"):
            return None

        return app_data.get("data")

    async def get_app_details_batch(self, app_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Get game details for multiple Steam app IDs in a single request.

        Steam's appdetails endpoint accepts a comma-separated app ID list and
        returns a keyed object for each requested app.

        Args:
            app_ids: Steam application IDs

        Returns:
            Mapping of app_id to Steam app details for successful responses
        """
        if not app_ids:
            return {}

        unique_app_ids: List[int] = []
        seen: set[int] = set()
        for app_id in app_ids:
            if app_id in seen:
                continue
            unique_app_ids.append(app_id)
            seen.add(app_id)

        data = await self._request(
            f"{self.STORE_API_URL}/appdetails",
            params={"appids": ",".join(str(app_id) for app_id in unique_app_ids)},
            max_retries=4,
            limiter=app_details_rate_limiter,
            delay_seconds=0.5,
        )

        if not data:
            return {}

        details: Dict[int, Dict[str, Any]] = {}
        for app_id in unique_app_ids:
            app_data = data.get(str(app_id), {})
            if not app_data.get("success"):
                continue
            app_details = app_data.get("data")
            if app_details:
                details[app_id] = app_details

        return details

    async def get_review_summary(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        Get review summary for a game.

        This endpoint provides aggregated review data without requiring an API key.

        Args:
            app_id: Steam application ID

        Returns:
            Review summary including positive/negative counts and review score
        """
        # Note: Steam appreviews endpoint is NOT under /api path.
        # Try multiple parameter shapes because Steam occasionally changes behavior
        # for summary-only queries.
        request_variants = [
            {
                "json": "1",
                "language": "all",
                "purchase_type": "all",
                "num_per_page": "0",  # Historical summary-only shape
            },
            {
                "json": "1",
                "filter": "summary",
                "language": "all",
                "purchase_type": "all",
                "num_per_page": "1",
            },
            {
                "json": "1",
                "language": "all",
                "purchase_type": "all",
                "num_per_page": "1",
            },
        ]

        for params in request_variants:
            data = await self._request(
                f"https://store.steampowered.com/appreviews/{app_id}",
                params=params,
                log_http_error=False,
            )
            if not data:
                continue
            if data.get("success") and data.get("query_summary") is not None:
                return data.get("query_summary")

        # Fallback when appreviews endpoint is failing (observed intermittent 500s).
        print(f"  appreviews unavailable for app_id={app_id}, trying app page fallback")
        html_summary = await self._get_review_summary_from_store_page(app_id)
        if html_summary:
            print(f"  Fallback: parsed review summary from Steam app page for app_id={app_id}")
            return html_summary

        return None

    @staticmethod
    def _parse_review_summary_from_html(html: str) -> Optional[Dict[str, Any]]:
        """Extract review summary from Steam store page HTML."""
        text = unescape(html or "")
        patterns = [
            r"(\d{1,3})% of the ([\d,]+) user reviews for this game are positive",
            r"(\d{1,3})% of the ([\d,]+) user reviews in your language are positive",
            r"(\d{1,3})% of the ([\d,]+) user reviews [^\"<]* are positive",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue

            positive_pct = int(match.group(1))
            total_reviews = int(match.group(2).replace(",", ""))
            if total_reviews <= 0:
                continue

            total_positive = int(round((positive_pct / 100) * total_reviews))
            total_negative = max(total_reviews - total_positive, 0)
            review_desc = ScoreNormalizer.get_steam_review_description(
                Decimal(str(positive_pct))
            )

            return {
                "total_reviews": total_reviews,
                "total_positive": total_positive,
                "total_negative": total_negative,
                "review_score_desc": review_desc,
            }

        return None

    async def _get_review_summary_from_store_page(self, app_id: int) -> Optional[Dict[str, Any]]:
        """Fallback summary scraping from Steam app page when appreviews API fails."""
        async with rate_limiter:
            await asyncio.sleep(0.5)
            try:
                client = await self._get_client()
                response = await client.get(
                    f"https://store.steampowered.com/app/{app_id}/",
                    params={"l": "english", "cc": "us"},
                )
                response.raise_for_status()
                return self._parse_review_summary_from_html(response.text)
            except Exception as e:
                print(f"  Fallback app page fetch failed for app_id={app_id}: {e}")
                return None

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
            "scraped_at": datetime.now(timezone.utc),
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

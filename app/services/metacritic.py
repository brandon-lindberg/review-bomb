"""
Metacritic scraping service.

Scrapes user scores from Metacritic using Playwright.
Note: Use responsibly and respect robots.txt and rate limits.
"""

import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from app.services.score_normalizer import ScoreNormalizer


class MetacriticService:
    """Service for scraping user scores from Metacritic."""

    BASE_URL = "https://www.metacritic.com"

    def __init__(self, headless: bool = True):
        """
        Initialize Metacritic service.

        Args:
            headless: Whether to run browser in headless mode
        """
        self.headless = headless
        self._browser = None
        self._playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _get_page(self):
        """Get a new browser page with common settings."""
        if not self._browser:
            raise RuntimeError("Browser not initialized. Use 'async with' context manager.")

        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        return await context.new_page()

    @staticmethod
    def build_game_url(slug: str, platform: str = "pc") -> str:
        """
        Build Metacritic URL for a game.

        Args:
            slug: Game slug (e.g., "the-witcher-3-wild-hunt")
            platform: Platform slug (e.g., "pc", "playstation-5", "xbox-series-x")

        Returns:
            Full Metacritic URL
        """
        return f"https://www.metacritic.com/game/{slug}"

    @staticmethod
    def slugify(title: str) -> str:
        """
        Convert game title to Metacritic slug format.

        Args:
            title: Game title (e.g., "The Witcher 3: Wild Hunt")

        Returns:
            Slug format (e.g., "the-witcher-3-wild-hunt")
        """
        # Lowercase
        slug = title.lower()

        # Replace special characters
        slug = re.sub(r"[':!?.,]", "", slug)

        # Replace spaces and other separators with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)

        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)

        # Remove leading/trailing hyphens
        slug = slug.strip("-")

        return slug

    async def get_user_score(
        self,
        slug: str,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """
        Scrape user score for a game from Metacritic.

        Args:
            slug: Game slug or full URL
            max_retries: Number of retry attempts on failure

        Returns:
            Dictionary with score data ready for database storage
        """
        # Build URL if only slug provided
        if not slug.startswith("http"):
            url = self.build_game_url(slug)
        else:
            url = slug

        for attempt in range(max_retries):
            try:
                page = await self._get_page()

                try:
                    # Navigate to game page
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                    # Wait for user score to load
                    await page.wait_for_selector(
                        '[data-testid="user-score-value"], .c-siteReviewScore_user',
                        timeout=10000,
                    )

                    # Try multiple selectors for user score (Metacritic changes their HTML)
                    score_text = None
                    sample_size = None

                    # Try new layout
                    score_el = await page.query_selector('[data-testid="user-score-value"]')
                    if score_el:
                        score_text = await score_el.text_content()

                    # Try older layout
                    if not score_text:
                        score_el = await page.query_selector('.c-siteReviewScore_user')
                        if score_el:
                            score_text = await score_el.text_content()

                    # Try generic score selector
                    if not score_text:
                        score_el = await page.query_selector('.metascore_w.user')
                        if score_el:
                            score_text = await score_el.text_content()

                    if not score_text:
                        return None

                    # Parse score
                    score_text = score_text.strip()
                    if score_text.lower() in ("tbd", "n/a", ""):
                        return None

                    try:
                        raw_score = float(score_text)
                    except ValueError:
                        return None

                    # Try to get sample size (number of user ratings)
                    sample_el = await page.query_selector(
                        '[data-testid="user-score-count"], .c-siteReviewScore_user + span, .count a'
                    )
                    if sample_el:
                        sample_text = await sample_el.text_content()
                        # Extract number from text like "Based on 1,234 ratings"
                        numbers = re.findall(r"[\d,]+", sample_text or "")
                        if numbers:
                            sample_size = int(numbers[0].replace(",", ""))

                    # Normalize score (Metacritic user scores are 0-10)
                    normalized_score = ScoreNormalizer.normalize_metacritic_user_score(raw_score)

                    return {
                        "source": "METACRITIC",
                        "score": normalized_score,
                        "score_raw": str(raw_score),
                        "sample_size": sample_size,
                        "positive_count": None,
                        "negative_count": None,
                        "review_score_desc": None,
                        "scraped_at": datetime.utcnow(),
                    }

                finally:
                    await page.close()

            except PlaywrightTimeout:
                print(f"Timeout scraping {url}, attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue

            except Exception as e:
                print(f"Error scraping {url}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue

        return None

    async def search_game(self, title: str) -> Optional[str]:
        """
        Search for a game on Metacritic and return its slug.

        Args:
            title: Game title to search for

        Returns:
            Game slug if found, None otherwise
        """
        search_url = f"{self.BASE_URL}/search/{self.slugify(title)}/?category=13"  # 13 = games

        try:
            page = await self._get_page()

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

                # Wait for search results
                await page.wait_for_selector('.c-pageSiteSearch-results', timeout=10000)

                # Get first result link
                first_result = await page.query_selector(
                    '.c-pageSiteSearch-results a[href*="/game/"]'
                )

                if first_result:
                    href = await first_result.get_attribute("href")
                    if href:
                        # Extract slug from URL like /game/the-witcher-3-wild-hunt
                        match = re.search(r"/game/([^/]+)", href)
                        if match:
                            return match.group(1)

                return None

            finally:
                await page.close()

        except Exception as e:
            print(f"Error searching for {title}: {e}")
            return None


# Convenience function for one-off scraping
async def scrape_metacritic_score(slug: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to scrape a single game's user score.

    Args:
        slug: Game slug (e.g., "the-witcher-3-wild-hunt")

    Returns:
        Score data or None
    """
    async with MetacriticService() as service:
        return await service.get_user_score(slug)

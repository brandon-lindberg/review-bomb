"""
Metacritic scraping service.

Scrapes user scores from Metacritic using Playwright.
Note: Use responsibly and respect robots.txt and rate limits.
"""

import asyncio
import re
from datetime import datetime, timezone
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
        await self._cleanup_browser()
        if self._playwright:
            await self._playwright.stop()

    async def _cleanup_browser(self):
        """Safely close browser if it exists."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

    async def _restart_playwright(self):
        """Restart the entire Playwright instance when connection is corrupted."""
        print("Restarting Playwright...")
        await self._cleanup_browser()
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        # Small delay before restarting
        await asyncio.sleep(2)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

    async def _ensure_browser(self):
        """Ensure browser is running, restart if needed."""
        try:
            if self._browser is None or not self._browser.is_connected():
                await self._cleanup_browser()
                self._browser = await self._playwright.chromium.launch(headless=self.headless)
        except Exception as e:
            # If we can't create a browser, restart Playwright entirely
            error_msg = str(e).lower()
            if "pipe closed" in error_msg or "connection closed" in error_msg:
                await self._restart_playwright()
            else:
                raise

    async def _get_page(self):
        """Get a new browser page with common settings."""
        await self._ensure_browser()

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

    async def get_scores(
        self,
        slug: str,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """
        Scrape both user score and metascore (critic aggregate) from Metacritic.

        Args:
            slug: Game slug or full URL
            max_retries: Number of retry attempts on failure

        Returns:
            Dictionary with both user score and metascore data
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

                    # Wait for page to fully render dynamic content
                    await asyncio.sleep(3)

                    result = {
                        "user_score": None,
                        "user_score_raw": None,
                        "user_sample_size": None,
                        "metascore": None,
                        "critic_count": None,
                        "scraped_at": datetime.now(timezone.utc),
                    }

                    # === METASCORE (Critic aggregate) ===
                    # Use targeted JavaScript to find the metascore
                    # CRITICAL: Must find the AGGREGATE metascore, not individual critic scores
                    # The aggregate section has "Based on X Critic Reviews" text
                    # Individual reviews are in "Latest Critic Reviews" section - avoid those!
                    metascore_js = await page.evaluate('''() => {
                        // Helper: Check if element is inside "Latest Critic Reviews" section
                        function isInLatestReviewsSection(el) {
                            let parent = el;
                            while (parent) {
                                const text = parent.textContent || '';
                                // If we find "Latest Critic Reviews" before finding "Based on X Critic",
                                // this element is in the wrong section
                                if (text.includes('Latest Critic Reviews')) {
                                    // But check if this same container also has the aggregate
                                    if (!text.match(/Based on \\d+ Critic Review/i)) {
                                        return true;
                                    }
                                }
                                parent = parent.parentElement;
                            }
                            return false;
                        }

                        // Method 1 (PRIMARY): Find "Based on X Critic Reviews" text and get score from that section
                        // This is the most reliable way to identify the aggregate section
                        const allSpans = document.querySelectorAll('span, div, p');
                        for (const span of allSpans) {
                            const spanText = span.textContent.trim();
                            // Match "Based on X Critic Reviews" but NOT inside "Latest Critic Reviews"
                            if (/^Based on \\d+ Critic Review/i.test(spanText)) {
                                // Found the aggregate label! Now look for the score nearby
                                // Go up to parent containers and find the score
                                let parent = span.parentElement;
                                for (let i = 0; i < 5 && parent; i++) {
                                    // Don't go too far up - stay in the aggregate section
                                    if (parent.textContent.includes('Latest Critic Reviews')) break;

                                    const children = parent.querySelectorAll('span, div');
                                    for (const child of children) {
                                        const childText = child.textContent.trim();
                                        // Match 1-3 digit scores
                                        if (/^\\d{1,3}$/.test(childText)) {
                                            const val = parseInt(childText);
                                            if (val >= 0 && val <= 100) {
                                                return childText;
                                            }
                                        }
                                    }
                                    parent = parent.parentElement;
                                }
                            }
                        }

                        // Method 2: Find METASCORE label and look for nearby score
                        for (const elem of allSpans) {
                            const text = elem.textContent.trim();
                            // Check for spaced "M E T A S C O R E" or regular "Metascore"
                            if (/^M\\s*E\\s*T\\s*A\\s*S\\s*C\\s*O\\s*R\\s*E$/i.test(text) ||
                                text === 'METASCORE' || text === 'Metascore') {
                                // Found label - look for score in parent containers
                                let parent = elem.parentElement;
                                for (let i = 0; i < 4 && parent; i++) {
                                    // Don't look in Latest Critic Reviews section
                                    if (parent.textContent.includes('Latest Critic Reviews')) break;

                                    const scoreChildren = parent.querySelectorAll('span, div');
                                    for (const child of scoreChildren) {
                                        const childText = child.textContent.trim();
                                        if (/^\\d{1,3}$/.test(childText)) {
                                            const val = parseInt(childText);
                                            if (val >= 0 && val <= 100) return childText;
                                        }
                                    }
                                    parent = parent.parentElement;
                                }
                            }
                        }

                        // Method 3 (FALLBACK): data-testid but verify not in Latest Reviews
                        let el = document.querySelector('[data-testid="critic-score-value"]');
                        if (el && !isInLatestReviewsSection(el)) {
                            const text = el.textContent.trim();
                            if (text && !['tbd', 'n/a', ''].includes(text.toLowerCase())) {
                                const match = text.match(/^(\\d{1,3})$/);
                                if (match) {
                                    const val = parseInt(match[1]);
                                    if (val >= 0 && val <= 100) return match[1];
                                }
                            }
                        }

                        return null;
                    }''')

                    if metascore_js:
                        try:
                            result["metascore"] = Decimal(str(int(metascore_js)))
                        except (ValueError, TypeError):
                            pass

                    # Try to get critic review count
                    critic_count_selectors = [
                        '[data-testid="critic-score-count"]',
                        '.c-siteReviewScore:not(.c-siteReviewScore_user) + span',
                    ]
                    for selector in critic_count_selectors:
                        try:
                            count_el = await page.query_selector(selector)
                            if count_el:
                                count_text = await count_el.text_content()
                                numbers = re.findall(r"[\d,]+", count_text or "")
                                if numbers:
                                    result["critic_count"] = int(numbers[0].replace(",", ""))
                                    break
                        except Exception:
                            continue

                    # === USER SCORE ===
                    # Use targeted JavaScript to find the user score
                    # Only look in specific locations to avoid picking up wrong numbers
                    user_score_js = await page.evaluate('''() => {
                        // Method 1: data-testid (most reliable)
                        let el = document.querySelector('[data-testid="user-score-value"]');
                        if (el) {
                            const text = el.textContent.trim();
                            if (text && !['tbd', 'n/a', ''].includes(text.toLowerCase())) {
                                // Must be a decimal like "8.1" - not a whole number
                                const match = text.match(/^(\\d\\.\\d)$/);
                                if (match) return match[1];
                            }
                        }

                        // Method 2: Look for the specific user score section
                        // Find elements that contain "User Score" or "User Ratings" text nearby
                        const sections = document.querySelectorAll('section, div');
                        for (const section of sections) {
                            const text = section.textContent;
                            // Must contain "User" and "Rating" to be the user score section
                            if (text.includes('User') && (text.includes('Rating') || text.includes('Score'))) {
                                // Look for a child element with just a decimal score
                                const children = section.querySelectorAll('span, div');
                                for (const child of children) {
                                    const childText = child.textContent.trim();
                                    // Only match decimal scores like "5.7", "8.1" - exactly X.X format
                                    if (/^\\d\\.\\d$/.test(childText)) {
                                        const val = parseFloat(childText);
                                        if (val > 0 && val <= 10) return childText;
                                    }
                                }
                            }
                        }

                        // Method 3: Find score circle/badge near "User" text
                        // Look for score elements that are siblings or near "user" labels
                        const scoreElements = document.querySelectorAll('[class*="Score"]');
                        for (const scoreEl of scoreElements) {
                            // Check if this is in a user context (class contains "user" case-insensitive)
                            const className = scoreEl.className.toLowerCase();
                            if (className.includes('user')) {
                                const text = scoreEl.textContent.trim();
                                // Extract decimal score
                                const match = text.match(/(\\d\\.\\d)/);
                                if (match) {
                                    const val = parseFloat(match[1]);
                                    if (val > 0 && val <= 10) return match[1];
                                }
                            }
                        }

                        return null;
                    }''')

                    if user_score_js:
                        try:
                            raw_score = float(user_score_js)
                            if 0 < raw_score <= 10:
                                result["user_score_raw"] = str(raw_score)
                                result["user_score"] = ScoreNormalizer.normalize_metacritic_user_score(raw_score)
                        except ValueError:
                            pass

                    # Try to get user sample size using JavaScript
                    user_sample_js = await page.evaluate('''() => {
                        // Method 1: data-testid
                        let el = document.querySelector('[data-testid="user-score-count"]');
                        if (el) {
                            const text = el.textContent.trim();
                            const match = text.match(/([\\d,]+)/);
                            if (match) return match[1].replace(/,/g, '');
                        }

                        // Method 2: Search full page text for "Based on X User Ratings"
                        // This is the most reliable - works regardless of element nesting
                        const bodyText = document.body.innerText || document.body.textContent || '';
                        const bodyMatch = bodyText.match(/Based on ([\\d,]+) User/i);
                        if (bodyMatch) {
                            return bodyMatch[1].replace(/,/g, '');
                        }

                        // Method 3: Find individual elements with the pattern
                        const allElements = document.querySelectorAll('span, div, p, a');
                        for (const elem of allElements) {
                            const text = elem.textContent.trim();
                            const match = text.match(/Based on ([\\d,]+) User/i) ||
                                          text.match(/^([\\d,]+) User Rating/i);
                            if (match) {
                                return match[1].replace(/,/g, '');
                            }
                        }

                        return null;
                    }''')

                    if user_sample_js:
                        try:
                            result["user_sample_size"] = int(user_sample_js)
                        except (ValueError, TypeError):
                            pass

                    # Return result if we got at least one score
                    if result["user_score"] is not None or result["metascore"] is not None:
                        return result

                    return None

                finally:
                    await page.close()

            except PlaywrightTimeout:
                print(f"Timeout scraping {url}, attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue

            except Exception as e:
                error_msg = str(e).lower()
                # Check if browser/Playwright connection crashed and needs restart
                if any(err in error_msg for err in [
                    "browser has been closed",
                    "target closed",
                    "pipe closed",
                    "connection closed",
                ]):
                    print(f"Browser/Playwright crashed, restarting... ({url})")
                    try:
                        await self._restart_playwright()
                    except Exception as restart_err:
                        print(f"Failed to restart Playwright: {restart_err}")
                    await asyncio.sleep(2)
                    if attempt < max_retries - 1:
                        continue
                else:
                    print(f"Error scraping {url}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue

        return None

    async def get_user_score(
        self,
        slug: str,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """
        Scrape user score for a game from Metacritic.

        Legacy method - wraps get_scores() for backwards compatibility.

        Args:
            slug: Game slug or full URL
            max_retries: Number of retry attempts on failure

        Returns:
            Dictionary with score data ready for database storage
        """
        scores = await self.get_scores(slug, max_retries)
        if not scores or scores.get("user_score") is None:
            return None

        return {
            "source": "METACRITIC",
            "score": scores["user_score"],
            "score_raw": scores["user_score_raw"],
            "sample_size": scores["user_sample_size"],
            "positive_count": None,
            "negative_count": None,
            "review_score_desc": None,
            "scraped_at": scores["scraped_at"],
        }

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

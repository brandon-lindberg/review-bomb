"""
Game matching service.

Matches games across OpenCritic, Steam, and Metacritic using fuzzy title matching
and release date proximity.
"""

import re
from datetime import date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from difflib import SequenceMatcher

from app.services.steam import SteamService
from app.services.metacritic import MetacriticService


class GameMatcher:
    """Service for matching games across different platforms."""

    # Manual overrides for games that are hard to match automatically
    # Format: {opencritic_id: {"steam_app_id": int, "metacritic_slug": str}}
    MANUAL_OVERRIDES: Dict[int, Dict[str, Any]] = {
        # Overwatch (canonical entry after OW2 merge) — OC 1673
        # Steam app 2357570 is the live game, Metacritic "overwatch" is the current page
        1673: {"steam_app_id": 2357570, "metacritic_slug": "overwatch"},
        # Ghost of Tsushima Director's Cut — OC lists PS release date (2021),
        # but Steam release is in 2024; force known Steam app mapping.
        11839: {"steam_app_id": 2215430},
    }

    # Common title transformations to improve matching
    TITLE_REPLACEMENTS = [
        (r"\s*:\s*", " "),           # "Game: Subtitle" -> "Game Subtitle"
        (r"\s*-\s*", " "),           # "Game - Subtitle" -> "Game Subtitle"
        (r"\s+edition$", "", True),  # Remove "Edition" suffix
        (r"\s+remastered$", "", True),
        (r"\s+definitive$", "", True),
        (r"\s+complete$", "", True),
        (r"\s+goty$", "", True),
        (r"\s+game of the year$", "", True),
        (r"[™®©]", ""),             # Remove trademark symbols
        (r"\s+", " "),              # Normalize whitespace
    ]

    # Common suffix patterns in store/listing names that can hide the canonical title.
    SEARCH_SUFFIX_PATTERNS = [
        r"(?i)\s*[:\-]?\s*chapters?\s+\d+(?:\s*(?:&|and|,)\s*\d+)*.*$",
        r"(?i)\s*[:\-]?\s*chapter\s+\d+.*$",
        r"(?i)\s*[:\-]?\s*episode\s+\d+.*$",
    ]

    @classmethod
    def build_search_queries(cls, title: str) -> List[str]:
        """
        Build fallback Steam search queries for problematic titles.

        Steam search can return no results for some punctuation/symbol combinations
        (for example "Delta" vs "Δ" or titles with subtitle suffixes).
        """
        candidates: List[str] = []

        def add(value: Optional[str]) -> None:
            if not value:
                return
            v = value.strip()
            if v and v not in candidates:
                candidates.append(v)

        add(title)

        # Symbol normalization fallbacks.
        if re.search(r"\bdelta\b", title, flags=re.IGNORECASE):
            add(re.sub(r"\bdelta\b", "Δ", title, flags=re.IGNORECASE))
        if "Δ" in title:
            add(title.replace("Δ", "Delta"))

        # Subtitle splits.
        for sep in [":", " - ", " – ", " — "]:
            if sep in title:
                left, right = title.split(sep, 1)
                add(left)
                add(right)

        # Strip common chapter/episode suffixes.
        stripped = title
        for pattern in cls.SEARCH_SUFFIX_PATTERNS:
            stripped = re.sub(pattern, "", stripped).strip()
        add(stripped)

        return candidates

    @classmethod
    def build_similarity_titles(cls, title: str) -> List[str]:
        """
        Build title variants for similarity scoring.

        Unlike search queries, this intentionally avoids left/right subtitle
        splits. Otherwise a title like "Game: Subtitle" can incorrectly score
        as a perfect match against unrelated "Game" entries.
        """
        candidates: List[str] = []

        def add(value: Optional[str]) -> None:
            if not value:
                return
            v = value.strip()
            if v and v not in candidates:
                candidates.append(v)

        add(title)

        # Symbol normalization fallbacks.
        if re.search(r"\bdelta\b", title, flags=re.IGNORECASE):
            add(re.sub(r"\bdelta\b", "Δ", title, flags=re.IGNORECASE))
        if "Δ" in title:
            add(title.replace("Δ", "Delta"))

        # Strip common chapter/episode suffixes.
        stripped = title
        for pattern in cls.SEARCH_SUFFIX_PATTERNS:
            stripped = re.sub(pattern, "", stripped).strip()
        add(stripped)

        return candidates

    def __init__(
        self,
        steam_service: Optional[SteamService] = None,
        metacritic_service: Optional[MetacriticService] = None,
    ):
        """
        Initialize game matcher.

        Args:
            steam_service: Steam API service instance
            metacritic_service: Metacritic scraping service instance
        """
        self.steam_service = steam_service or SteamService()
        self.metacritic_service = metacritic_service

    @classmethod
    def normalize_title(cls, title: str) -> str:
        """
        Normalize a game title for comparison.

        Args:
            title: Original game title

        Returns:
            Normalized title for matching
        """
        normalized = title.lower().strip()

        for pattern, replacement, *flags in cls.TITLE_REPLACEMENTS:
            case_insensitive = flags[0] if flags else False
            if case_insensitive:
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            else:
                normalized = re.sub(pattern, replacement, normalized)

        return normalized.strip()

    @classmethod
    def calculate_similarity(cls, title1: str, title2: str) -> float:
        """
        Calculate similarity between two titles.

        Args:
            title1: First title
            title2: Second title

        Returns:
            Similarity score between 0 and 1
        """
        norm1 = cls.normalize_title(title1)
        norm2 = cls.normalize_title(title2)

        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, norm1, norm2).ratio()

    @classmethod
    def dates_match(
        cls,
        date1: Optional[date],
        date2: Optional[date],
        tolerance_days: int = 90,
    ) -> bool:
        """
        Check if two dates are within tolerance of each other.

        Args:
            date1: First date
            date2: Second date
            tolerance_days: Maximum days apart to consider a match

        Returns:
            True if dates match within tolerance
        """
        if date1 is None or date2 is None:
            return True  # If either date is unknown, don't penalize

        return abs((date1 - date2).days) <= tolerance_days

    async def find_steam_match(
        self,
        title: str,
        release_date: Optional[date] = None,
        opencritic_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Find matching Steam app ID for a game.

        Args:
            title: Game title
            release_date: Optional release date for better matching
            opencritic_id: Optional OpenCritic ID for manual override lookup

        Returns:
            Steam app ID if found, None otherwise
        """
        # Check manual overrides first
        if opencritic_id and opencritic_id in self.MANUAL_OVERRIDES:
            override = self.MANUAL_OVERRIDES[opencritic_id]
            if "steam_app_id" in override:
                return override["steam_app_id"]

        # Search Steam with fallbacks for known store-search quirks.
        search_results: List[Dict[str, Any]] = []
        for query in self.build_search_queries(title):
            search_results = await self.steam_service.search_games(query)
            if search_results:
                break
        if not search_results:
            return None

        comparison_titles = self.build_similarity_titles(title)

        # Find best match
        best_match: Optional[int] = None
        best_score = 0.0

        # First pass: title similarity only (cheap).
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for result in search_results:
            steam_title = result.get("name", "")
            similarity = max(
                self.calculate_similarity(candidate, steam_title)
                for candidate in comparison_titles
            )
            scored.append((similarity, result))

        # Evaluate strongest candidates first; limit app-details requests.
        scored.sort(key=lambda item: item[0], reverse=True)
        for similarity, result in scored[:10]:
            adjusted = similarity

            # Get release date from Steam for verification if we have one
            if similarity > 0.8 and release_date:
                app_details = await self.steam_service.get_app_details(result["steam_app_id"])
                if app_details:
                    steam_data = SteamService.transform_app_details(
                        app_details, result["steam_app_id"]
                    )
                    if not self.dates_match(release_date, steam_data.get("release_date")):
                        # Cross-platform ports/remasters can have large release-date deltas.
                        # Keep near-exact title matches viable, penalize only weaker matches.
                        if similarity < 0.97:
                            adjusted *= 0.7

            if adjusted > best_score:
                best_score = adjusted
                best_match = result["steam_app_id"]

        # Only return if confidence is high enough
        if best_score >= 0.85:
            return best_match

        return None

    def find_metacritic_slug(
        self,
        title: str,
        opencritic_id: Optional[int] = None,
    ) -> str:
        """
        Generate Metacritic slug for a game.

        Args:
            title: Game title
            opencritic_id: Optional OpenCritic ID for manual override lookup

        Returns:
            Metacritic slug
        """
        # Check manual overrides first
        if opencritic_id and opencritic_id in self.MANUAL_OVERRIDES:
            override = self.MANUAL_OVERRIDES[opencritic_id]
            if "metacritic_slug" in override:
                return override["metacritic_slug"]

        # Generate slug from title
        return MetacriticService.slugify(title)

    async def match_game(
        self,
        title: str,
        release_date: Optional[date] = None,
        opencritic_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Find matches for a game across Steam and Metacritic.

        Args:
            title: Game title
            release_date: Optional release date
            opencritic_id: Optional OpenCritic ID

        Returns:
            Dictionary with steam_app_id and metacritic_slug
        """
        steam_app_id = await self.find_steam_match(
            title, release_date, opencritic_id
        )

        metacritic_slug = self.find_metacritic_slug(title, opencritic_id)

        return {
            "steam_app_id": steam_app_id,
            "metacritic_slug": metacritic_slug,
        }

    async def verify_metacritic_slug(
        self,
        slug: str,
        expected_title: str,
    ) -> bool:
        """
        Verify that a Metacritic slug is valid and matches expected game.

        Args:
            slug: Metacritic slug to verify
            expected_title: Expected game title

        Returns:
            True if slug is valid and matches
        """
        if not self.metacritic_service:
            return True  # Can't verify without service

        try:
            # Try to get the score - if it works, the page exists
            score_data = await self.metacritic_service.get_user_score(slug)
            return score_data is not None
        except Exception:
            return False

    @classmethod
    def add_manual_override(
        cls,
        opencritic_id: int,
        steam_app_id: Optional[int] = None,
        metacritic_slug: Optional[str] = None,
    ) -> None:
        """
        Add a manual override for game matching.

        Args:
            opencritic_id: OpenCritic game ID
            steam_app_id: Steam app ID to use
            metacritic_slug: Metacritic slug to use
        """
        if opencritic_id not in cls.MANUAL_OVERRIDES:
            cls.MANUAL_OVERRIDES[opencritic_id] = {}

        if steam_app_id is not None:
            cls.MANUAL_OVERRIDES[opencritic_id]["steam_app_id"] = steam_app_id

        if metacritic_slug is not None:
            cls.MANUAL_OVERRIDES[opencritic_id]["metacritic_slug"] = metacritic_slug


# Utility functions for batch matching

async def batch_match_games(
    games: List[Dict[str, Any]],
    matcher: Optional[GameMatcher] = None,
) -> List[Dict[str, Any]]:
    """
    Match multiple games at once.

    Args:
        games: List of game dictionaries with 'title', 'release_date', 'opencritic_id'
        matcher: Optional GameMatcher instance

    Returns:
        List of games with steam_app_id and metacritic_slug added
    """
    if matcher is None:
        matcher = GameMatcher()

    results = []
    for game in games:
        match_data = await matcher.match_game(
            title=game.get("title", ""),
            release_date=game.get("release_date"),
            opencritic_id=game.get("opencritic_id"),
        )
        results.append({**game, **match_data})

    return results

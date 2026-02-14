"""
Match news articles to games by checking if game titles appear in article text.

Uses word-boundary regex matching against article titles (and optionally descriptions)
to link RSS news articles to specific games in the database.
"""

import re
from typing import Optional


class NewsMatcher:
    """Matches news articles to games using word-boundary title matching."""

    MIN_TITLE_LENGTH = 4

    def __init__(self, games: list[tuple[int, str]]):
        """
        Args:
            games: List of (game_id, game_title) tuples from the database.
        """
        self._patterns = []
        for game_id, title in games:
            if len(title) < self.MIN_TITLE_LENGTH:
                continue
            pattern = re.compile(
                r"\b" + re.escape(title) + r"\b",
                re.IGNORECASE,
            )
            self._patterns.append((game_id, title, pattern))
        # Sort by title length descending so longer (more specific) matches win
        self._patterns.sort(key=lambda x: len(x[1]), reverse=True)

    def match(self, article_title: str, description: Optional[str] = None) -> Optional[int]:
        """Return the game_id if a game title is found in the article, or None."""
        for game_id, _title, pattern in self._patterns:
            if pattern.search(article_title):
                return game_id
        if description:
            for game_id, _title, pattern in self._patterns:
                if pattern.search(description):
                    return game_id
        return None

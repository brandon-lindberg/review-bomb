"""
Match news articles to games by checking if game titles appear in article text.

Uses normalized phrase matching (with punctuation/possessive tolerance) against
article titles and descriptions to link RSS news articles to games.
"""

import re
from collections import Counter
from typing import Optional


class NewsMatcher:
    """Matches news articles to games using normalized title phrase matching."""

    MIN_TITLE_LENGTH = 4
    MIN_FALLBACK_TOKEN_COUNT = 3
    MIN_FALLBACK_TOKEN_LENGTH = 3
    MAX_FALLBACK_ANCHOR_FREQUENCY = 12
    _WHITESPACE_RE = re.compile(r"\s+")
    _NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
    # Treat apostrophe-s as a possessive marker so "Rayman's" matches "Rayman".
    _POSSESSIVE_RE = re.compile(r"\b([a-z0-9]+)'s\b")
    _ORDINAL_RE = re.compile(r"\b(\d+)(st|nd|rd|th)\b")
    _ROMAN_TOKEN_RE = re.compile(r"^[ivxlcdm]+$")
    _FALLBACK_STOPWORDS = {
        "a",
        "an",
        "and",
        "edition",
        "for",
        "from",
        "hd",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }

    def __init__(self, games: list[tuple[int, str]]):
        """
        Args:
            games: List of (game_id, game_title) tuples from the database.
        """
        self._patterns = []
        fallback_seed = []
        for game_id, title in games:
            if len(title) < self.MIN_TITLE_LENGTH:
                continue

            normalized_title = self._normalize(title)
            if len(normalized_title) < self.MIN_TITLE_LENGTH:
                continue

            exact_pattern = re.compile(
                r"(?:^| )" + re.escape(normalized_title) + r"(?: |$)",
            )
            patterns = [exact_pattern]

            segmented_pattern = self._build_segmented_pattern(title)
            if segmented_pattern:
                patterns.append(segmented_pattern)

            self._patterns.append((game_id, title, patterns, normalized_title))
            fallback_tokens = self._extract_fallback_tokens(normalized_title)
            if len(fallback_tokens) >= self.MIN_FALLBACK_TOKEN_COUNT:
                fallback_seed.append((game_id, fallback_tokens, normalized_title))

        # Sort by title length descending so longer (more specific) matches win
        self._patterns.sort(key=lambda x: len(x[3]), reverse=True)
        self._fallback_by_anchor = self._build_fallback_index(fallback_seed)

    @classmethod
    def _normalize(cls, text: Optional[str]) -> str:
        """Normalize text for resilient phrase matching."""
        if not text:
            return ""

        normalized = text.lower()
        normalized = normalized.replace("’", "'").replace("‘", "'")
        normalized = cls._ORDINAL_RE.sub(r"\1", normalized)
        normalized = cls._POSSESSIVE_RE.sub(r"\1", normalized)
        normalized = normalized.replace("'", "")
        normalized = cls._NON_ALNUM_RE.sub(" ", normalized)
        normalized = cls._WHITESPACE_RE.sub(" ", normalized).strip()
        return normalized

    @classmethod
    def _build_segmented_pattern(cls, title: str) -> Optional[re.Pattern[str]]:
        """
        Build a looser pattern for colon-subtitle titles.

        Example:
        "God of War: Sons of Sparta" matches "God of War ... Sons of Sparta".
        """
        if ":" not in title:
            return None

        segments = []
        for raw_segment in title.split(":"):
            normalized_segment = cls._normalize(raw_segment)
            if len(normalized_segment) >= 3:
                segments.append(normalized_segment)

        if len(segments) < 2:
            return None

        segment_terms = [
            r"(?:^| )" + re.escape(segment) + r"(?: |$)"
            for segment in segments
        ]
        return re.compile(r".*?".join(segment_terms))

    @classmethod
    def _extract_fallback_tokens(cls, normalized_title: str) -> list[str]:
        """Extract meaningful tokens used by the second-tier matcher."""
        tokens = []
        for token in normalized_title.split():
            if token in cls._FALLBACK_STOPWORDS:
                continue
            if token.isdigit() or cls._ROMAN_TOKEN_RE.match(token):
                tokens.append(token)
                continue
            if len(token) < cls.MIN_FALLBACK_TOKEN_LENGTH:
                continue
            tokens.append(token)
        return tokens

    @classmethod
    def _build_fallback_index(cls, fallback_seed):
        """
        Build an anchor-token index for resilient matching when exact phrase
        matching fails due intervening words/rephrasing.
        """
        token_frequency = Counter()
        for _game_id, tokens, _normalized_title in fallback_seed:
            for token in set(tokens):
                token_frequency[token] += 1

        fallback_by_anchor = {}
        for game_id, tokens, normalized_title in fallback_seed:
            unique_tokens = set(tokens)
            anchor = min(
                unique_tokens,
                key=lambda token: (token_frequency[token], -len(token)),
            )
            if token_frequency[anchor] > cls.MAX_FALLBACK_ANCHOR_FREQUENCY:
                continue

            entry = (
                game_id,
                tuple(tokens),
                frozenset(unique_tokens),
                (len(unique_tokens), len(normalized_title)),
            )
            fallback_by_anchor.setdefault(anchor, []).append(entry)

        for anchor in fallback_by_anchor:
            fallback_by_anchor[anchor].sort(
                key=lambda item: (item[3][0], item[3][1]),
                reverse=True,
            )

        return fallback_by_anchor

    @staticmethod
    def _tokens_in_order(needle_tokens: tuple[str, ...], haystack_tokens: list[str]) -> bool:
        """Return True if all needle tokens appear in haystack in order."""
        start = 0
        for token in needle_tokens:
            try:
                index = haystack_tokens.index(token, start)
            except ValueError:
                return False
            start = index + 1
        return True

    def _match_fallback(self, normalized_text: str) -> Optional[int]:
        """Second-tier matcher for rephrased title mentions."""
        if not normalized_text or not self._fallback_by_anchor:
            return None

        article_tokens = normalized_text.split()
        if len(article_tokens) < self.MIN_FALLBACK_TOKEN_COUNT:
            return None

        article_token_set = set(article_tokens)
        candidates_by_game_id = {}
        for token in article_token_set:
            for entry in self._fallback_by_anchor.get(token, []):
                game_id = entry[0]
                if game_id not in candidates_by_game_id:
                    candidates_by_game_id[game_id] = entry

        if not candidates_by_game_id:
            return None

        candidates = sorted(
            candidates_by_game_id.values(),
            key=lambda item: (item[3][0], item[3][1]),
            reverse=True,
        )
        for game_id, ordered_tokens, required_tokens, _score in candidates:
            if not required_tokens.issubset(article_token_set):
                continue
            if self._tokens_in_order(ordered_tokens, article_tokens):
                return game_id

        return None

    def match(self, article_title: str, description: Optional[str] = None) -> Optional[int]:
        """Return the game_id if a game title is found in the article, or None."""
        normalized_title = self._normalize(article_title)
        for game_id, _title, patterns, _normalized_game_title in self._patterns:
            if normalized_title and any(pattern.search(normalized_title) for pattern in patterns):
                return game_id

        normalized_description = self._normalize(description)
        if normalized_description:
            for game_id, _title, patterns, _normalized_game_title in self._patterns:
                if any(pattern.search(normalized_description) for pattern in patterns):
                    return game_id

        fallback_title_match = self._match_fallback(normalized_title)
        if fallback_title_match:
            return fallback_title_match

        return None

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
    MIN_EXACT_MATCH_SCORE = 65
    MIN_EXACT_MATCH_MARGIN = 8
    MIN_FALLBACK_TOKEN_COUNT = 3
    MIN_FALLBACK_TOKEN_LENGTH = 3
    MAX_FALLBACK_ANCHOR_FREQUENCY = 12
    _WHITESPACE_RE = re.compile(r"\s+")
    _NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
    # Treat apostrophe-s as a possessive marker so "Rayman's" matches "Rayman".
    _POSSESSIVE_RE = re.compile(r"\b([a-z0-9]+)'s\b")
    _ORDINAL_RE = re.compile(r"\b(\d+)(st|nd|rd|th)\b")
    _ROMAN_TOKEN_RE = re.compile(r"^[ivxlcdm]+$")
    _SEQUEL_NUMERIC_TOKEN_RE = re.compile(r"^(?:[2-9]|1[0-9]|20)$")
    _ROMAN_TO_INT_TOKEN_MAP = {
        "i": "1",
        "ii": "2",
        "iii": "3",
        "iv": "4",
        "v": "5",
        "vi": "6",
        "vii": "7",
        "viii": "8",
        "ix": "9",
        "x": "10",
        "xi": "11",
        "xii": "12",
        "xiii": "13",
        "xiv": "14",
        "xv": "15",
        "xvi": "16",
        "xvii": "17",
        "xviii": "18",
        "xix": "19",
        "xx": "20",
    }
    _INT_TO_ROMAN_TOKEN_MAP = {
        value: key for key, value in _ROMAN_TO_INT_TOKEN_MAP.items()
    }
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
    # Single-token game titles that are common natural-language words require
    # stricter confirmation to avoid hijacking generic headlines.
    _AMBIGUOUS_SINGLE_WORD_TITLES = {
        "control",
        "everything",
        "inside",
        "prey",
        "stray",
    }
    _COMMON_LANGUAGE_TOKENS = {
        "again",
        "all",
        "alone",
        "another",
        "anything",
        "arms",
        "battle",
        "beyond",
        "black",
        "blue",
        "bright",
        "broken",
        "change",
        "control",
        "day",
        "days",
        "dead",
        "deeper",
        "destiny",
        "dream",
        "dreams",
        "echo",
        "edge",
        "echoes",
        "element",
        "expand",
        "everything",
        "evolve",
        "fall",
        "final",
        "first",
        "forever",
        "future",
        "ghost",
        "glow",
        "grow",
        "hatred",
        "hero",
        "horizon",
        "idea",
        "inside",
        "journey",
        "klaus",
        "light",
        "legend",
        "life",
        "lines",
        "lost",
        "marvel",
        "origin",
        "origins",
        "out",
        "outside",
        "paladins",
        "path",
        "play",
        "prey",
        "prime",
        "project",
        "redacted",
        "red",
        "redo",
        "return",
        "rise",
        "road",
        "rumble",
        "saga",
        "shadow",
        "shadows",
        "shift",
        "signal",
        "star",
        "stars",
        "state",
        "story",
        "stray",
        "source",
        "super",
        "ultimate",
        "under",
        "unknown",
        "void",
        "war",
        "world",
    }
    # If an ambiguous token starts the headline with one of these follow-up
    # words, it is usually a generic phrase ("Everything you need to know...").
    _GENERIC_HEADLINE_FOLLOWUPS = {
        "about",
        "all",
        "and",
        "announced",
        "are",
        "at",
        "coming",
        "for",
        "from",
        "in",
        "is",
        "know",
        "learned",
        "need",
        "new",
        "on",
        "revealed",
        "shows",
        "that",
        "thats",
        "to",
        "we",
        "what",
        "you",
    }
    _AMBIGUOUS_PREPOSITIONS = {
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "to",
        "with",
        "without",
    }
    _AMBIGUOUS_ALLOWED_PREDECESSORS = (
        _FALLBACK_STOPWORDS
        | _AMBIGUOUS_PREPOSITIONS
        | _GENERIC_HEADLINE_FOLLOWUPS
        | {
            "hands",
            "latest",
            "new",
            "official",
            "our",
        }
    )
    # Nearby terms that strongly imply game-title usage for ambiguous words.
    _GAME_CONTEXT_TOKENS = {
        "access",
        "announced",
        "announces",
        "beta",
        "build",
        "class",
        "classes",
        "confirmed",
        "confirms",
        "date",
        "dates",
        "demo",
        "dev",
        "developer",
        "developers",
        "dlc",
        "download",
        "early",
        "event",
        "expansion",
        "game",
        "gameplay",
        "guide",
        "guides",
        "hands",
        "impression",
        "impressions",
        "launch",
        "maps",
        "mode",
        "modding",
        "patches",
        "player",
        "players",
        "playtest",
        "patch",
        "port",
        "preview",
        "release",
        "released",
        "releasing",
        "remake",
        "remaster",
        "review",
        "reviews",
        "season",
        "sequel",
        "server",
        "steam",
        "studio",
        "switch",
        "trailer",
        "times",
        "update",
        "updates",
        "walkthrough",
        "xbox",
        "playstation",
        "ps5",
        "pc",
    }
    _REFERENCE_PREFIX_PATTERNS = (
        ("fan", "of"),
        ("fans", "of"),
        ("homage", "to"),
        ("inspired", "by"),
        ("similar", "to"),
        ("spiritual", "successor", "to"),
        ("successor", "to"),
        ("tribute", "to"),
    )
    _REFERENCE_PREFIX_TOKENS = {
        "channeling",
        "channels",
        "echoes",
        "echoing",
        "evokes",
        "evoking",
        "like",
        "meets",
    }
    _REFERENCE_SUFFIX_TOKENS = {
        "inspired",
        "like",
    }

    def __init__(self, games: list[tuple[int, str]]):
        """
        Args:
            games: List of (game_id, game_title) tuples from the database.
        """
        self._patterns = []
        prepared_games = []
        self._title_token_frequency = Counter()
        fallback_seed = []
        for game_id, title in games:
            if len(title) < self.MIN_TITLE_LENGTH:
                continue

            normalized_title = self._normalize(title)
            if len(normalized_title) < self.MIN_TITLE_LENGTH:
                continue

            tokens = normalized_title.split()
            for token in set(tokens):
                self._title_token_frequency[token] += 1

            prepared_games.append((game_id, title, normalized_title, tokens))
            fallback_tokens = self._extract_fallback_tokens(normalized_title)
            if len(fallback_tokens) >= self.MIN_FALLBACK_TOKEN_COUNT:
                fallback_seed.append((game_id, fallback_tokens, normalized_title))

        for game_id, title, normalized_title, tokens in prepared_games:
            patterns = [
                re.compile(r"(?:^| )" + re.escape(variant) + r"(?: |$)")
                for variant in sorted(
                    self._expand_numeric_title_variants(normalized_title),
                    key=len,
                    reverse=True,
                )
            ]

            segmented_pattern = self._build_segmented_pattern(title)
            if segmented_pattern:
                patterns.append(segmented_pattern)

            ambiguous_title = self._is_ambiguous_title(tokens)
            primary_token = self._primary_title_token(tokens)

            self._patterns.append(
                (
                    game_id,
                    title,
                    patterns,
                    normalized_title,
                    ambiguous_title,
                    primary_token,
                )
            )

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
    def _numeric_token_variants(cls, token: str) -> set[str]:
        """Return roman/arabic token variants for sequel-style numbers."""
        variants = {token}
        if token in cls._ROMAN_TO_INT_TOKEN_MAP:
            variants.add(cls._ROMAN_TO_INT_TOKEN_MAP[token])
        if token in cls._INT_TO_ROMAN_TOKEN_MAP:
            variants.add(cls._INT_TO_ROMAN_TOKEN_MAP[token])
        return variants

    @classmethod
    def _expand_numeric_title_variants(cls, normalized_title: str) -> set[str]:
        """
        Expand title phrases to include arabic/roman numeral variants.
        Example: "helldivers ii" -> {"helldivers ii", "helldivers 2"}.
        """
        tokens = normalized_title.split()
        if not tokens:
            return {normalized_title}

        variants: set[tuple[str, ...]] = {tuple(tokens)}
        for idx, token in enumerate(tokens):
            token_variants = cls._numeric_token_variants(token)
            if len(token_variants) == 1:
                continue

            next_variants: set[tuple[str, ...]] = set(variants)
            for existing in variants:
                for replacement in token_variants:
                    if replacement == existing[idx]:
                        continue
                    replaced = list(existing)
                    replaced[idx] = replacement
                    next_variants.add(tuple(replaced))
            variants = next_variants

        return {" ".join(parts) for parts in variants if parts}

    @classmethod
    def _title_has_numeric_suffix(cls, normalized_title: str) -> bool:
        tokens = normalized_title.split()
        if not tokens:
            return False
        last = tokens[-1]
        return bool(
            cls._SEQUEL_NUMERIC_TOKEN_RE.match(last)
            or last in cls._ROMAN_TO_INT_TOKEN_MAP
        )

    @classmethod
    def _is_numeric_sequel_token(cls, token: str) -> bool:
        return bool(
            cls._SEQUEL_NUMERIC_TOKEN_RE.match(token)
            or token in cls._ROMAN_TO_INT_TOKEN_MAP
        )

    @classmethod
    def _has_numeric_sequel_suffix_usage(
        cls,
        normalized_text: str,
        normalized_game_title: str,
    ) -> bool:
        """
        Return True when an article uses "<base title> <sequel-number>".
        This helps avoid linking sequel headlines to base-game records.
        """
        article_tokens = normalized_text.split()
        game_tokens = normalized_game_title.split()
        if not article_tokens or not game_tokens:
            return False

        game_len = len(game_tokens)
        for idx in range(0, len(article_tokens) - game_len):
            if article_tokens[idx:idx + game_len] != game_tokens:
                continue
            suffix_index = idx + game_len
            if suffix_index >= len(article_tokens):
                continue
            if cls._is_numeric_sequel_token(article_tokens[suffix_index]):
                return True
        return False

    @classmethod
    def _primary_title_token(cls, tokens: list[str]) -> Optional[str]:
        """Pick the strongest token for ambiguity checks on a title."""
        if not tokens:
            return None
        meaningful = [token for token in tokens if token not in cls._FALLBACK_STOPWORDS]
        if meaningful:
            return meaningful[0]
        return tokens[0]

    @classmethod
    def _is_common_ambiguous_token(cls, token: str) -> bool:
        return (
            token in cls._AMBIGUOUS_SINGLE_WORD_TITLES
            or token in cls._COMMON_LANGUAGE_TOKENS
        )

    def _is_high_risk_ambiguous_single_word_title(
        self,
        normalized_game_title: str,
        primary_token: Optional[str],
    ) -> bool:
        if not primary_token:
            return False

        meaningful = [
            token
            for token in normalized_game_title.split()
            if token not in self._FALLBACK_STOPWORDS
        ]
        if len(meaningful) != 1:
            return False

        token = meaningful[0]
        if token.isdigit() or self._ROMAN_TOKEN_RE.match(token):
            return False
        if self._is_common_ambiguous_token(token):
            return True
        if len(token) <= 5:
            return True
        return False

    def _is_ambiguous_title(self, tokens: list[str]) -> bool:
        """Detect titles likely to collide with generic prose/news phrasing."""
        if not tokens:
            return False

        meaningful = [token for token in tokens if token not in self._FALLBACK_STOPWORDS]
        primary_token = self._primary_title_token(tokens)
        if not primary_token:
            return False

        if len(meaningful) == 1:
            token = meaningful[0]
            if token.isdigit() or self._ROMAN_TOKEN_RE.match(token):
                return False
            if self._is_common_ambiguous_token(token):
                return True
            if len(token) <= 5:
                return True
            if self._title_token_frequency.get(token, 0) > 1:
                return True
            return False

        if len(meaningful) == 2 and all(token in self._COMMON_LANGUAGE_TOKENS for token in meaningful):
            return True

        # Very short two-token titles with repeated high-frequency token can be noisy.
        if len(meaningful) == 2 and any(self._title_token_frequency.get(token, 0) > 10 for token in meaningful):
            return True

        return False

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

    @classmethod
    def _is_generic_ambiguous_lead_phrase(
        cls,
        normalized_title: str,
        ambiguous_token: str,
    ) -> bool:
        """Detect ambiguous-token headlines that are generic prose, not a game mention."""
        tokens = normalized_title.split()
        if len(tokens) < 2:
            return False
        if tokens[0] != ambiguous_token:
            return False
        return tokens[1] in cls._GENERIC_HEADLINE_FOLLOWUPS

    @classmethod
    def _has_ambiguous_game_context(
        cls,
        normalized_title: str,
        ambiguous_token: str,
    ) -> bool:
        """
        Ambiguous single-word titles only auto-match if a game-context token is near
        the token in the headline (e.g. "Everything review", "Control trailer").
        """
        tokens = normalized_title.split()
        if not tokens:
            return False

        for index, token in enumerate(tokens):
            if token != ambiguous_token:
                continue

            if index > 0 and tokens[index - 1] in cls._AMBIGUOUS_PREPOSITIONS:
                continue
            if index + 1 < len(tokens) and tokens[index + 1] in cls._AMBIGUOUS_PREPOSITIONS:
                continue

            prev_tokens = tokens[max(0, index - 3):index]
            next_tokens = tokens[index + 1:index + 4]
            neighborhood = prev_tokens + next_tokens
            if any(candidate in cls._GAME_CONTEXT_TOKENS for candidate in neighborhood):
                return True
            if any(
                candidate.isdigit() or cls._ROMAN_TOKEN_RE.match(candidate)
                for candidate in neighborhood
            ):
                return True

        return False

    @classmethod
    def _has_blocking_ambiguous_predecessor(
        cls,
        normalized_title: str,
        ambiguous_token: str,
    ) -> bool:
        """
        High-risk one-word titles should not match when they only appear as the
        trailing token of a larger phrase/title such as "Mirror's Edge".
        """
        tokens = normalized_title.split()
        if not tokens:
            return False

        for index, token in enumerate(tokens):
            if token != ambiguous_token or index == 0:
                continue

            previous = tokens[index - 1]
            if previous in cls._AMBIGUOUS_ALLOWED_PREDECESSORS:
                continue
            if previous in cls._GAME_CONTEXT_TOKENS:
                continue
            if previous.isdigit() or cls._ROMAN_TOKEN_RE.match(previous):
                continue
            return True

        return False

    @classmethod
    def _has_reference_only_phrase_usage(
        cls,
        normalized_text: str,
        normalized_game_title: str,
    ) -> bool:
        """
        Detect exact title mentions used as comparison/reference phrases rather
        than the article's primary subject, e.g. "channels Mirror's Edge".
        """
        article_tokens = normalized_text.split()
        game_tokens = normalized_game_title.split()
        if len(article_tokens) < len(game_tokens) or len(game_tokens) < 2:
            return False

        match_indexes = [
            index
            for index in range(0, len(article_tokens) - len(game_tokens) + 1)
            if article_tokens[index:index + len(game_tokens)] == game_tokens
        ]
        if not match_indexes:
            return False

        for index in match_indexes:
            prefix = article_tokens[max(0, index - 4):index]
            suffix = article_tokens[index + len(game_tokens):index + len(game_tokens) + 3]

            if suffix and suffix[0] in cls._REFERENCE_SUFFIX_TOKENS:
                continue
            if prefix and prefix[-1] in cls._REFERENCE_PREFIX_TOKENS:
                continue
            if any(
                len(prefix) >= len(pattern)
                and tuple(prefix[-len(pattern):]) == pattern
                for pattern in cls._REFERENCE_PREFIX_PATTERNS
            ):
                continue
            return False

        return True

    def _score_exact_match_candidate(
        self,
        *,
        normalized_article_title: str,
        normalized_article_description: str,
        normalized_game_title: str,
        title_matched: bool,
        description_matched: bool,
        ambiguous_title: bool,
        primary_token: Optional[str],
    ) -> int:
        """
        Score one exact/segmented candidate and return an integer confidence score.
        Higher is better; low scores are treated as no-match.
        """
        score = len(normalized_game_title)
        if title_matched:
            score += 90
        if description_matched:
            score += 65

        title_reference_only = (
            title_matched
            and self._has_reference_only_phrase_usage(
                normalized_article_title,
                normalized_game_title,
            )
        )
        description_reference_only = (
            description_matched
            and self._has_reference_only_phrase_usage(
                normalized_article_description,
                normalized_game_title,
            )
        )
        if title_reference_only:
            score -= 130
        if description_reference_only:
            score -= 100

        title_uses_numeric_sequel_suffix = (
            title_matched
            and self._has_numeric_sequel_suffix_usage(
                normalized_article_title,
                normalized_game_title,
            )
        )
        description_uses_numeric_sequel_suffix = (
            description_matched
            and self._has_numeric_sequel_suffix_usage(
                normalized_article_description,
                normalized_game_title,
            )
        )
        title_has_numeric_suffix = self._title_has_numeric_suffix(normalized_game_title)

        if title_has_numeric_suffix:
            if title_uses_numeric_sequel_suffix:
                score += 25
            if description_uses_numeric_sequel_suffix:
                score += 15
        else:
            if title_uses_numeric_sequel_suffix:
                score -= 140
            if description_uses_numeric_sequel_suffix:
                score -= 110

        if not ambiguous_title:
            return score

        if not primary_token:
            return score - 60

        if (
            self._is_common_ambiguous_token(primary_token)
            and title_matched
            and self._is_generic_ambiguous_lead_phrase(
                normalized_article_title,
                primary_token,
            )
        ):
            score -= 130

        title_has_context = (
            title_matched
            and self._has_ambiguous_game_context(normalized_article_title, primary_token)
        )
        description_has_context = (
            description_matched
            and self._has_ambiguous_game_context(normalized_article_description, primary_token)
        )
        high_risk_single_word = self._is_high_risk_ambiguous_single_word_title(
            normalized_game_title,
            primary_token,
        )
        title_has_blocking_predecessor = (
            high_risk_single_word
            and title_matched
            and self._has_blocking_ambiguous_predecessor(
                normalized_article_title,
                primary_token,
            )
        )
        description_has_blocking_predecessor = (
            high_risk_single_word
            and description_matched
            and self._has_blocking_ambiguous_predecessor(
                normalized_article_description,
                primary_token,
            )
        )

        if title_has_blocking_predecessor:
            score -= 140
        if description_has_blocking_predecessor:
            score -= 110

        if title_has_context or description_has_context:
            score += 30
        elif high_risk_single_word:
            # For short/common one-word titles, plain token overlap is too noisy.
            score -= 120
        elif title_matched and not description_matched:
            score -= 70
        elif description_matched and not title_matched:
            score -= 45
        else:
            score -= 35

        return score

    def match(self, article_title: str, description: Optional[str] = None) -> Optional[int]:
        """Return the game_id if a game title is found in the article, or None."""
        normalized_title = self._normalize(article_title)
        normalized_description = self._normalize(description)

        title_exact_candidates = []
        description_only_exact_candidates = []
        for (
            game_id,
            _title,
            patterns,
            normalized_game_title,
            ambiguous_title,
            primary_token,
        ) in self._patterns:
            title_match = bool(
                normalized_title and any(pattern.search(normalized_title) for pattern in patterns)
            )
            description_match = bool(
                normalized_description
                and any(pattern.search(normalized_description) for pattern in patterns)
            )

            if not title_match and not description_match:
                continue

            score = self._score_exact_match_candidate(
                normalized_article_title=normalized_title,
                normalized_article_description=normalized_description,
                normalized_game_title=normalized_game_title,
                title_matched=title_match,
                description_matched=description_match,
                ambiguous_title=ambiguous_title,
                primary_token=primary_token,
            )
            candidate = (score, len(normalized_game_title), game_id)
            if title_match:
                title_exact_candidates.append(candidate)
            else:
                description_only_exact_candidates.append(candidate)

        # If the headline already names one or more candidates, do not let
        # description-only mentions override it (prevents cross-topic hijacks).
        candidate_groups = [title_exact_candidates] if title_exact_candidates else [description_only_exact_candidates]
        for exact_candidates in candidate_groups:
            if not exact_candidates:
                continue
            exact_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            best_score, _best_len, best_game_id = exact_candidates[0]
            if best_score < self.MIN_EXACT_MATCH_SCORE:
                continue
            if len(exact_candidates) == 1:
                return best_game_id
            second_score = exact_candidates[1][0]
            if (best_score - second_score) >= self.MIN_EXACT_MATCH_MARGIN:
                return best_game_id

        fallback_title_match = self._match_fallback(normalized_title)
        if fallback_title_match:
            return fallback_title_match

        return None

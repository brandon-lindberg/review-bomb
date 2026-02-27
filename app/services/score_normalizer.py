"""
Score normalization service.

Converts various score formats to a 0-100 scale for comparison.
"""

import re
from decimal import Decimal
from typing import Optional, Tuple


class ScoreNormalizer:
    """Normalizes game review scores to a 0-100 scale."""

    # Letter grade to numeric mapping
    LETTER_GRADES = {
        "A+": 97, "A": 93, "A-": 90,
        "B+": 87, "B": 83, "B-": 80,
        "C+": 77, "C": 73, "C-": 70,
        "D+": 67, "D": 63, "D-": 60,
        "F": 50,
    }

    # Common score scales and their multipliers to get to 100
    SCALE_MULTIPLIERS = {
        "5": 20,      # 0-5 scale -> multiply by 20
        "10": 10,     # 0-10 scale -> multiply by 10
        "20": 5,      # 0-20 scale -> multiply by 5
        "100": 1,     # 0-100 scale -> no change
        "4": 25,      # 0-4 scale (stars) -> multiply by 25
    }

    @staticmethod
    def _format_scale(scale_value: float) -> str:
        """Render numeric scale consistently without trailing .0."""
        if scale_value.is_integer():
            return str(int(scale_value))
        return str(scale_value)

    @classmethod
    def normalize(
        cls,
        raw_score: str,
        scale: Optional[str] = None,
    ) -> Tuple[Optional[Decimal], Optional[str]]:
        """
        Normalize a score to 0-100 scale.

        Args:
            raw_score: The original score string (e.g., "8.5", "4/5", "B+", "85%")
            scale: Optional scale hint (e.g., "10", "5", "100", "letter")

        Returns:
            Tuple of (normalized_score, detected_scale)
            Returns (None, None) if score cannot be parsed
        """
        if not raw_score:
            return None, None

        raw_score = raw_score.strip().upper()

        # Handle "N/A", "TBD", text-based recommendations, and other non-numeric indicators
        # These are NOT real scores and should not be included in disparity calculations
        unscored_values = {
            # Explicit unscored indicators
            "N/A", "TBD", "UNSCORED", "-", "", "NA", "NONE", "NO SCORE",
            # Recommendation-based systems (not numeric scores)
            "RECOMMENDED", "NOT RECOMMENDED", "YES", "NO",
            "BUY", "BUY IT", "DON'T BUY", "SKIP", "SKIP IT",
            "ESSENTIAL", "MUST-PLAY", "MUST PLAY", "AVOID",
            "WORTH PLAYING", "WORTH IT", "NOT WORTH IT",
            # Award/badge systems
            "EDITORS' CHOICE", "EDITOR'S CHOICE", "EDITORS CHOICE",
            "PLATINUM", "GOLD", "SILVER", "BRONZE",
            # Thumbs systems
            "THUMBS UP", "THUMBS DOWN",
        }
        if raw_score in unscored_values:
            return None, None

        # Try letter grade first
        if raw_score in cls.LETTER_GRADES:
            return Decimal(str(cls.LETTER_GRADES[raw_score])), "letter"

        # Handle percentage format (e.g., "85%")
        if raw_score.endswith("%"):
            try:
                value = float(raw_score[:-1])
                return Decimal(str(round(value, 2))), "100"
            except ValueError:
                pass

        # Handle fraction format (e.g., "4/5", "8.5/10")
        fraction_match = re.match(r"^([\d.]+)\s*/\s*([\d.]+)$", raw_score)
        if fraction_match:
            try:
                numerator = float(fraction_match.group(1))
                denominator = float(fraction_match.group(2))
                if denominator > 0:
                    normalized = (numerator / denominator) * 100
                    detected_scale = str(int(denominator)) if denominator == int(denominator) else str(denominator)
                    return Decimal(str(round(normalized, 2))), detected_scale
            except ValueError:
                pass

        # Handle numeric score
        try:
            value = float(raw_score)

            # If a numeric scale is provided, prefer ratio normalization.
            if scale:
                try:
                    scale_value = float(scale)
                except (TypeError, ValueError):
                    scale_value = None

                if scale_value and scale_value > 0:
                    # Standard case: 7 on a 10-scale => 70.
                    if 0 <= value <= scale_value:
                        normalized = (value / scale_value) * 100
                        return Decimal(str(round(normalized, 2))), cls._format_scale(scale_value)

                    # Source sometimes reports a base of 10/20 while score is already 0-100.
                    if value > scale_value and 0 <= value <= 100:
                        return Decimal(str(round(value, 2))), "100"

                    # Out-of-range values should be treated as unscored.
                    return None, None

            # Try to detect scale from value range
            detected_scale = cls._detect_scale(value)
            if detected_scale:
                multiplier = cls.SCALE_MULTIPLIERS[detected_scale]
                normalized = value * multiplier
                return Decimal(str(round(min(normalized, 100), 2))), detected_scale

            # If value is already 0-100 range, assume it's on 100 scale
            if 0 <= value <= 100:
                return Decimal(str(round(value, 2))), "100"

        except ValueError:
            pass

        return None, None

    @classmethod
    def _detect_scale(cls, value: float) -> Optional[str]:
        """
        Try to detect the scale from the value.

        This is a heuristic - values > 10 are assumed to be on 100 scale,
        values <= 10 are assumed to be on 10 scale, etc.
        """
        if value > 20:
            return "100"
        elif value > 10:
            return "20"
        elif value > 5:
            return "10"
        elif value > 4:
            return "5"
        else:
            # Could be 4-star or 5-star, default to 5
            return "5"

    @classmethod
    def normalize_steam_score(cls, positive: int, negative: int) -> Optional[Decimal]:
        """
        Calculate Steam review score from positive/negative counts.

        Steam displays this as a percentage of positive reviews.
        """
        total = positive + negative
        if total == 0:
            return None

        percentage = (positive / total) * 100
        return Decimal(str(round(percentage, 2)))

    @classmethod
    def normalize_metacritic_user_score(cls, score: float) -> Decimal:
        """
        Normalize Metacritic user score (0-10 scale) to 0-100.
        """
        return Decimal(str(round(score * 10, 2)))

    @classmethod
    def get_steam_review_description(cls, score: Decimal) -> str:
        """
        Get Steam-style review description from percentage score.
        """
        score_float = float(score)

        if score_float >= 95:
            return "Overwhelmingly Positive"
        elif score_float >= 80:
            return "Very Positive"
        elif score_float >= 70:
            return "Mostly Positive"
        elif score_float >= 40:
            return "Mixed"
        elif score_float >= 20:
            return "Mostly Negative"
        else:
            return "Overwhelmingly Negative"

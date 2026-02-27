"""
Helpers for correcting stale review normalized scores at read time.
"""

from decimal import Decimal
from typing import Optional, Tuple

from app.services.score_normalizer import ScoreNormalizer


def corrected_normalized_score(
    *,
    score_raw: Optional[str],
    score_scale: Optional[str],
    stored_score_normalized: Optional[Decimal],
) -> Tuple[Optional[Decimal], bool]:
    """
    Recompute a review's normalized score from raw+scale.

    Returns:
        (score_to_use, was_corrected)
    """
    if not score_raw:
        return stored_score_normalized, False

    recomputed, _detected_scale = ScoreNormalizer.normalize(score_raw, score_scale)
    if recomputed is None:
        return stored_score_normalized, False

    if stored_score_normalized != recomputed:
        return recomputed, True

    return stored_score_normalized, False

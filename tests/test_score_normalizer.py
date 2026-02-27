from decimal import Decimal

from app.services.score_normalizer import ScoreNormalizer


def test_numeric_scale_ratio_normalization():
    score, detected_scale = ScoreNormalizer.normalize("8", "10")
    assert score == Decimal("80")
    assert detected_scale == "10"


def test_numeric_scale_raw_already_in_percent_range():
    score, detected_scale = ScoreNormalizer.normalize("70", "10")
    assert score == Decimal("70")
    assert detected_scale == "100"


def test_numeric_scale_handles_twenty_point_schema_drift():
    score, detected_scale = ScoreNormalizer.normalize("80", "20")
    assert score == Decimal("80")
    assert detected_scale == "100"


def test_numeric_scale_keeps_zero_as_valid_score():
    score, detected_scale = ScoreNormalizer.normalize("0", "10")
    assert score == Decimal("0")
    assert detected_scale == "10"

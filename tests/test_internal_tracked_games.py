"""Auth contract for the internal tracked-games endpoint."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.routers.internal import verify_scraper_token


def _settings(token: str | None) -> Settings:
    return Settings(scraper_api_token=token)


def test_verify_scraper_token_allows_when_no_token_configured():
    with patch("app.routers.internal.get_settings", return_value=_settings(None)):
        # Should not raise
        verify_scraper_token(authorization=None)
        verify_scraper_token(authorization="Bearer anything")


def test_verify_scraper_token_rejects_missing_header_when_configured():
    with patch("app.routers.internal.get_settings", return_value=_settings("expected-secret")):
        with pytest.raises(HTTPException) as exc:
            verify_scraper_token(authorization=None)
        assert exc.value.status_code == 401


def test_verify_scraper_token_rejects_malformed_header():
    with patch("app.routers.internal.get_settings", return_value=_settings("expected-secret")):
        with pytest.raises(HTTPException) as exc:
            verify_scraper_token(authorization="Token foo")
        assert exc.value.status_code == 401


def test_verify_scraper_token_rejects_wrong_token():
    with patch("app.routers.internal.get_settings", return_value=_settings("expected-secret")):
        with pytest.raises(HTTPException) as exc:
            verify_scraper_token(authorization="Bearer wrong-secret")
        assert exc.value.status_code == 401


def test_verify_scraper_token_accepts_correct_token():
    with patch("app.routers.internal.get_settings", return_value=_settings("expected-secret")):
        # Should not raise
        verify_scraper_token(authorization="Bearer expected-secret")
        verify_scraper_token(authorization="bearer expected-secret")

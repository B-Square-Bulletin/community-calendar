#!/usr/bin/env python3
"""Tests for Monroe County History Center scraper (SiteGround handling)."""

import logging
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root and scrapers/ to path so scraper imports resolve
_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))
sys.path.insert(0, str(_proj_root / "scrapers"))

from scrapers.monroe_county_history_center import HistoryCenterScraper  # noqa: E402

# The SiteGround sgcaptcha challenge: a 202 meta-refresh page, not a calendar.
CAPTCHA_HTML = (
    '<html><head><link rel="icon" href="data:;"><meta http-equiv="refresh" '
    'content="0;/.well-known/sgcaptcha/?r=%2Fwp-json%2Fwp%2Fv2%2Fajde_events'
    '&y=ipc:64.38.182.56:1791648429.348"></meta></head></html>'
)


def _mock_response(status_code: int, text: str) -> Mock:
    mock = Mock()
    mock.status_code = status_code
    mock.text = text
    mock.json.return_value = []
    return mock


class TestUserAgent:
    """monroehistory.org hard-403s the project UA; a plain one is required."""

    def test_plain_mozilla_user_agent_sent(self):
        scraper = HistoryCenterScraper()
        captured_headers: dict[str, str] = {}

        def intercept_get(url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return _mock_response(200, "[]")

        with patch("scrapers.monroe_county_history_center.requests.get", intercept_get):
            scraper.fetch_events()

        assert captured_headers["User-Agent"] == "Mozilla/5.0", (
            "Project User-Agent is hard-403'd by SiteGround; "
            f"got {captured_headers.get('User-Agent')!r}"
        )


class TestSiteGroundChallenge:
    """A challenge is a block, not an empty calendar."""

    def test_challenge_warns_and_returns_empty(self, caplog):
        scraper = HistoryCenterScraper()

        with (
            patch(
                "scrapers.monroe_county_history_center.requests.get",
                return_value=_mock_response(202, CAPTCHA_HTML),
            ),
            caplog.at_level(logging.WARNING, logger="HistoryCenterScraper"),
        ):
            events = scraper.fetch_events()

        assert events == []
        assert any("captcha challenge" in r.message for r in caplog.records)

    def test_end_of_list_400_is_not_a_challenge(self, caplog):
        """WordPress 400 past the last page is normal, not a block."""
        scraper = HistoryCenterScraper()

        with (
            patch(
                "scrapers.monroe_county_history_center.requests.get",
                return_value=_mock_response(400, '{"code":"rest_post_invalid_page_number"}'),
            ),
            caplog.at_level(logging.WARNING, logger="HistoryCenterScraper"),
        ):
            events = scraper.fetch_events()

        assert events == []
        assert not any("captcha" in r.message for r in caplog.records)

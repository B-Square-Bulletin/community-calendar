#!/usr/bin/env python3
"""Tests for the Tribe Events REST API scraper."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from zoneinfo import ZoneInfo

from scrapers.lib.tribe_events import HEADERS, TribeEventsScraper

# Real event data captured from the NAMI Bloomington Tribe Events API
SAMPLE_API_EVENT = {
    "id": 10000502,
    "title": "Family Support Group (virtual)",
    "start_date": "2026-06-15 17:45:00",
    "end_date": "2026-06-15 19:00:00",
    "url": "https://namigreaterbloomingtonarea.org/event/family-support-group-virtual-24/2026-06-15/",
    "description": "<p>NAMI Family Support Group is a peer-led support group for any adult with a loved one who has experienced symptoms of a mental health condition.</p>",
    "venue": {
        "venue": "Zoom Meeting",
        "address": "",
        "city": "",
        "state": "",
        "zip": "",
        "country": "",
    },
}


class TestHeaders:
    """HEADERS module-level constant should use a browser-like User-Agent."""

    def test_headers_contains_user_agent(self):
        """HEADERS dict must have a User-Agent key."""
        assert "User-Agent" in HEADERS

    def test_user_agent_is_browser_like(self):
        """User-Agent should look like a real browser, not a bot identifier."""
        ua = HEADERS["User-Agent"]
        # Should not contain "compatible" (bot indicator)
        assert "compatible" not in ua.lower(), f"UA looks like a bot: {ua}"
        # Should contain a browser identifier
        assert "Chrome" in ua or "Firefox" in ua or "Safari" in ua, (
            f"UA lacks browser identifier: {ua}"
        )


class TestFetchEventsHeaders:
    """TribeEventsScraper.fetch_events() should pass the correct headers."""

    def test_fetch_events_uses_headers(self):
        """fetch_events should pass HEADERS to requests.get."""
        mock_response = {
            "events": [],
            "total": 0,
            "total_pages": 1,
        }

        # Create a minimal concrete subclass
        class TestScraper(TribeEventsScraper):
            name = "Test Source"
            domain = "test.example.com"
            api_url = "https://test.example.com/wp-json/tribe/events/v1/events/"
            default_location = "Testville, US"
            max_pages = 1

        scraper = TestScraper()

        with patch("scrapers.lib.tribe_events.requests.get") as mock_get:
            mock_get.return_value.ok = True
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            scraper.fetch_events()

            # Verify requests.get was called once with the correct headers
            mock_get.assert_called_once_with(
                f"{scraper.api_url}?per_page={scraper.per_page}&page=1",
                headers=HEADERS,
                timeout=30,
            )


class TestParseEvent:
    """TribeEventsScraper._parse_event() correctly parses API response data."""

    def test_parse_basic_event(self):
        """Parse a real API event and verify output fields."""

        class TestScraper(TribeEventsScraper):
            name = "NAMI Greater Bloomington"
            domain = "namigreaterbloomingtonarea.org"
            api_url = "https://example.com/wp-json/tribe/events/v1/events/"
            timezone = "America/Indiana/Indianapolis"
            default_location = "Bloomington, IN"

        scraper = TestScraper()
        tz = ZoneInfo("America/Indiana/Indianapolis")
        result = scraper._parse_event(SAMPLE_API_EVENT, tz)

        assert result is not None
        assert result["title"] == "Family Support Group (virtual)"
        assert result["url"] == SAMPLE_API_EVENT["url"]
        assert result["location"] == "Zoom Meeting"  # From venue.venue field
        assert "NAMI Family Support Group" in result["description"]
        assert result["uid"] == "tribe-10000502@namigreaterbloomingtonarea.org"

        # Check datetimes
        assert isinstance(result["dtstart"], datetime)
        assert result["dtstart"].year == 2026
        assert result["dtstart"].month == 6
        assert result["dtstart"].day == 15
        assert result["dtstart"].hour == 17
        assert result["dtstart"].minute == 45

        assert isinstance(result["dtend"], datetime)
        assert result["dtend"].hour == 19
        assert result["dtend"].minute == 0


class TestFetchFailures:
    """A broken first page fails the run; a dormant calendar stays quiet."""

    def _scraper(self) -> TribeEventsScraper:
        class TestScraper(TribeEventsScraper):
            name = "Test Source"
            domain = "test.example.com"
            api_url = "https://test.example.com/wp-json/tribe/events/v1/events/"
            max_pages = 3

        return TestScraper()

    def _response(self, payload: dict) -> Mock:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_200_with_no_events_is_quiet_not_a_failure(self):
        with patch("scrapers.lib.tribe_events.requests.get") as mock_get:
            mock_get.return_value = self._response({"events": [], "total_pages": 1})
            assert self._scraper().fetch_events() == []

    def test_http_error_raises(self):
        with patch("scrapers.lib.tribe_events.requests.get") as mock_get:
            response = Mock()
            response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "403 Client Error"
            )
            mock_get.return_value = response
            with pytest.raises(requests.exceptions.HTTPError):
                self._scraper().fetch_events()

    def test_network_error_raises(self):
        with patch("scrapers.lib.tribe_events.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("connection refused")
            with pytest.raises(requests.exceptions.ConnectionError):
                self._scraper().fetch_events()

    def test_malformed_json_raises(self):
        with patch("scrapers.lib.tribe_events.requests.get") as mock_get:
            response = self._response({})
            response.json.side_effect = ValueError("Expecting value: line 1 column 1")
            mock_get.return_value = response
            with pytest.raises(ValueError):
                self._scraper().fetch_events()

    def test_later_page_failure_keeps_pages_already_fetched(self):
        page1 = self._response(
            {
                "events": [{"id": 1, "title": "Concert", "start_date": "2030-05-01 19:00:00"}],
                "total_pages": 2,
            }
        )
        page2 = Mock()
        page2.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        with patch("scrapers.lib.tribe_events.requests.get") as mock_get:
            mock_get.side_effect = [page1, page2]
            events = self._scraper().fetch_events()
        assert [e["title"] for e in events] == ["Concert"]

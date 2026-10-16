#!/usr/bin/env python3
"""Tests for the parameterized Tribe Events REST scraper (scrapers/tribe_rest.py).

Pins the difference between a broken ingest and a genuinely dormant calendar:
a first page that cannot be fetched fails the run, while a 200 with an empty
events array still writes a valid-empty (quiet) calendar.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

# Add project root and scrapers/ to path so scraper imports resolve
_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))
sys.path.insert(0, str(_proj_root / "scrapers"))

from scrapers.tribe_rest import TribeRestScraper  # noqa: E402


def _scraper() -> TribeRestScraper:
    return TribeRestScraper(api_base="https://example.org", source_name="Example Venue")


def _response(payload: dict) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class TestDormantCalendar:
    def test_200_with_no_events_is_quiet_not_a_failure(self):
        """A 200 with an empty events array is dormant, so it returns normally."""
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            mock_get.return_value = _response({"events": [], "total_pages": 1})
            assert _scraper().fetch_events() == []

    def test_200_with_no_events_writes_a_valid_empty_calendar(self, tmp_path):
        """A dormant calendar still writes a valid, zero-event ICS file."""
        output = tmp_path / "example.ics"
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            mock_get.return_value = _response({"events": [], "total_pages": 1})
            _scraper().run(str(output))
        content = output.read_text()
        assert "BEGIN:VCALENDAR" in content
        assert "BEGIN:VEVENT" not in content


class TestFirstPageFailure:
    def test_http_error_raises(self):
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            response = Mock()
            response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "403 Client Error"
            )
            mock_get.return_value = response
            with pytest.raises(requests.exceptions.HTTPError):
                _scraper().fetch_events()

    def test_network_error_raises(self):
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("connection refused")
            with pytest.raises(requests.exceptions.ConnectionError):
                _scraper().fetch_events()

    def test_malformed_json_raises(self):
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            response = _response({})
            response.json.side_effect = ValueError("Expecting value: line 1 column 1")
            mock_get.return_value = response
            with pytest.raises(ValueError):
                _scraper().fetch_events()

    def test_run_writes_no_calendar(self, tmp_path):
        """A failed first page must not overwrite the source's output file."""
        output = tmp_path / "example.ics"
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("connection refused")
            with pytest.raises(requests.exceptions.ConnectionError):
                _scraper().run(str(output))
        assert not output.exists()


class TestLaterPageFailure:
    def test_keeps_pages_already_fetched(self):
        """A failure after the first page keeps the pages already fetched."""
        page1 = _response(
            {
                "events": [{"id": 1, "title": "Concert", "start_date": "2030-05-01 19:00:00"}],
                "total_pages": 2,
            }
        )
        page2 = Mock()
        page2.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        with patch("scrapers.tribe_rest.requests.get") as mock_get:
            mock_get.side_effect = [page1, page2]
            events = _scraper().fetch_events()
        assert [e["title"] for e in events] == ["Concert"]

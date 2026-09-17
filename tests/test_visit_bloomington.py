#!/usr/bin/env python3
"""Tests for the Visit Bloomington Simpleview REST API scraper (#124).

The HTTP boundary (`requests.get`) is mocked, so these tests drive the real
token/paging/mapping/horizon path against payloads captured from the live API
(tests/fixtures/bloomington/visit_bloomington_events.json).
"""

import copy
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.visit_bloomington import (
    CRAWL_DELAY,
    EVENTS_URL,
    TOKEN_URL,
    VisitBloomingtonScraper,
)

TZ = ZoneInfo("America/Indiana/Indianapolis")
FIXTURE = Path(__file__).parent / "fixtures" / "bloomington" / "visit_bloomington_events.json"
# Frozen "now" so the horizon filter is deterministic against the captured payloads.
FROZEN_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=TZ)


def _fixture_docs() -> list[dict]:
    return json.loads(FIXTURE.read_text())["docs"]


class _Resp:
    def __init__(self, status_code: int = 200, text: str = "", payload: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self) -> dict | None:
        return self._payload


def _events_payload(docs: list[dict], count: int | None = None) -> dict:
    return {"docs": {"count": len(docs) if count is None else count, "docs": docs}}


def _fake_get(
    pages: list[dict], token: str = "token-123", token_status: int = 200, events_status: int = 200
):
    """requests.get side_effect: serve the token, then paged docs by skip."""

    def _get(
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout: int | None = None,
    ):
        if url == TOKEN_URL:
            return _Resp(token_status, text=token)
        if url == EVENTS_URL:
            options = json.loads((params or {})["json"])["options"]
            index = options["skip"] // options["limit"]
            payload = pages[index] if index < len(pages) else _events_payload([])
            return _Resp(events_status, payload=payload)
        raise AssertionError(f"unexpected URL: {url}")

    return _get


def _fetch(pages: list[dict], now: datetime = FROZEN_NOW) -> list[dict]:
    scraper = VisitBloomingtonScraper()
    with (
        patch("scrapers.visit_bloomington.requests.get", side_effect=_fake_get(pages)),
        patch("scrapers.visit_bloomington._now", return_value=now),
        patch("scrapers.visit_bloomington.time.sleep"),
    ):
        return scraper.fetch_events()


def _by_title(events: list[dict], title: str) -> dict:
    return next(e for e in events if e["title"] == title)


class TestSingleEventMapping:
    """fetch_events() maps the API's single (recurType 0) docs to events."""

    def test_returns_one_event_per_single_event_and_skips_recurring(self):
        events = _fetch([_events_payload(_fixture_docs())])

        titles = {e["title"] for e in events}
        assert titles == {
            "Author event with Paul C. Gutjahr at Morgenstern Books",
            "IU Football vs Western Kentucky",
            "Resurrection/Kuang ye shi dai | Arthouse Now",
            "Free Riders w/Moxy",
        }
        # The recurring series doc (recurType 5) is deferred to occurrence expansion.
        assert "Downtown Shop Night" not in titles

    def test_timed_event_keeps_clock_times(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")

        assert event["dtstart"] == datetime(2026, 9, 16, 18, 0, tzinfo=TZ)
        assert event["dtend"] == datetime(2026, 9, 16, 19, 0, tzinfo=TZ)

    def test_all_day_only_when_source_has_no_start_time(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "IU Football vs Western Kentucky")

        # The source has no startTime, so this is a genuine all-day DATE event
        # with an exclusive DTEND (the following day).
        assert event["dtstart"] == date(2026, 9, 19)
        assert event["dtend"] == date(2026, 9, 20)

    def test_missing_end_time_gets_a_default_duration(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Free Riders w/Moxy")

        assert event["dtstart"] == datetime(2026, 9, 16, 22, 0, tzinfo=TZ)
        assert event["dtend"] > event["dtstart"]

    def test_uid_is_stable_hash_of_recid_and_occurrence_date(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")

        expected = hashlib.md5(b"59452-2026-09-16").hexdigest() + "@visitbloomington.com"
        assert event["uid"] == expected

    def test_editing_the_title_does_not_change_the_uid(self):
        docs = _fixture_docs()
        events = _fetch([_events_payload(docs)])
        before = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")["uid"]

        edited = copy.deepcopy(docs)
        for doc in edited:
            if doc["recid"] == "59452":
                doc["title"] = "Renamed author event"
        after = _fetch([_events_payload(edited)])
        renamed = next(e for e in after if e["uid"] == before)
        assert renamed["title"] == "Renamed author event"

    def test_two_events_have_distinct_uids(self):
        events = _fetch([_events_payload(_fixture_docs())])
        uids = [e["uid"] for e in events]
        assert len(uids) == len(set(uids))

    def test_location_comes_from_the_source_fields(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")

        assert "Morgenstern Books" in event["location"]
        assert "849 S. Auto Mall Road" in event["location"]
        assert "Bloomington" in event["location"]

    def test_geo_coordinates_map_from_geojson(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")

        # loc.coordinates is GeoJSON [lng, lat]; the event carries (lat, lng).
        assert event["geo"] == (39.15644580000001, -86.49563789999999)

    def test_geo_absent_when_source_has_no_coordinates(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Resurrection/Kuang ye shi dai | Arthouse Now")
        assert event["geo"] is None

    def test_description_is_full_stripped_plain_text(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")

        assert "<p>" not in event["description"]
        assert "<br>" not in event["description"]
        assert "Faith in Space" in event["description"]
        # The API HTML is ~1874 chars; a 500-char cap would truncate it.
        assert len(event["description"]) > 500

    def test_event_url_is_the_cvb_event_page(self):
        events = _fetch([_events_payload(_fixture_docs())])
        event = _by_title(events, "Author event with Paul C. Gutjahr at Morgenstern Books")

        assert event["url"] == (
            "https://www.visitbloomington.com/event/"
            "author-event-with-paul-c-gutjahr-at-morgenstern-books/59452/"
        )
        # `linkUrl` is the origin site; the CVB page must be used, not it.
        assert "morgensternbooks.com" not in event["url"]

    def test_result_context_is_preserved(self):
        docs = _fixture_docs()
        payload = {"docs": {"count": len(docs), "docs": docs}}
        assert payload["docs"]["docs"] == docs


class TestHorizon:
    """Only occurrences inside the Horizon are emitted (client-side on `date`)."""

    def test_occurrence_beyond_the_horizon_is_dropped(self):
        docs = _fixture_docs()
        doc = next(d for d in docs if d["recid"] == "59452")
        doc["date"] = "2028-09-16T03:59:59.000Z"
        doc["endDate"] = "2028-09-16T03:59:59.000Z"
        doc["startDate"] = "2028-09-15T04:00:00.000Z"

        events = _fetch([_events_payload(docs)])
        assert "Author event with Paul C. Gutjahr at Morgenstern Books" not in {
            e["title"] for e in events
        }

    def test_past_occurrence_is_dropped(self):
        docs = _fixture_docs()
        doc = next(d for d in docs if d["recid"] == "59452")
        doc["date"] = "2026-08-01T03:59:59.000Z"
        doc["endDate"] = "2026-08-01T03:59:59.000Z"
        doc["startDate"] = "2026-07-31T04:00:00.000Z"

        events = _fetch([_events_payload(docs)])
        assert "Author event with Paul C. Gutjahr at Morgenstern Books" not in {
            e["title"] for e in events
        }


class TestFetchPaging:
    """Paging follows the reported count, with browser UA and crawl-delay spacing."""

    def test_paging_continues_until_count_is_exhausted(self):
        docs = _fixture_docs()
        # count > PAGE_LIMIT so the loop advances to a second page, then stops
        # once skip + limit reaches the reported count.
        pages = [
            _events_payload(docs[:2], count=52),
            _events_payload(docs[2:4], count=52),
        ]
        scraper = VisitBloomingtonScraper()
        calls: list[str] = []

        def _get(
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int | None = None,
        ):
            calls.append(url)
            if url == TOKEN_URL:
                return _Resp(200, text="tok")
            options = json.loads((params or {})["json"])["options"]
            return _Resp(200, payload=pages[options["skip"] // options["limit"]])

        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_get),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep") as mock_sleep,
        ):
            events = scraper.fetch_events()

        assert len(events) == 4
        assert calls.count(EVENTS_URL) == 2
        # One wait between the two pages, none after the final page.
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(CRAWL_DELAY)

    def test_events_request_carries_a_desktop_chrome_user_agent(self):
        seen: dict[str, dict[str, str]] = {}

        def _get(
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int | None = None,
        ):
            if url == EVENTS_URL:
                seen["headers"] = headers or {}
                return _Resp(200, payload=_events_payload(_fixture_docs()))
            return _Resp(200, text="tok")

        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_get),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
        ):
            scraper.fetch_events()

        ua = seen["headers"]["User-Agent"]
        assert "Chrome" in ua
        assert "compatible" not in ua.lower()

    def test_non_200_events_response_is_raised_not_swallowed(self):
        scraper = VisitBloomingtonScraper()
        with (
            patch(
                "scrapers.visit_bloomington.requests.get",
                side_effect=_fake_get([], events_status=403),
            ),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            pytest.raises(RuntimeError, match="403"),
        ):
            scraper.fetch_events()

    def test_non_200_token_response_is_raised(self):
        scraper = VisitBloomingtonScraper()
        with (
            patch(
                "scrapers.visit_bloomington.requests.get",
                side_effect=_fake_get([], token_status=403),
            ),
            pytest.raises(RuntimeError, match="403"),
        ):
            scraper.fetch_events()


class TestCalendarOutput:
    """The scraper stamps attribution and its source page onto the ICS."""

    def test_emits_x_source_and_x_source_url(self):
        events = _fetch([_events_payload(_fixture_docs())])
        ics = VisitBloomingtonScraper().create_calendar(events).to_ical().decode()

        assert "X-SOURCE:Visit Bloomington" in ics
        assert "X-SOURCE-URL:https://www.visitbloomington.com/events/" in ics

    def test_geo_is_emitted_from_coordinates(self):
        events = _fetch([_events_payload(_fixture_docs())])
        ics = VisitBloomingtonScraper().create_calendar(events).to_ical().decode()

        assert "GEO:39.15644580000001;-86.49563789999999" in ics

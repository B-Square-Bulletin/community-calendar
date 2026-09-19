#!/usr/bin/env python3
"""Tests for the Visit Bloomington Simpleview REST API scraper (#124).

The HTTP boundary (`requests.get`) is mocked, so these tests drive the real
token/paging/mapping/horizon path against payloads captured from the live API
(tests/fixtures/bloomington/visit_bloomington_events.json).
"""

import copy
import hashlib
import json
import logging
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
from scripts.combine_ics import AGGREGATORS, dedupe_cross_source
from scripts.process_pending_feeds import parse_pending_feeds

TZ = ZoneInfo("America/Indiana/Indianapolis")
BLOOMINGTON_DIR = Path(__file__).parent.parent / "cities" / "bloomington"
FIXTURE = Path(__file__).parent / "fixtures" / "bloomington" / "visit_bloomington_events.json"
# Reconstructed from the aggregate live-run evidence (see the fixture's note).
EVIDENCE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "bloomington"
    / "visit_bloomington_multiday_occurrences.json"
)
# Frozen "now" so the horizon filter is deterministic against the captured payloads.
FROZEN_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=TZ)
RUN_HISTORY_FILE = "visit_bloomington.runs.json"


@pytest.fixture(autouse=True)
def _isolated_run_history(tmp_path, monkeypatch):
    """Keep the degradation guard's on-disk history out of the repo during tests."""
    monkeypatch.setattr(
        "scrapers.visit_bloomington.RUN_HISTORY_PATH",
        tmp_path / RUN_HISTORY_FILE,
    )


def _seed_run_history(tmp_path, fetched_counts: list[int]) -> None:
    runs = [
        {"date": f"2026-08-{i:02d}", "fetched": count, "emitted": count}
        for i, count in enumerate(fetched_counts, start=1)
    ]
    (tmp_path / RUN_HISTORY_FILE).write_text(json.dumps({"runs": runs}))


def _fixture_docs() -> list[dict]:
    return json.loads(FIXTURE.read_text())["docs"]


def _evidence_docs() -> list[dict]:
    return json.loads(EVIDENCE_FIXTURE.read_text())["docs"]


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


def _recurring_doc(
    occurrence_iso: str, recid: str = "58704", title: str = "Downtown Shop Night"
) -> dict:
    """A recurring-series occurrence document (the source emits one per date)."""
    doc = next(d for d in _fixture_docs() if d["recid"] == recid)
    doc = copy.deepcopy(doc)
    doc["title"] = title
    doc["cms_title"] = title
    doc["date"] = occurrence_iso
    doc["dates"] = {"eventDate": occurrence_iso}
    return doc


def _multi_day_doc(
    recid: str, title: str, start_iso: str, end_iso: str, occurrence_iso: str
) -> dict:
    """A multi-day event day-document (recurType 99, no recurrence description)."""
    return {
        "recid": recid,
        "title": title,
        "cms_title": title,
        "recurType": 99,
        "recurrence": None,
        "startDate": start_iso,
        "endDate": end_iso,
        "date": occurrence_iso,
        "dates": {"eventDate": occurrence_iso},
        "description": "<p>A three-day festival.</p>",
        "location": "Brown County Fairgrounds",
        "city": "Nashville",
        "state": "IN",
        "loc": {"type": "Point", "coordinates": [-86.25, 39.2]},
    }


def _located_single_doc(
    recid: str,
    title: str,
    location: str,
    address1: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
) -> dict:
    """A single-day document at an arbitrary address, for the geo prefilter."""
    occurrence_iso = "2026-09-19T15:59:59.000Z"  # local 2026-09-19, in horizon
    return {
        "recid": recid,
        "title": title,
        "cms_title": title,
        "recurType": 0,
        "recurrence": None,
        "startDate": occurrence_iso,
        "endDate": occurrence_iso,
        "date": occurrence_iso,
        "description": "<p>Some event.</p>",
        "location": location,
        "address1": address1,
        "city": city,
        "state": state,
        "zip": zip_code,
    }


class TestSingleEventMapping:
    """fetch_events() maps the API's single (recurType 0) docs to events."""

    def test_returns_one_event_per_single_event_document(self):
        events = _fetch([_events_payload(_fixture_docs())])

        titles = {e["title"] for e in events}
        assert {
            "Author event with Paul C. Gutjahr at Morgenstern Books",
            "IU Football vs Western Kentucky",
            "Resurrection/Kuang ye shi dai | Arthouse Now",
            "Free Riders w/Moxy",
        } <= titles

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


class TestGeoPrefilter:
    """Events outside the city's allowed towns are dropped before the ICS.

    The scrape-time prefilter reuses the authoritative combine-time allowlist
    (cities/bloomington/city.conf via combine_ics), so it is an optimization
    over the same scope, not a Bloomington-only bound.
    """

    def test_event_outside_the_allowed_towns_is_dropped(self):
        docs = [
            _located_single_doc(
                "80001",
                "Indy Home Show",
                "Indiana Convention Center",
                "100 S Capitol Ave",
                "Indianapolis",
                "IN",
                "46204",
            )
        ]
        titles = {e["title"] for e in _fetch([_events_payload(docs)])}

        assert "Indy Home Show" not in titles

    def test_zip_only_in_area_address_is_kept(self):
        # Sleeper's Bar: Bloomington ZIP, no town name in the address (#127).
        docs = [
            _located_single_doc(
                "80004",
                "Live Music at Sleeper's",
                "Sleeper's Bar",
                "2601 N Walnut St",
                None,
                "IN",
                "47404",
            )
        ]
        titles = {e["title"] for e in _fetch([_events_payload(docs)])}

        assert "Live Music at Sleeper's" in titles

    def test_zip_only_surrounding_town_address_is_kept(self):
        # McGlocklin Park: Stinesville ZIP, an allowed town (#127).
        docs = [
            _located_single_doc(
                "80005",
                "McGlocklin Park Cleanup",
                "McGlocklin Park",
                "Market Street",
                None,
                "IN",
                "47464",
            )
        ]
        titles = {e["title"] for e in _fetch([_events_payload(docs)])}

        assert "McGlocklin Park Cleanup" in titles

    def test_in_scope_surrounding_town_is_kept(self):
        docs = [
            _located_single_doc(
                "80002",
                "Brown County Jamboree",
                "Brown County Music Center",
                "114 E Gould St",
                "Nashville",
                "IN",
                "47448",
            )
        ]
        titles = {e["title"] for e in _fetch([_events_payload(docs)])}

        assert "Brown County Jamboree" in titles

    def test_venue_only_location_is_kept(self):
        # No address indicator: nothing to geo-filter on, so it passes through
        # exactly as the combine-time filter would allow it.
        docs = [
            _located_single_doc("80003", "Trivia Night", "The Bluebird", None, None, None, None)
        ]
        titles = {e["title"] for e in _fetch([_events_payload(docs)])}

        assert "Trivia Night" in titles


class TestRecurringExpansion:
    """The source pre-expands a recurring series into one document per occurrence."""

    def test_weekly_series_yields_one_event_per_occurrence(self):
        docs = [
            _recurring_doc("2026-09-17T03:59:59.000Z"),  # local 2026-09-16
            _recurring_doc("2026-09-24T03:59:59.000Z"),  # local 2026-09-23
        ]
        starts = sorted(
            e["dtstart"]
            for e in _fetch([_events_payload(docs)])
            if e["title"] == "Downtown Shop Night"
        )

        assert starts == [
            datetime(2026, 9, 16, 16, 0, tzinfo=TZ),
            datetime(2026, 9, 23, 16, 0, tzinfo=TZ),
        ]

    def test_occurrence_outside_the_horizon_is_dropped(self):
        docs = [
            _recurring_doc("2026-09-17T03:59:59.000Z"),
            _recurring_doc("2027-06-24T03:59:59.000Z"),  # beyond the horizon
        ]
        starts = [
            e["dtstart"]
            for e in _fetch([_events_payload(docs)])
            if e["title"] == "Downtown Shop Night"
        ]

        assert starts == [datetime(2026, 9, 16, 16, 0, tzinfo=TZ)]

    def test_occurrences_of_a_series_have_distinct_uids(self):
        docs = [
            _recurring_doc("2026-09-17T03:59:59.000Z"),
            _recurring_doc("2026-09-24T03:59:59.000Z"),
        ]
        uids = [
            e["uid"] for e in _fetch([_events_payload(docs)]) if e["title"] == "Downtown Shop Night"
        ]

        assert len(uids) == 2
        assert len(set(uids)) == 2

    def test_editing_the_title_does_not_change_an_occurrence_uid(self):
        before = _by_title(
            _fetch([_events_payload([_recurring_doc("2026-09-17T03:59:59.000Z")])]),
            "Downtown Shop Night",
        )["uid"]

        renamed = _recurring_doc("2026-09-17T03:59:59.000Z", title="Renamed Shop Night")
        event = _by_title(_fetch([_events_payload([renamed])]), "Renamed Shop Night")

        assert event["uid"] == before


class TestMultiDayEvents:
    """A genuinely multi-day event stays one span with an exclusive end date."""

    def test_multi_day_event_emits_one_span_with_exclusive_end_date(self):
        # Fri 2026-09-18 00:00 local .. Sun 2026-09-20 23:59 local.
        docs = [
            _multi_day_doc(
                "70001",
                "Brown County Music Festival",
                "2026-09-18T04:00:00.000Z",
                "2026-09-21T03:59:59.000Z",
                "2026-09-19T03:59:59.000Z",
            )
        ]
        events = _fetch([_events_payload(docs)])

        assert len(events) == 1
        assert events[0]["dtstart"] == date(2026, 9, 18)
        assert events[0]["dtend"] == date(2026, 9, 21)  # exclusive

    def test_day_documents_of_one_span_collapse_to_a_single_event(self):
        span = ("2026-09-18T04:00:00.000Z", "2026-09-21T03:59:59.000Z")
        docs = [
            _multi_day_doc(
                "70001", "Brown County Music Festival", *span, "2026-09-19T03:59:59.000Z"
            ),
            _multi_day_doc(
                "70001", "Brown County Music Festival", *span, "2026-09-20T03:59:59.000Z"
            ),
        ]

        assert len(_fetch([_events_payload(docs)])) == 1


class TestLiveRunEvidence:
    """Shapes the aggregate live run observed but the captured page did not.

    The fixture is reconstructed (not a byte capture) from prd item 4's
    2026-09-16 live-run note: a wide multi-day span emitted as multiple
    per-day documents, and a recurring series emitted as multiple occurrences.
    """

    def test_multiday_span_documents_collapse_to_one_event(self):
        events = _fetch([_events_payload(_evidence_docs())])
        heist = [e for e in events if e["title"] == "Heist"]

        assert len(heist) == 1
        assert heist[0]["dtstart"] == date(2026, 9, 3)
        assert heist[0]["dtend"] == date(2026, 9, 22)  # exclusive

    def test_recurring_series_yields_one_event_per_occurrence(self):
        starts = sorted(
            e["dtstart"]
            for e in _fetch([_events_payload(_evidence_docs())])
            if e["title"] == "Downtown Shop Night"
        )

        assert starts == [
            datetime(2026, 9, 16, 16, 0, tzinfo=TZ),
            datetime(2026, 10, 21, 16, 0, tzinfo=TZ),
        ]


class TestFetchPaging:
    """Paging follows the reported count, with browser UA and crawl-delay spacing."""

    def test_paging_continues_until_count_is_exhausted(self):
        docs = _fixture_docs()
        # The first page holds fewer docs than the reported count, so the loop
        # advances to a second page and stops once the count is received.
        pages = [
            _events_payload(docs[:2], count=4),
            _events_payload(docs[2:4], count=4),
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
        # One wait before the first page and one between the two pages.
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(CRAWL_DELAY)

    def test_empty_page_before_count_is_exhausted_raises(self):
        # A page that returns nothing while the source still reports
        # occurrences is an API failure, not a finished pull: the partial
        # inventory must not be reported as a successful run.
        docs = _fixture_docs()
        pages = [
            _events_payload(docs[:2], count=52),
            _events_payload([], count=52),
        ]
        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_fake_get(pages)),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep"),
            pytest.raises(RuntimeError, match="empty page"),
        ):
            scraper.fetch_events()

    def test_page_without_a_reported_count_does_not_complete(self):
        # `count` is requested explicitly. A page that omits it cannot prove
        # the inventory is exhausted, so it must not return a partial pull as
        # a successful run.
        docs = _fixture_docs()
        pages = [{"docs": {"docs": docs}}]
        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_fake_get(pages)),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep"),
            pytest.raises(RuntimeError, match="count"),
        ):
            scraper.fetch_events()

    def test_pagination_beyond_max_pages_raises(self, monkeypatch):
        # MAX_PAGES is a runaway guard, not a truncation point: hitting it
        # while `count` still reports occurrences must fail loudly rather
        # than return the capped prefix as a complete inventory.
        monkeypatch.setattr("scrapers.visit_bloomington.MAX_PAGES", 2)
        docs = _fixture_docs()
        pages = [
            _events_payload(docs, count=1000),
            _events_payload(docs, count=1000),
        ]
        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_fake_get(pages)),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep"),
            pytest.raises(RuntimeError, match="MAX_PAGES"),
        ):
            scraper.fetch_events()

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


class TestRequestSpacing:
    """Every request to the host is separated by the source's Crawl-delay."""

    def test_crawl_delay_precedes_the_first_events_request(self):
        order: list[object] = []

        def _get(
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int | None = None,
        ):
            order.append(url)
            if url == TOKEN_URL:
                return _Resp(200, text="tok")
            return _Resp(200, payload=_events_payload(_fixture_docs()))

        def _sleep(seconds: float) -> None:
            order.append(("sleep", seconds))

        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_get),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep", side_effect=_sleep),
        ):
            scraper.fetch_events()

        assert order == [TOKEN_URL, ("sleep", CRAWL_DELAY), EVENTS_URL]

    def test_crawl_delay_precedes_the_retried_events_request(self):
        order: list[object] = []
        events_calls = {"n": 0}

        def _get(
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int | None = None,
        ):
            order.append(url)
            if url == TOKEN_URL:
                return _Resp(200, text="tok")
            events_calls["n"] += 1
            if events_calls["n"] == 1:
                return _Resp(403)
            return _Resp(200, payload=_events_payload(_fixture_docs()))

        def _sleep(seconds: float) -> None:
            order.append(("sleep", seconds))

        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_get),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep", side_effect=_sleep),
        ):
            scraper.fetch_events()

        # The re-fetched token is itself a request, so the retried page is
        # spaced from it as well as from the 403 it followed.
        assert order == [
            TOKEN_URL,
            ("sleep", CRAWL_DELAY),
            EVENTS_URL,
            ("sleep", CRAWL_DELAY),
            TOKEN_URL,
            ("sleep", CRAWL_DELAY),
            EVENTS_URL,
        ]


class TestFetchRetry:
    """A 403 burst re-fetches the token and retries the request once."""

    def test_403_triggers_token_refetch_and_one_successful_retry(self):
        docs = _fixture_docs()
        token_calls: list[str] = []
        events_calls = {"n": 0}

        def _get(
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int | None = None,
        ):
            if url == TOKEN_URL:
                token_calls.append(url)
                return _Resp(200, text="tok")
            assert url == EVENTS_URL
            events_calls["n"] += 1
            if events_calls["n"] == 1:
                return _Resp(403)
            return _Resp(200, payload=_events_payload(docs))

        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_get),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep") as mock_sleep,
        ):
            events = scraper.fetch_events()

        # The successful retry is not treated as a failure: the whole page is mapped.
        assert len(events) == 5
        assert len(token_calls) == 2  # initial token + one re-fetch
        assert events_calls["n"] == 2  # initial request + one retry
        mock_sleep.assert_any_call(CRAWL_DELAY)

    def test_repeated_403_raises_after_a_single_retry(self):
        token_calls: list[str] = []
        events_calls = {"n": 0}

        def _get(
            url: str,
            headers: dict[str, str] | None = None,
            params: dict[str, str] | None = None,
            timeout: int | None = None,
        ):
            if url == TOKEN_URL:
                token_calls.append(url)
                return _Resp(200, text="tok")
            events_calls["n"] += 1
            return _Resp(403)

        scraper = VisitBloomingtonScraper()
        with (
            patch("scrapers.visit_bloomington.requests.get", side_effect=_get),
            patch("scrapers.visit_bloomington._now", return_value=FROZEN_NOW),
            patch("scrapers.visit_bloomington.time.sleep"),
            pytest.raises(RuntimeError, match="403"),
        ):
            scraper.fetch_events()

        # Only one re-fetch and one retry, then the failure surfaces.
        assert len(token_calls) == 2
        assert events_calls["n"] == 2


class TestInstanceState:
    """The token-refresh guard lives on the instance, not as shared class state."""

    def test_token_refresh_flag_is_not_shared_class_state(self, monkeypatch):
        # A class-level mutable default can leak across instances. Simulate a
        # poisoned class default: a freshly constructed scraper must still start
        # with its own per-run guard, independent of the class attribute.
        monkeypatch.setattr(VisitBloomingtonScraper, "_token_refreshed", True, raising=False)

        assert VisitBloomingtonScraper()._token_refreshed is False


class TestDegradationGuard:
    """A fetch far below the trailing 7-run median warns rather than hiding."""

    def test_fetch_below_half_trailing_median_warns(self, tmp_path, caplog):
        _seed_run_history(tmp_path, [1000] * 7)

        with caplog.at_level(logging.WARNING):
            _fetch([_events_payload(_fixture_docs())])

        assert any(
            "median" in r.getMessage() and "50%" in r.getMessage() for r in caplog.records
        ), caplog.text

    def test_fetch_at_or_above_half_trailing_median_does_not_warn(self, tmp_path, caplog):
        _seed_run_history(tmp_path, [8] * 7)

        with caplog.at_level(logging.WARNING):
            _fetch([_events_payload(_fixture_docs())])

        # 5 occurrences is above half of the 8 median, so no warning.
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_first_run_records_history_without_warning(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING):
            _fetch([_events_payload(_fixture_docs())])

        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        recorded = json.loads((tmp_path / RUN_HISTORY_FILE).read_text())["runs"]
        assert len(recorded) == 1
        assert recorded[0]["fetched"] == 5
        assert recorded[0]["emitted"] >= 1


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


def _registered_bloomington_entries() -> list[dict]:
    """Parse the city's pending and active source inventories."""
    entries: list[dict] = []
    for name in ("pending_feeds.txt", "feeds.txt"):
        entries.extend(parse_pending_feeds(BLOOMINGTON_DIR / name))
    return entries


def _dedupe_event(title: str, source: str) -> dict:
    """An event dict as combine_ics.dedupe_cross_source consumes it."""
    content = (
        f"SUMMARY:{title}\r\n"
        f"X-SOURCE:{source}\r\n"
        f"URL:https://example.com/{source.replace(' ', '-')}\r\n"
        "UID:shared-uid"
    )
    return {"dtstart": datetime(2026, 9, 16, 18, 0, tzinfo=TZ), "content": content}


class TestRegistrationContract:
    """The #124 registration: DB-first entry, primary-source dedup (ADR 0011)."""

    def test_registers_visit_bloomington_through_the_db_first_path(self):
        # The entry must satisfy the feeds-table insert-time trigger that the
        # nightly pending-feeds processor and DB-first runner execute against.
        entry = next(
            (
                e
                for e in _registered_bloomington_entries()
                if e["name"] == "Visit Bloomington" and e["feed_type"] == "scraper"
            ),
            None,
        )
        assert entry is not None, "Visit Bloomington is not registered for Bloomington"
        assert entry["url"] == "cities/bloomington/visit_bloomington.ics"
        assert entry["scraper_cmd"].startswith("python scrapers/")
        assert "scrapers/visit_bloomington.py" in entry["scraper_cmd"]

    def test_source_is_a_primary_not_an_aggregator(self):
        # ADR 0011: absent from the aggregator list -> wins cross-source dedup.
        assert "Visit Bloomington" not in AGGREGATORS

    def test_dedupe_prefers_visit_bloomington_and_dual_credits_limestone_post(self):
        # Limestone Post's CitySpark feed echoes CVB events; the CVB copy is
        # kept and the merged attribution lists the primary source first.
        limestone = _dedupe_event("Downtown Shop Night", "Limestone Post")
        visit = _dedupe_event("Downtown Shop Night", "Visit Bloomington")

        kept = dedupe_cross_source([limestone, visit], input_dir=None)

        assert len(kept) == 1
        assert "X-SOURCE:Visit Bloomington, Limestone Post" in kept[0]["content"]

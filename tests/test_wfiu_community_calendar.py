#!/usr/bin/env python3
"""Tests for the WFIU Community Calendar scraper (#140, listing tracer bullet).

The HTTP boundary is the module-level `_fetch_html(url)` seam: the tests patch it
with fixtures keyed by URL, so listing paging and the card/time mapping run
end-to-end without touching the live site. The clock (`_now`) is frozen and
`time.sleep` is patched, so the Horizon window is deterministic.
"""

import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.wfiu_community_calendar import (
    CRAWL_DELAY,
    PAGE_CAP,
    WFIUCommunityCalendarScraper,
)
from scripts.combine_ics import AGGREGATORS, dedupe_cross_source
from scripts.process_pending_feeds import parse_pending_feeds

TZ = ZoneInfo("America/Indiana/Indianapolis")
BLOOMINGTON_DIR = Path(__file__).parent.parent / "cities" / "bloomington"
FIXTURES = Path(__file__).parent / "fixtures" / "bloomington"

# Frozen "now" so the Horizon window is deterministic against the captured pages.
# 3 months ahead -> Horizon 2026-12-15 (see BaseScraper.horizon_cutoff).
FROZEN_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=TZ)
MONTHS_AHEAD = 3
RUN_HISTORY_FILE = "wfiu_community_calendar.runs.json"

HEIST_SLUG = "heist-24-08-2026-10-32-57"
UKULELE_SLUG = "adult-ukulele-class-04-08-2026-11-29-41"
METZ_SLUG = "meet-me-at-the-metz-carillon-series-01-09-2026-09-00-00"

DETAIL_FILES = {
    HEIST_SLUG: "wfiu_detail_heist.html",
    UKULELE_SLUG: "wfiu_detail_ukulele.html",
    METZ_SLUG: "wfiu_detail_metz.html",
}


@pytest.fixture(autouse=True)
def _isolated_run_history(tmp_path, monkeypatch):
    """Keep the degradation guard's on-disk history out of the repo during tests."""
    monkeypatch.setattr(
        "scrapers.wfiu_community_calendar.RUN_HISTORY_PATH",
        tmp_path / RUN_HISTORY_FILE,
    )


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _expected_f1(now: datetime = FROZEN_NOW, months: int = MONTHS_AHEAD) -> str:
    start = datetime.combine(now.date(), datetime.min.time(), tzinfo=TZ)
    end = now + timedelta(days=months * 31)
    return f"{int(start.timestamp() * 1000)}-{int(end.timestamp() * 1000)}"


class _Site:
    """A patched `_fetch_html` returning fixtures and recording the URLs."""

    def __init__(
        self,
        pages: list[str] | None = None,
        details: dict[str, str] | None = None,
    ):
        self.pages = (
            pages
            if pages is not None
            else [
                _fixture("wfiu_listing_page1.html"),
                _fixture("wfiu_listing_page2.html"),
            ]
        )
        self.details = details if details is not None else DETAIL_FILES
        self.calls: list[str] = []

    def fetch(self, url: str) -> str:
        self.calls.append(url)
        path = urlparse(url).path
        if "/event/" in path:
            slug = path.rsplit("/", 1)[1]
            return _fixture(self.details[slug])
        page = int(parse_qs(urlparse(url).query)["p"][0])
        return self.pages[page - 1]


def _run(site: _Site | None = None, now: datetime = FROZEN_NOW, months: int = MONTHS_AHEAD):
    site = site or _Site()
    scraper = WFIUCommunityCalendarScraper()
    scraper.months_ahead = months
    with (
        patch("scrapers.wfiu_community_calendar._fetch_html", side_effect=site.fetch),
        patch("scrapers.wfiu_community_calendar._now", return_value=now),
        patch("scrapers.wfiu_community_calendar.time.sleep"),
    ):
        events = scraper.fetch_events()
    return events, site.calls


def _by_title(events: list[dict], title: str) -> dict:
    return next(e for e in events if e["title"] == title)


def _listing_html(*cards: str, page_counts: str | None = "1 of 1") -> str:
    counts = (
        f'<div class="EventSearchResultsModule-pageCounts">{page_counts}</div>'
        if page_counts
        else ""
    )
    return "".join(cards) + f'<div class="EventSearchResultsModule-pagination">{counts}</div>'


def _card(
    title: str,
    *,
    slug: str = HEIST_SLUG,
    display_date: str = "Sep 18",
    weekday: str = "Friday",
    time_raw: str = "09:00 AM - 10:00 PM on Fri, 18 Sep 2026",
) -> str:
    return f"""
<ps-promo class="PromoEvent" data-no-media="">
 <div class="PromoEvent-link" data-href="https://www.ipm.org/community-calendar/event/{slug}">
  <a class="PromoEvent-link-link" href="https://www.ipm.org/community-calendar/event/{slug}">
   <div class="PromoEvent-date"><p class="PromoEvent-date-date">{display_date}
    <span class="PromoEvent-date-day">{weekday}</span></p></div>
  </a>
  <div class="PromoEvent-content">
   <h3 class="PromoEvent-title"><a class="Link" href="https://www.ipm.org/community-calendar/event/{slug}">{title}</a></h3>
   <div class="PromoEvent-venue PromoEvent-content-item">Somewhere</div>
   <div class="PromoEvent-time PromoEvent-content-item">{time_raw}</div>
  </div>
 </div>
</ps-promo>
"""


class TestListingWalk:
    """fetch_events() walks the date-filtered listing and emits one event per card."""

    def test_emits_one_event_per_occurrence_card(self):
        events, _ = _run()

        assert len(events) == 3
        assert {e["title"] for e in events} == {
            "Heist",
            "Adult Ukulele Class",
            "Meet Me at the Metz Carillon Series",
        }

    def test_event_carries_title_start_end_url_and_venue(self):
        events, _ = _run()
        event = _by_title(events, "Heist")

        assert event["dtstart"] == datetime(2026, 9, 18, 9, 0, tzinfo=TZ)
        assert event["dtend"] == datetime(2026, 9, 18, 22, 0, tzinfo=TZ)
        assert event["url"] == (
            "https://www.ipm.org/community-calendar/event/heist-24-08-2026-10-32-57"
        )
        assert "Waldron Auditorium" in event["location"]

    def test_pagination_fetches_every_reported_page(self):
        _, calls = _run()

        listing_calls = [url for url in calls if "/event/" not in url]
        assert len(listing_calls) == 2
        assert [parse_qs(urlparse(url).query)["p"][0] for url in listing_calls] == ["1", "2"]

    def test_listing_fetch_carries_the_horizon_date_filter(self):
        _, calls = _run()

        first = parse_qs(urlparse(calls[0]).query)
        assert first["f1"] == [_expected_f1()]

    def test_page_count_above_the_cap_raises_loud(self):
        site = _Site(pages=[_listing_html(_card("Heist"), page_counts=f"1 of {PAGE_CAP + 1}")])

        with pytest.raises(RuntimeError, match="page cap"):
            _run(site)

    def test_missing_page_count_raises_loud(self):
        site = _Site(pages=[_listing_html(_card("Heist"), page_counts=None)])

        with pytest.raises(RuntimeError, match="page count"):
            _run(site)

    def test_detail_urls_are_fetched_once_per_unique_event(self):
        _, calls = _run()

        detail_calls = [url for url in calls if "/event/" in url]
        assert len(detail_calls) == 3
        assert len(set(detail_calls)) == 3

    def test_detail_cap_is_a_loud_ceiling(self, monkeypatch):
        monkeypatch.setattr("scrapers.wfiu_community_calendar.DETAIL_CAP", 1)

        with pytest.raises(RuntimeError, match="detail"):
            _run()

    def test_crawl_delay_spaces_requests(self):
        scraper = WFIUCommunityCalendarScraper()
        scraper.months_ahead = MONTHS_AHEAD
        site = _Site()
        with (
            patch("scrapers.wfiu_community_calendar._fetch_html", side_effect=site.fetch),
            patch("scrapers.wfiu_community_calendar._now", return_value=FROZEN_NOW),
            patch("scrapers.wfiu_community_calendar.time.sleep") as mock_sleep,
        ):
            scraper.fetch_events()

        mock_sleep.assert_any_call(CRAWL_DELAY)


class TestTimeBlocks:
    """The card's time text drives timed vs all-day and the clock times."""

    def test_daily_block_keeps_clock_times(self):
        events, _ = _run()
        event = _by_title(events, "Heist")

        assert isinstance(event["dtstart"], datetime)
        assert event["dtstart"].hour == 9

    def test_weekly_block_uses_the_card_weekday_time(self):
        events, _ = _run()
        event = _by_title(events, "Adult Ukulele Class")

        assert event["dtstart"] == datetime(2026, 9, 18, 17, 30, tzinfo=TZ)
        assert event["dtend"] == datetime(2026, 9, 18, 18, 30, tzinfo=TZ)

    def test_one_off_block_keeps_clock_times(self):
        events, _ = _run()
        event = _by_title(events, "Meet Me at the Metz Carillon Series")

        assert event["dtstart"] == datetime(2026, 9, 19, 19, 30, tzinfo=TZ)
        assert event["dtend"] == datetime(2026, 9, 19, 21, 30, tzinfo=TZ)

    def test_block_without_a_parseable_time_is_all_day(self):
        site = _Site(
            pages=[
                _listing_html(
                    _card("Mystery Event", time_raw="Doors open at dusk"),
                )
            ]
        )
        events, _ = _run(site)

        event = events[0]
        assert event["dtstart"] == date(2026, 9, 18)
        assert event["dtend"] == date(2026, 9, 19)


class TestTimeAndIdentity:
    """Clock-time hardening and per-occurrence identity (#141).

    These are regression guards for the visitor-facing contract: a parseable
    time is never silently coerced to all-day, a start-only time gets a sane
    duration, and two showings of the same work on one date stay distinct.
    """

    def test_start_only_time_becomes_a_one_hour_event(self):
        site = _Site(pages=[_listing_html(_card("Doors", time_raw="07:30 PM"))])

        events, _ = _run(site)

        assert events[0]["dtstart"] == datetime(2026, 9, 18, 19, 30, tzinfo=TZ)
        assert events[0]["dtend"] == datetime(2026, 9, 18, 20, 30, tzinfo=TZ)

    def test_zero_duration_block_becomes_a_one_hour_event(self):
        site = _Site(pages=[_listing_html(_card("Marker", time_raw="09:00 AM - 09:00 AM"))])

        events, _ = _run(site)

        assert events[0]["dtend"] - events[0]["dtstart"] == timedelta(hours=1)

    def test_late_ending_rolls_past_midnight_and_stays_timed(self):
        site = _Site(pages=[_listing_html(_card("Late", time_raw="10:00 PM - 01:00 AM"))])

        events, _ = _run(site)

        assert events[0]["dtstart"] == datetime(2026, 9, 18, 22, 0, tzinfo=TZ)
        assert events[0]["dtend"] == datetime(2026, 9, 19, 1, 0, tzinfo=TZ)

    def test_multi_day_run_emits_one_timed_event_with_no_span(self):
        # The Heist card reads "every day through Sep 20, 2026" but the listing
        # already expands occurrences, so this card is only its own day.
        events, _ = _run()
        heist = [e for e in events if e["title"] == "Heist"]

        assert len(heist) == 1
        assert heist[0]["dtstart"] == datetime(2026, 9, 18, 9, 0, tzinfo=TZ)
        assert heist[0]["dtend"] == datetime(2026, 9, 18, 22, 0, tzinfo=TZ)

    def test_yearless_date_binds_to_the_in_horizon_year(self):
        site = _Site(
            pages=[_listing_html(_card("Winter", display_date="Dec 10", weekday="Thursday"))]
        )

        events, _ = _run(site)

        assert events[0]["dtstart"] == datetime(2026, 12, 10, 9, 0, tzinfo=TZ)

    def test_yearless_date_resolves_the_year_end_rollover(self):
        now = datetime(2026, 12, 20, 9, 0, tzinfo=TZ)
        site = _Site(
            pages=[_listing_html(_card("New Year", display_date="Jan 5", weekday="Tuesday"))]
        )

        events, _ = _run(site, now=now)

        assert events[0]["dtstart"] == datetime(2027, 1, 5, 9, 0, tzinfo=TZ)

    def test_weekday_disagreement_falls_back_with_a_warning(self, caplog):
        # Dec 10 2026 is a Thursday; the card says Monday, so binding must
        # still land in-window but announce the mismatch.
        site = _Site(pages=[_listing_html(_card("Odd", display_date="Dec 10", weekday="Monday"))])

        with caplog.at_level("WARNING"):
            events, _ = _run(site)

        assert events[0]["dtstart"] == datetime(2026, 12, 10, 9, 0, tzinfo=TZ)
        assert any("weekday" in r.getMessage().lower() for r in caplog.records)

    def test_unparseable_dates_raise_after_a_small_threshold(self):
        bad = [_card(f"Bad {i}", display_date="Sep 1", weekday="Tuesday") for i in range(4)]
        site = _Site(pages=[_listing_html(*bad)])

        with pytest.raises(RuntimeError, match="date"):
            _run(site)

    def test_dates_below_the_threshold_degrade_without_raising(self):
        bad = [_card(f"Bad {i}", display_date="Sep 1", weekday="Tuesday") for i in range(3)]
        site = _Site(pages=[_listing_html(*bad)])

        events, _ = _run(site)

        assert events == []

    def test_same_day_repeat_showings_get_distinct_uids(self):
        matinee = _card("Movie", time_raw="02:00 PM - 04:00 PM")
        evening = _card("Movie", time_raw="07:00 PM - 09:00 PM")
        site = _Site(pages=[_listing_html(matinee, evening)])

        events, _ = _run(site)

        assert len(events) == 2
        assert len({e["uid"] for e in events}) == 2

    def test_duplicate_cards_collapse_to_one_event(self):
        card = _card("Movie", time_raw="02:00 PM - 04:00 PM")
        site = _Site(pages=[_listing_html(card, card)])

        events, _ = _run(site)

        assert len(events) == 1


class TestHorizonGuard:
    """Every emitted occurrence passes the shared Horizon predicate."""

    def test_occurrence_beyond_the_horizon_is_dropped(self):
        beyond = _listing_html(_card("Far Away Event", display_date="Dec 20", weekday="Sunday"))
        events, _ = _run(_Site(pages=[beyond]))

        assert events == []

    def test_past_occurrence_is_dropped(self):
        past = _listing_html(_card("Gone Event", display_date="Sep 1", weekday="Tuesday"))
        events, _ = _run(_Site(pages=[past]))

        assert events == []


class TestRunHistory:
    """Each run records its fetch/emit counts and warns on a collapsed card count."""

    def test_records_pages_cards_details_and_emitted(self, tmp_path):
        _run()

        runs = json.loads((tmp_path / RUN_HISTORY_FILE).read_text())["runs"]
        assert len(runs) == 1
        assert runs[0]["pages"] == 2
        assert runs[0]["cards_fetched"] == 3
        assert runs[0]["unique_detail_urls"] == 3
        assert runs[0]["details_fetched"] == 3
        assert runs[0]["emitted"] == 3

    def test_cards_below_half_the_trailing_median_warn(self, tmp_path, caplog):
        runs = [
            {"date": f"2026-08-{i:02d}", "cards_fetched": 100, "emitted": 100} for i in range(1, 8)
        ]
        (tmp_path / RUN_HISTORY_FILE).write_text(json.dumps({"runs": runs}))

        with caplog.at_level("WARNING"):
            _run()

        assert any("median" in r.getMessage() and "50%" in r.getMessage() for r in caplog.records)

    def test_cards_at_or_above_half_the_trailing_median_do_not_warn(self, tmp_path, caplog):
        runs = [{"date": f"2026-08-{i:02d}", "cards_fetched": 4, "emitted": 4} for i in range(1, 8)]
        (tmp_path / RUN_HISTORY_FILE).write_text(json.dumps({"runs": runs}))

        with caplog.at_level("WARNING"):
            _run()

        assert not [r for r in caplog.records if r.levelno >= 30]


class TestCalendarOutput:
    """The scraper stamps attribution and its source page onto the ICS."""

    def test_emits_x_source_and_x_source_url(self):
        events, _ = _run()
        ics = WFIUCommunityCalendarScraper().create_calendar(events).to_ical().decode()

        assert "X-SOURCE:WFIU Community Calendar" in ics
        assert "X-SOURCE-URL:https://www.ipm.org/community-calendar/" in ics

    def test_uid_keys_on_content_id_date_and_time_block(self):
        events, _ = _run()
        event = _by_title(events, "Heist")

        expected = hashlib.md5(
            b"000001a0-3430-d25b-a9ea-3e3853560000-2026-09-18-0900-2200"
        ).hexdigest()
        assert event["uid"] == f"{expected}@ipm.org"


def _registered_bloomington_entries() -> list[dict]:
    entries: list[dict] = []
    for name in ("pending_feeds.txt", "feeds.txt"):
        entries.extend(parse_pending_feeds(BLOOMINGTON_DIR / name))
    return entries


def _dedupe_event(title: str, source: str) -> dict:
    content = (
        f"SUMMARY:{title}\r\n"
        f"X-SOURCE:{source}\r\n"
        f"URL:https://example.com/{source.replace(' ', '-')}\r\n"
        "UID:shared-uid"
    )
    return {"dtstart": datetime(2026, 9, 18, 9, 0, tzinfo=TZ), "content": content}


class TestRegistrationContract:
    """The #140 registration shape: DB-first entry, aggregator dedup (ADR 0011)."""

    def test_scraper_identity_matches_the_spec(self):
        assert WFIUCommunityCalendarScraper.name == "WFIU Community Calendar"
        assert WFIUCommunityCalendarScraper.domain == "ipm.org"
        assert WFIUCommunityCalendarScraper.timezone == "America/Indiana/Indianapolis"

    def test_registered_entry_satisfies_the_feeds_table_trigger(self):
        # The entry must satisfy the feeds-table insert-time trigger that the
        # nightly pending-feeds processor and DB-first runner execute against.
        entry = next(
            (
                e
                for e in _registered_bloomington_entries()
                if e["name"] == "WFIU Community Calendar" and e["feed_type"] == "scraper"
            ),
            None,
        )
        assert entry is not None, "WFIU Community Calendar is not registered for Bloomington"
        cmd = entry["scraper_cmd"] or ""
        assert entry["url"] == "cities/bloomington/wfiu_community_calendar.ics"
        assert cmd.startswith("python scrapers/")
        assert "scrapers/wfiu_community_calendar.py" in cmd

    def test_source_is_an_aggregator(self):
        assert "WFIU Community Calendar" in AGGREGATORS

    def test_dedupe_prefers_visit_bloomington_over_wfiu(self):
        wfiu = _dedupe_event("Heist", "WFIU Community Calendar")
        visit = _dedupe_event("Heist", "Visit Bloomington")

        kept = dedupe_cross_source([wfiu, visit], input_dir=None)

        assert len(kept) == 1
        assert "X-SOURCE:Visit Bloomington, WFIU Community Calendar" in kept[0]["content"]

    def test_dedupe_merges_fellow_aggregators_alphabetically(self):
        wfiu = _dedupe_event("Heist", "WFIU Community Calendar")
        limestone = _dedupe_event("Heist", "Limestone Post")

        kept = dedupe_cross_source([wfiu, limestone], input_dir=None)

        assert len(kept) == 1
        assert "X-SOURCE:Limestone Post, WFIU Community Calendar" in kept[0]["content"]

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
from scripts.combine_ics import (
    AGGREGATORS,
    _url_predates_window,
    extract_events,
)
from scripts.process_pending_feeds import parse_pending_feeds

TZ = ZoneInfo("America/Indiana/Indianapolis")
BLOOMINGTON_DIR = Path(__file__).parent.parent / "cities" / "bloomington"
FIXTURES = Path(__file__).parent / "fixtures" / "bloomington"

# Frozen "now" so the Horizon window is deterministic against the captured pages.
# 3 months ahead -> Horizon 2026-12-17 (see BaseScraper.horizon_cutoff).
FROZEN_NOW = datetime(2026, 9, 15, 9, 0, tzinfo=TZ)
MONTHS_AHEAD = 3
RUN_HISTORY_FILE = "wfiu_community_calendar.runs.json"

HEIST_SLUG = "heist-24-08-2026-10-32-57"
UKULELE_SLUG = "adult-ukulele-class-04-08-2026-11-29-41"
METZ_SLUG = "meet-me-at-the-metz-carillon-series-01-09-2026-09-00-00"
NO_ZIP_SLUG = "no-zip-concert-01-09-2026-09-00-00"

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
        fail: set[str] | None = None,
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
        self.fail = fail or set()
        self.calls: list[str] = []

    def fetch(self, url: str) -> str:
        self.calls.append(url)
        path = urlparse(url).path
        if "/event/" in path:
            slug = path.rsplit("/", 1)[1]
            if slug in self.fail:
                raise RuntimeError(f"simulated detail failure for {url}")
            return _fixture(self.details[slug])
        page = int(parse_qs(urlparse(url).query)["p"][0])
        return self.pages[page - 1]


class _RepeatingSite(_Site):
    """A site that returns page 1's body for every listing request."""

    def __init__(self):
        self.pages = [_listing_html(_card("Heist"), page_counts="1 of 2")]
        self.details = DETAIL_FILES
        self.fail = set()
        self.calls: list[str] = []

    def fetch(self, url: str) -> str:
        self.calls.append(url)
        if "/event/" in urlparse(url).path:
            return _fixture(self.details[HEIST_SLUG])
        return self.pages[0]


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
    href_prefix: str = "https://www.ipm.org",
) -> str:
    href = f"{href_prefix}/community-calendar/event/{slug}"
    return f"""
<ps-promo class="PromoEvent" data-no-media="">
 <div class="PromoEvent-link" data-href="{href}">
  <a class="PromoEvent-link-link" href="{href}">
   <div class="PromoEvent-date"><p class="PromoEvent-date-date">{display_date}
    <span class="PromoEvent-date-day">{weekday}</span></p></div>
  </a>
  <div class="PromoEvent-content">
   <h3 class="PromoEvent-title"><a class="Link" href="{href}">{title}</a></h3>
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

    def test_repeated_listing_page_raises_loud(self):
        """A page that ignores the requested number must fail, not double-count."""
        site = _RepeatingSite()

        with pytest.raises(RuntimeError, match="page 2"):
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

    def test_crawl_delay_precedes_the_first_detail_fetch(self):
        """The listing-to-detail transition must be spaced like every other gap."""
        scraper = WFIUCommunityCalendarScraper()
        scraper.months_ahead = MONTHS_AHEAD
        site = _Site()
        order: list[str] = []

        def record_fetch(url: str) -> str:
            order.append(url)
            return site.fetch(url)

        with (
            patch("scrapers.wfiu_community_calendar._fetch_html", side_effect=record_fetch),
            patch("scrapers.wfiu_community_calendar._now", return_value=FROZEN_NOW),
            patch(
                "scrapers.wfiu_community_calendar.time.sleep",
                side_effect=lambda _seconds: order.append("sleep"),
            ),
        ):
            scraper.fetch_events()

        first_detail = next(i for i, entry in enumerate(order) if "/event/" in entry)
        assert order[first_detail - 1] == "sleep"


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

    def test_weekly_schedule_selects_the_card_weekday_entry(self):
        site = _Site(
            pages=[
                _listing_html(
                    _card(
                        "Weekly Pick",
                        weekday="Friday",
                        time_raw=(
                            "Every week through Oct 27, 2026. "
                            "Monday: 10:00 AM - 11:00 AM "
                            "Friday: 05:30 PM - 06:30 PM"
                        ),
                    ),
                )
            ]
        )
        events, _ = _run(site)

        assert events[0]["dtstart"] == datetime(2026, 9, 18, 17, 30, tzinfo=TZ)
        assert events[0]["dtend"] == datetime(2026, 9, 18, 18, 30, tzinfo=TZ)

    def test_weekly_schedule_without_a_matching_weekday_is_all_day(self):
        site = _Site(
            pages=[
                _listing_html(
                    _card(
                        "Mismatched Pick",
                        weekday="Friday",
                        time_raw=("Every week through Oct 27, 2026. Monday: 10:00 AM - 11:00 AM"),
                    ),
                )
            ]
        )
        events, _ = _run(site)

        assert events[0]["dtstart"] == date(2026, 9, 18)
        assert events[0]["dtend"] == date(2026, 9, 19)


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

    def test_occurrence_one_day_past_the_horizon_drops_without_a_date_error(self, caplog):
        # The listing's `f1` filter clips to its end date inclusively, so a
        # multi-day series that starts in-window leaks its horizon+1 occurrence
        # (2026-12-18 here). That is a normal out-of-window drop -- the Horizon
        # guard would discard it anyway -- not date drift, so it must not log an
        # ERROR or count toward DATE_ERROR_THRESHOLD.
        leaked = _listing_html(_card("Late Run", display_date="Dec 18", weekday="Friday"))

        with caplog.at_level("ERROR"):
            events, _ = _run(_Site(pages=[leaked]))

        assert events == []
        assert not [r for r in caplog.records if "could not bind a date" in r.getMessage()]

    def test_unparseable_dates_raise_after_a_small_threshold(self):
        bad = [_card(f"Bad {i}", display_date="Feb 30", weekday="Monday") for i in range(4)]
        site = _Site(pages=[_listing_html(*bad)])

        with pytest.raises(RuntimeError, match="date"):
            _run(site)

    def test_dates_below_the_threshold_degrade_without_raising(self):
        bad = [_card(f"Bad {i}", display_date="Feb 30", weekday="Monday") for i in range(3)]
        site = _Site(pages=[_listing_html(*bad)])

        events, _ = _run(site)

        assert events == []

    def test_past_real_dates_still_count_as_date_errors(self):
        # The listing is filtered from today, so a card already behind us is
        # stale -- drift, not the horizon leak -- and must keep counting toward
        # DATE_ERROR_THRESHOLD. Sep 1 is before the frozen clock.
        past = [_card(f"Stale {i}", display_date="Sep 1", weekday="Tuesday") for i in range(4)]
        site = _Site(pages=[_listing_html(*past)])

        with pytest.raises(RuntimeError, match="date"):
            _run(site)

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
    """Every emitted occurrence passes the shared Horizon predicate.

    A real date ahead of the Horizon is a normal drop, never date drift: the
    listing's inclusive end filter leaks it for a series that starts in-window.
    A month/day that names no real calendar date, or one already past, still
    counts toward `DATE_ERROR_THRESHOLD` -- see `TestTimeAndIdentity`.
    """

    def test_occurrence_beyond_the_horizon_is_dropped(self):
        beyond = _listing_html(_card("Far Away Event", display_date="Dec 20", weekday="Sunday"))
        events, _ = _run(_Site(pages=[beyond]))

        assert events == []

    def test_past_occurrence_is_dropped(self):
        past = _listing_html(_card("Gone Event", display_date="Sep 1", weekday="Tuesday"))
        events, _ = _run(_Site(pages=[past]))

        assert events == []

    def test_many_occurrences_past_the_horizon_do_not_trip_the_date_threshold(self, caplog):
        """A busy season of horizon+1 leaks must not abort the run.

        Before #148 four such cards exceeded DATE_ERROR_THRESHOLD and raised;
        they are valid dates, so they drop silently instead.
        """
        leaked = [_card(f"Late {i}", display_date="Dec 18", weekday="Friday") for i in range(5)]

        with caplog.at_level("ERROR"):
            events, _ = _run(_Site(pages=[_listing_html(*leaked)]))

        assert events == []
        assert not [r for r in caplog.records if "could not bind a date" in r.getMessage()]

    def test_cross_year_horizon_leak_drops_without_a_date_error(self, caplog):
        # When the Horizon crosses New Year, the leak's month/day also occurs in
        # `today.year`, far in the past. Classification must read the occurrence
        # nearest today (the future one), not that current-year date.
        now = datetime(2026, 12, 20, 9, 0, tzinfo=TZ)
        leak = (now + timedelta(days=MONTHS_AHEAD * 31)).date() + timedelta(days=1)
        assert leak.year > now.year  # the case under test
        card = _card(
            "Cross-Year Leak",
            display_date=f"{leak:%b} {leak.day}",
            weekday=leak.strftime("%A"),
        )

        with caplog.at_level("ERROR"):
            events, _ = _run(_Site(pages=[_listing_html(card)]), now=now)

        assert events == []
        assert not [r for r in caplog.records if "could not bind a date" in r.getMessage()]

    def test_six_month_horizon_leak_drops_without_a_date_error(self, caplog):
        # With a months-long Horizon the leak's previous-year occurrence can sit
        # nearer today than the leak sits past the Horizon; the card's weekday
        # must decide, not raw proximity to today.
        now = datetime(2026, 9, 21, 9, 0, tzinfo=TZ)
        months = 6
        leak = (now + timedelta(days=months * 31)).date() + timedelta(days=1)
        assert leak.strftime("%A") == "Saturday"  # 2027-03-27
        card = _card(
            "Six-Month Leak",
            display_date=f"{leak:%b} {leak.day}",
            weekday=leak.strftime("%A"),
        )

        with caplog.at_level("ERROR"):
            events, _ = _run(_Site(pages=[_listing_html(card)]), now=now, months=months)

        assert events == []
        assert not [r for r in caplog.records if "could not bind a date" in r.getMessage()]

    def test_weekday_disambiguates_a_stale_cross_year_card(self, caplog):
        # Jan 1 2026 is a Thursday and Jan 1 2027 a Friday: the card names the
        # already-past occurrence, so it is stale drift, not the next-year leak.
        card = _card("Stale New Year", display_date="Jan 1", weekday="Thursday")

        with caplog.at_level("ERROR"):
            events, _ = _run(_Site(pages=[_listing_html(card)]))

        assert events == []
        assert [r for r in caplog.records if "could not bind a date" in r.getMessage()]

    def test_leap_day_card_resolves_to_its_stated_year(self, caplog):
        # Feb 29 has no occurrence inside the window's own years; the weekday
        # names 2024 (Thursday), a past leap year, so the card is stale drift.
        card = _card("Old Leap Day", display_date="Feb 29", weekday="Thursday")

        with caplog.at_level("ERROR"):
            events, _ = _run(_Site(pages=[_listing_html(card)]))

        assert events == []
        assert [r for r in caplog.records if "could not bind a date" in r.getMessage()]


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


class TestStaleUrlGuard:
    """The pipeline's stale-URL guard is a verified no-op for WFIU (#143, spec Q15).

    WFIU slugs embed DD-MM-YYYY (e.g. heist-24-08-2026-10-32-57) and carry no
    /YYYY/MM/ path, so the guard that drops stale WordPress-style URLs can never
    read a WFIU event as stale -- even when the slug's date predates the build
    window.
    """

    def test_no_wfiu_event_is_dropped_by_the_stale_url_guard(self):
        events, _ = _run()
        ics = WFIUCommunityCalendarScraper().create_calendar(events).to_ical().decode()
        pipeline_events = extract_events(ics, source_name="WFIU Community Calendar")

        # The Heist slug embeds 24-08-2026, a month before the frozen clock, so a
        # /YYYY/MM/ read would call it stale. The guard must keep it anyway.
        kept = [e for e in pipeline_events if not _url_predates_window(e["content"], FROZEN_NOW)]

        assert len(kept) == len(pipeline_events) == 3
        assert any("heist-24-08-2026-10-32-57" in e["content"] for e in kept)


def _registered_bloomington_entries() -> list[dict]:
    entries: list[dict] = []
    for name in ("pending_feeds.txt", "feeds.txt"):
        entries.extend(parse_pending_feeds(BLOOMINGTON_DIR / name))
    return entries


class TestRegistrationContract:
    """The #140 registration shape: DB-first entry, primary-source priority (ADR 0011)."""

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


HEIST_IMAGE_SUFFIX = "sq-heist-2.jpg"
HEIST_LOCATION = "Waldron Auditorium, 122 S Walnut St, Bloomington, Indiana 47404"


class TestDetailEnrichment:
    """Canonical fields come from the detail page; the card is the fallback (#142).

    The visitor contract: a card shows the detail's title, venue, postal
    address, rich description, image, and ticket link -- not the thin listing
    text -- so the event can be placed geographically and acted on.
    """

    def test_detail_title_and_venue_win_over_the_card(self):
        site = _Site(pages=[_listing_html(_card("HEIST CARD TITLE"))])

        events, _ = _run(site)

        assert events[0]["title"] == "Heist"
        assert events[0]["location"].startswith("Waldron Auditorium")

    def test_location_carries_venue_street_city_state_and_zip(self):
        events, _ = _run()

        assert _by_title(events, "Heist")["location"] == HEIST_LOCATION

    def test_shared_city_filter_can_act_on_the_postal_location(self):
        from scrapers.lib.city_filter import (
            load_allowed_cities,
            location_matches_allowed_cities,
        )

        allowed, excluded, zips = load_allowed_cities(BLOOMINGTON_DIR)
        events, _ = _run()
        heist = _by_title(events, "Heist")["location"]
        ukulele = _by_title(events, "Adult Ukulele Class")["location"]

        assert location_matches_allowed_cities(heist, allowed, excluded, zips)
        assert not location_matches_allowed_cities(ukulele, allowed, excluded, zips)

    def test_description_is_plain_text_with_org_prefix_and_ticket_suffix(self):
        events, _ = _run()
        event = _by_title(events, "Heist")

        assert event["description"].startswith("Presented by Constellation Stage + Screen")
        assert "A band of criminals" in event["description"]
        assert "Constellation Stage & Screen presents" in event["description"]
        assert "Tickets: https://seeconstellation.org/mainstage/heist/" in event["description"]
        assert "<" not in event["description"]
        assert "&amp;" not in event["description"]

    def test_event_url_stays_on_the_credited_detail_page(self):
        events, _ = _run()
        event = _by_title(events, "Heist")

        assert event["url"] == (
            "https://www.ipm.org/community-calendar/event/heist-24-08-2026-10-32-57"
        )
        assert event["url"] != "https://seeconstellation.org/mainstage/heist/"

    def test_detail_image_is_attached(self):
        events, _ = _run()
        event = _by_title(events, "Heist")

        assert event["image_url"].startswith("https://")
        assert event["image_url"].endswith(HEIST_IMAGE_SUFFIX)

    def test_card_fields_backfill_a_detail_without_them(self):
        site = _Site(
            pages=[_listing_html(_card("The Card Title"))],
            details={HEIST_SLUG: "wfiu_detail_minimal.html"},
        )

        events, _ = _run(site)

        assert events[0]["title"] == "The Card Title"
        assert events[0]["location"] == "Somewhere"
        assert not events[0].get("image_url")

    def test_shared_detail_url_is_fetched_once(self):
        card = _card("Movie", time_raw="02:00 PM - 04:00 PM")

        _, calls = _run(_Site(pages=[_listing_html(card, card)]))

        detail_calls = [url for url in calls if "/event/" in url]
        assert len(detail_calls) == 1

    def test_missing_content_id_falls_back_to_the_card_url(self):
        site = _Site(
            pages=[_listing_html(_card("Heist"))],
            details={HEIST_SLUG: "wfiu_detail_no_meta.html"},
        )

        events, _ = _run(site)

        expected = hashlib.md5(
            b"https://www.ipm.org/community-calendar/event/heist-24-08-2026-10-32-57"
            b"-2026-09-18-0900-2200"
        ).hexdigest()
        assert events[0]["uid"] == f"{expected}@ipm.org"


class TestDetailFailure:
    """A failed detail fetch degrades to a card event, loudly and boundedly (#142)."""

    def test_failed_detail_emits_a_card_fallback_and_warns(self, caplog):
        site = _Site(fail={HEIST_SLUG})

        with caplog.at_level("WARNING"):
            events, _ = _run(site)

        heist = _by_title(events, "Heist")
        assert heist["title"] == "Heist"
        assert heist["location"] == "Waldron Auditorium"
        assert any("detail" in r.getMessage().lower() for r in caplog.records)

    def test_failed_details_above_the_threshold_raise(self, monkeypatch):
        monkeypatch.setattr("scrapers.wfiu_community_calendar.DETAIL_ERROR_THRESHOLD", 1)
        site = _Site(
            pages=[
                _listing_html(
                    _card("Heist", slug=HEIST_SLUG),
                    _card("Class", slug=UKULELE_SLUG),
                )
            ],
            fail={HEIST_SLUG, UKULELE_SLUG},
        )

        with pytest.raises(RuntimeError, match="detail"):
            _run(site)

    def test_detail_failure_aborts_without_fetching_the_rest(self, monkeypatch):
        """Once the threshold is crossed the run must not keep hitting the source."""
        monkeypatch.setattr("scrapers.wfiu_community_calendar.DETAIL_ERROR_THRESHOLD", 1)
        site = _Site(
            pages=[
                _listing_html(
                    _card("Heist", slug=HEIST_SLUG),
                    _card("Class", slug=UKULELE_SLUG),
                    _card("Concert", slug=METZ_SLUG),
                )
            ],
            fail={HEIST_SLUG, UKULELE_SLUG, METZ_SLUG},
        )

        with pytest.raises(RuntimeError, match="detail"):
            _run(site)

        detail_calls = [url for url in site.calls if "/event/" in url]
        assert len(detail_calls) == 2

    def test_postal_less_emissions_are_counted_in_the_run_record(self, tmp_path):
        site = _Site(fail={HEIST_SLUG})

        _run(site)

        runs = json.loads((tmp_path / RUN_HISTORY_FILE).read_text())["runs"]
        assert runs[-1]["postal_less"] == 1

    def test_postal_less_is_zero_when_every_detail_has_an_address(self, tmp_path):
        _run()

        runs = json.loads((tmp_path / RUN_HISTORY_FILE).read_text())["runs"]
        assert runs[-1]["postal_less"] == 0

    def test_address_without_a_zip_is_not_postal_less(self, tmp_path):
        """ZIP alone was never the indicator set: a 2-letter state also counts.

        The shared city filter geo-checks the emitted location via its ", IN"
        state indicator, so this event is not postal-less even though the
        detail carries no ZIP. Regression guard for the old bool(zip) check.
        """
        site = _Site(
            pages=[_listing_html(_card("No Zip", slug=NO_ZIP_SLUG))],
            details={NO_ZIP_SLUG: "wfiu_detail_no_zip.html"},
        )

        events, _ = _run(site)

        assert events[0]["location"] == "Waldron Auditorium, 122 S Walnut St, Bloomington, IN"
        runs = json.loads((tmp_path / RUN_HISTORY_FILE).read_text())["runs"]
        assert runs[-1]["postal_less"] == 0


class TestRelativeHrefNormalization:
    """A relative card href is resolved against BASE_URL before it leaves the scraper.

    Brightspot could serve relative `href`s; emitting one verbatim would produce a
    relative `URL:` line and, when the detail lacks a content id, seed the
    fallback identity (and therefore the UID) with that relative string. Both the
    event url and the fallback UID must be absolute.
    """

    def test_relative_card_href_emits_absolute_url_and_uid(self):
        site = _Site(
            pages=[_listing_html(_card("Heist", href_prefix=""))],
            details={HEIST_SLUG: "wfiu_detail_no_meta.html"},
        )

        events, calls = _run(site)

        absolute = f"https://www.ipm.org/community-calendar/event/{HEIST_SLUG}"
        assert events[0]["url"] == absolute
        expected = hashlib.md5(f"{absolute}-2026-09-18-0900-2200".encode()).hexdigest()
        assert events[0]["uid"] == f"{expected}@ipm.org"
        assert [url for url in calls if "/event/" in url] == [absolute]


class TestRegistrationSmokeTest:
    """The registration smoke test gets a bounded crawl; production stays unbounded.

    `add_scraper.py` runs the exact registered command under a 120s timeout,
    which a full Horizon crawl can exceed. `SCRAPER_TEST_PAGE_CAP` (armed only
    by that harness) stops the walk cleanly and skips run history, so a smoke
    test cannot masquerade as a coverage run or drag down the trailing median.
    """

    def test_test_page_cap_bounds_the_smoke_crawl_without_raising(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_TEST_PAGE_CAP", "1")

        events, calls = _run()

        listing_calls = [url for url in calls if "/event/" not in url]
        assert len(listing_calls) == 1
        assert len(events) == 2  # the fixture's first page still emits

    def test_smoke_crawl_does_not_record_run_history(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SCRAPER_TEST_PAGE_CAP", "1")

        _run()

        assert not (tmp_path / RUN_HISTORY_FILE).exists()

    def test_registered_command_walks_every_page_when_the_cap_is_unset(self):
        # No env var: the production path is unchanged (the fixture has 2 pages).
        _, calls = _run()

        listing_calls = [url for url in calls if "/event/" not in url]
        assert len(listing_calls) == 2

    def test_an_invalid_cap_is_ignored(self, monkeypatch):
        monkeypatch.setenv("SCRAPER_TEST_PAGE_CAP", "not-a-number")

        _, calls = _run()

        listing_calls = [url for url in calls if "/event/" not in url]
        assert len(listing_calls) == 2

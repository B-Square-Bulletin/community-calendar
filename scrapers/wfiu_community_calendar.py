#!/usr/bin/env python3
"""WFIU Community Calendar (Indiana Public Media) via server-rendered HTML.

The listing at https://www.ipm.org/community-calendar is Brightspot HTML with
no JSON/GraphQL/REST API, no RSS/Atom, no iCal/ICS, and no JSON-LD (verified in
the surface research). The only way in is to scrape the server-rendered pages
over plain HTTP -- no browser, no Node, no Crawlee, no new runtime dependency.

The listing is occurrence-expanded: it renders one `ps-promo.PromoEvent` card
per occurrence of a series, so each card becomes exactly one event. The listing
supports a server-side date filter and fixed 10-card pages:

    GET https://www.ipm.org/community-calendar?f1=<startMs>-<endMs>&p=1..N

`f1` is the machine value behind the From/To date pickers (`?from=`/`?to=` are
ignored). This scraper fetches only the pages inside the calendar's Horizon,
reads the rendered `1 of N` to bound paging, and hard-caps the pages it will
walk (failing loud rather than truncating a crawl).

Each unique detail URL is fetched once for the stable `brightspot.contentId`
that keys the UID. WFIU is an aggregator: it loses cross-source dedupe to
direct venue/CVB sources and merges with other aggregators under the existing
binary-tier sort in `scripts/combine_ics.py`/`source_priority.json`.

Usage:
    python scrapers/wfiu_community_calendar.py --output cities/bloomington/wfiu_community_calendar.ics
"""

import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from lib.base import BaseScraper
from lib.horizon import within

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent

BASE_URL = "https://www.ipm.org"
LISTING_URL = f"{BASE_URL}/community-calendar"
# The listing page itself is the source page attributed to every event.
SOURCE_URL = f"{LISTING_URL}/"

DOMAIN = "ipm.org"
DEFAULT_TIMEZONE = "America/Indiana/Indianapolis"
TIMEZONE = ZoneInfo(DEFAULT_TIMEZONE)

CITY = "bloomington"
CITY_DIR = ROOT_DIR / "cities" / CITY

# The listing reports `1 of N`; walk at most this many pages and raise if the
# source claims more, so a runaway crawl surfaces instead of quietly stopping.
PAGE_CAP = 80
# One detail fetch per unique event URL, for the stable content id. Raise on
# cap-hit rather than truncate the inventory.
DETAIL_CAP = 500
# robots.txt allows all and sets no Crawl-delay; this is voluntary citizenship.
CRAWL_DELAY = 2.0
REQUEST_TIMEOUT = 90

# Silent-degradation guard: each run appends its counts to a history file under
# the committed per-city report slice (`report/<city>/` is published by the
# workflow's existing `git add report/`), so the next run can warn when the
# fetched card count collapses against the trailing window.
RUN_HISTORY_PATH = ROOT_DIR / "report" / CITY / "wfiu_community_calendar.runs.json"
RUN_HISTORY_MAX = 30
RUN_HISTORY_WINDOW = 7
DEGRADATION_FRACTION = 0.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_LEADING_TIME = re.compile(r"^(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", re.I)
_SCHEDULE_ENTRY = re.compile(
    r"([A-Z][a-z]+):\s*(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)"
)
_PAGE_COUNT = re.compile(r"(\d+)\s+of\s+(\d+)")
_MONTH_DAY = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2})")
_CLOCK = re.compile(r"(\d{1,2}):(\d{2})(AM|PM)")
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _now() -> datetime:
    """Current time in the source's timezone (a seam, patched in tests)."""
    return datetime.now(TIMEZONE)


def _fetch_html(url: str) -> str:
    """Fetch one page over plain HTTP (a seam, patched in tests)."""
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"WFIU returned HTTP {response.status_code} for {url}")
    return response.text


def _trailing_median(counts: list[int]) -> float | None:
    """Median of the last RUN_HISTORY_WINDOW counts, or None when there are none."""
    window = counts[-RUN_HISTORY_WINDOW:]
    if not window:
        return None
    ordered = sorted(window)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _text(element) -> str:
    """Collapsed visible text of a selected node, or "" when absent."""
    return " ".join(element.get_text(" ", strip=True).split()) if element else ""


def _plain_text(markup: str) -> str:
    """Strip card HTML to readable plain text, with no length cap."""
    text = re.sub(r"(?i)<br\s*/?>", "\n", markup or "")
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _parse_clock(value: str) -> dtime:
    """Parse an `HH:MM AM/PM` clock string as a local wall-clock time."""
    match = _CLOCK.fullmatch(value.strip().upper().replace(" ", ""))
    if not match:
        raise ValueError(f"unparseable clock: {value!r}")
    hour = int(match.group(1)) % 12
    if match.group(3) == "PM":
        hour += 12
    return dtime(hour, int(match.group(2)))


def _time_range(raw: str, weekday: str | None) -> tuple[dtime, dtime] | None:
    """The card's clock range, or None when the text carries no parseable time.

    One-off, daily, and monthly cards lead with `HH:MM AM - HH:MM PM`. Weekly
    cards instead list `Weekday: HH:MM AM - HH:MM PM` entries; the occurrence
    card's own weekday selects the matching entry, falling back to the first.
    """
    text = " ".join((raw or "").split())
    head = _LEADING_TIME.match(text)
    if head:
        return _parse_clock(head.group(1)), _parse_clock(head.group(2))
    entries = _SCHEDULE_ENTRY.findall(text)
    if entries:
        for name, start, end in entries:
            if weekday and name.lower() == weekday.lower():
                return _parse_clock(start), _parse_clock(end)
        _, start, end = entries[0]
        return _parse_clock(start), _parse_clock(end)
    return None


def _bind_year(display: str, weekday: str | None, today: date) -> date | None:
    """Bind the card's year-less month/day to the first on/after `today`.

    The card renders `Sep 18 Friday` with no year; the candidate year whose
    weekday agrees is preferred, so a Dec->Jan rollover lands on the right date.
    The Horizon predicate is the authoritative guard downstream, not this binder.
    """
    match = _MONTH_DAY.match(display)
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    day = int(match.group(2))
    candidates: list[date] = []
    for year in range(today.year, today.year + 3):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            candidates.append(candidate)
    if not candidates:
        return None
    if weekday:
        for candidate in candidates:
            if candidate.strftime("%A").lower() == weekday.lower():
                return candidate
    return candidates[0]


def _uid(identity: str, occurrence_date: date) -> str:
    """Stable per-occurrence UID: hash of the content id plus occurrence date."""
    digest = hashlib.md5(f"{identity}-{occurrence_date.isoformat()}".encode()).hexdigest()
    return f"{digest}@{DOMAIN}"


def _content_id(html: str) -> str | None:
    """The Brightspot content id meta on a detail page, or None."""
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("meta[name='brightspot.contentId']")
    content = meta.get("content") if meta else None
    if not isinstance(content, str):
        return None
    return content.strip() or None


def _parse_cards(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """One dict per `ps-promo.PromoEvent` occurrence card on a listing page."""
    cards: list[dict[str, Any]] = []
    for node in soup.select("ps-promo.PromoEvent"):
        link = node.select_one("a.PromoEvent-link-link") or node.select_one("h3.PromoEvent-title a")
        cards.append(
            {
                "url": (link.get("href") if link else None),
                "title": _text(node.select_one(".PromoEvent-title")),
                "venue": _text(node.select_one(".PromoEvent-venue")),
                "date_display": _text(node.select_one(".PromoEvent-date-date")),
                "weekday": _text(node.select_one(".PromoEvent-date-day")) or None,
                "time_raw": _text(node.select_one(".PromoEvent-time")),
                "description": _text(node.select_one(".PromoEvent-description")),
            }
        )
    return cards


def _parse_listing_page(html: str) -> tuple[list[dict[str, Any]], int, int]:
    """The page's cards plus its rendered `current of total` page counts."""
    soup = BeautifulSoup(html, "html.parser")
    counts = _PAGE_COUNT.search(_text(soup.select_one(".EventSearchResultsModule-pageCounts")))
    if not counts:
        raise RuntimeError("WFIU listing page did not report a page count")
    return _parse_cards(soup), int(counts.group(1)), int(counts.group(2))


class WFIUCommunityCalendarScraper(BaseScraper):
    """WFIU Community Calendar (Indiana Public Media) via server-rendered HTML."""

    name = "WFIU Community Calendar"
    domain = DOMAIN
    timezone = DEFAULT_TIMEZONE
    source_url = SOURCE_URL

    def _walk_listing(self, start_ms: int, end_ms: int) -> tuple[list[dict[str, Any]], int]:
        """Fetch every listing page inside the Horizon, capped and loud."""
        cards: list[dict[str, Any]] = []
        total: int | None = None
        page = 1
        while True:
            if page > PAGE_CAP:
                raise RuntimeError(f"WFIU listing exceeded the hard page cap of {PAGE_CAP}")
            html = _fetch_html(f"{LISTING_URL}?f1={start_ms}-{end_ms}&p={page}")
            page_cards, _current, reported_total = _parse_listing_page(html)
            if total is None:
                total = reported_total
                if total > PAGE_CAP:
                    raise RuntimeError(
                        f"WFIU listing reports {total} pages, above the hard page cap "
                        f"of {PAGE_CAP}; refusing to truncate the crawl"
                    )
            cards.extend(page_cards)
            if page >= total:
                return cards, page
            page += 1
            time.sleep(CRAWL_DELAY)

    @staticmethod
    def _unique_urls(cards: list[dict[str, Any]]) -> list[str]:
        """Detail URLs in first-seen order, one per unique event."""
        return list(dict.fromkeys(c["url"] for c in cards if c.get("url")))

    def _fetch_details(self, urls: list[str]) -> dict[str, str]:
        """One fetch per unique detail URL, capped and loud."""
        if len(urls) > DETAIL_CAP:
            raise RuntimeError(
                f"WFIU listing yields {len(urls)} unique detail URLs, above the "
                f"detail-fetch cap of {DETAIL_CAP}; refusing to truncate"
            )
        details: dict[str, str] = {}
        for index, url in enumerate(urls):
            if index:
                time.sleep(CRAWL_DELAY)
            details[url] = _fetch_html(url)
        return details

    def _parse_card(
        self, card: dict[str, Any], today: date, detail_html: str | None
    ) -> dict[str, Any] | None:
        """One event from one occurrence card, or None when its date is unusable."""
        occurrence = _bind_year(card["date_display"], card["weekday"], today)
        if occurrence is None:
            self.logger.warning(
                f"WFIU Community Calendar: could not read a date from "
                f"{card['date_display']!r} for {card['title']!r}"
            )
            return None

        clock = _time_range(card["time_raw"], card["weekday"])
        if clock is None:
            self.logger.warning(
                f"WFIU Community Calendar: no parseable time in {card['time_raw']!r} "
                f"for {card['title']!r}; emitting all-day"
            )
            dtstart: Any = occurrence
            dtend: Any = occurrence + timedelta(days=1)
        else:
            start, end = clock
            dtstart = datetime.combine(occurrence, start, tzinfo=TIMEZONE)
            dtend = datetime.combine(occurrence, end, tzinfo=TIMEZONE)
            if dtend <= dtstart:
                dtend += timedelta(days=1)

        identity = (_content_id(detail_html) if detail_html else None) or card["url"]
        return {
            "title": card["title"],
            "dtstart": dtstart,
            "dtend": dtend,
            "url": card["url"],
            "location": card["venue"],
            "description": _plain_text(card["description"]),
            "uid": _uid(identity, occurrence),
        }

    def _load_runs(self) -> list[dict[str, Any]]:
        """Prior runs' records, or [] on a missing/corrupt history file."""
        try:
            data = json.loads(RUN_HISTORY_PATH.read_text())
        except (OSError, ValueError):
            return []
        runs = data.get("runs") if isinstance(data, dict) else None
        if not isinstance(runs, list):
            return []
        return [r for r in runs if isinstance(r, dict)]

    def _record_run(self, run: dict[str, Any], runs: list[dict[str, Any]]) -> None:
        runs.append(run)
        try:
            RUN_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            RUN_HISTORY_PATH.write_text(
                json.dumps({"runs": runs[-RUN_HISTORY_MAX:]}, indent=2) + "\n"
            )
        except OSError as exc:
            self.logger.warning(f"WFIU Community Calendar: could not write run history: {exc}")

    def _warn_if_degraded(self, cards: int, runs: list[dict[str, Any]]) -> None:
        counts = [r["cards_fetched"] for r in runs if isinstance(r.get("cards_fetched"), int)]
        median = _trailing_median(counts)
        if median and cards < median * DEGRADATION_FRACTION:
            self.logger.warning(
                f"WFIU Community Calendar: fetched {cards} cards, below 50% of the "
                f"trailing {min(len(counts), RUN_HISTORY_WINDOW)}-run median ({median:g}) "
                "-- possible coverage degradation"
            )

    def fetch_events(self) -> list[dict[str, Any]]:
        now = _now()
        today = now.date()
        horizon = self.horizon_cutoff(now)
        start_ms = int(datetime.combine(today, dtime.min, tzinfo=TIMEZONE).timestamp() * 1000)
        end_ms = int(horizon.timestamp() * 1000)

        cards, pages = self._walk_listing(start_ms, end_ms)
        urls = self._unique_urls(cards)
        details = self._fetch_details(urls)

        events: list[dict[str, Any]] = []
        for card in cards:
            detail = details.get(str(card.get("url") or ""))
            parsed = self._parse_card(card, today, detail)
            if parsed is None or not within(parsed["dtstart"], horizon):
                continue
            events.append(parsed)

        self.logger.info(
            f"WFIU Community Calendar: {pages} pages, {len(cards)} cards, "
            f"{len(urls)} unique detail URLs, {len(events)} events emitted"
        )
        runs = self._load_runs()
        self._warn_if_degraded(len(cards), runs)
        self._record_run(
            {
                "date": now.date().isoformat(),
                "pages": pages,
                "cards_fetched": len(cards),
                "unique_detail_urls": len(urls),
                "details_fetched": len(details),
                "emitted": len(events),
            },
            runs,
        )
        return events


if __name__ == "__main__":
    WFIUCommunityCalendarScraper.main()

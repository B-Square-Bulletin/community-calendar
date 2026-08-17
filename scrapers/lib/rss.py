"""RSS feed scraper base class."""

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

import feedparser

from .base import BaseScraper
from .timeutil import parse_naive_ics

if TYPE_CHECKING:
    from time import struct_time


class RssScraper(BaseScraper):
    """
    Base class for RSS feed scrapers.

    Subclasses must set:
    - name: str - Source name
    - domain: str - Domain for UIDs
    - rss_url: str - URL of the RSS feed

    And implement:
    - parse_entry(entry) -> dict | None
    """

    rss_url: str = ""
    timezone: str = "America/Los_Angeles"

    def fetch_events(self) -> list[dict[str, Any]]:
        """Fetch and parse events from RSS feed."""
        self.logger.info(f"Fetching RSS feed: {self.rss_url}")
        feed = feedparser.parse(self.rss_url)
        self.logger.info(f"Found {len(feed.entries)} entries in RSS feed")

        events = []
        for entry in feed.entries:
            event = self.parse_entry(entry)
            if event:
                events.append(event)
                self.logger.info(f"Found event: {event['title']} on {event['dtstart']}")

        return events

    @abstractmethod
    def parse_entry(self, entry: dict) -> dict[str, Any] | None:
        """
        Parse a single RSS entry into event data.

        Returns None if parsing fails.

        Returns dict with: title, dtstart, dtend, url, location, description
        """

    def parse_rss_date(self, entry: dict) -> datetime | None:
        """
        Parse date from RSS entry's published_parsed or published field.
        Returns datetime in local timezone.
        """
        tz = ZoneInfo(self.timezone)

        # Try parsed tuple first
        if entry.get("published_parsed"):
            dt_tuple = cast("struct_time", entry["published_parsed"])
            dt_utc = datetime(
                dt_tuple.tm_year,
                dt_tuple.tm_mon,
                dt_tuple.tm_mday,
                dt_tuple.tm_hour,
                dt_tuple.tm_min,
                dt_tuple.tm_sec,
                tzinfo=ZoneInfo("UTC"),
            )
            return dt_utc.astimezone(tz)

        # Try raw string
        pub_date = entry.get("published")
        if pub_date:
            try:
                # Common RSS format: "Sat, 07 Feb 2026 16:30:00 GMT"
                dt_utc = parse_naive_ics(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
                dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
                return dt_utc.astimezone(tz)
            except ValueError:
                pass

        return None

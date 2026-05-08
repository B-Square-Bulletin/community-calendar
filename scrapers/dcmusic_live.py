#!/usr/bin/env python3
"""
Per-venue scraper backed by dcmusic.live's venue pages.

Useful as a fallback for venues whose primary calendar platform doesn't
expose a public feed (e.g., Tockify calendars where the owner has not
enabled the ICS export). Each venue page at https://dcmusic.live/venues/<slug>
renders a uniform grid of event cards with:

  - <a href="<ticket-url>">  — ticket platform URL (often encodes a date)
  - <article> wrapping the card content
    - <img alt="Title Case Name">
    - <p>Tonight / Tomorrow / Friday, 5/8</p>  (date label, sometimes relative)
    - <p>6:30 PM</p>                            (time)
    - <h5 class="font-black capitalize">title (often lowercase)</h5>

Tockify URLs (`tockify.com/<calendar>/detail/<id>/<ts_ms>`) give us an exact
timestamp; for other platforms we fall back to the rendered date label.

Usage:
    python scrapers/dcmusic_live.py \\
        --slug jojo --name "Jojo's Restaurant and Bar" \\
        --address "1518 U Street NW, Washington, DC 20009" \\
        --output cities/dc-music/dcmusic_jojo.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import argparse
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.request import urlopen, Request
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


VENUE_URL_TEMPLATE = "https://dcmusic.live/venues/{slug}"
TOCKIFY_DETAIL_RE = re.compile(r'tockify\.com/[^/]+/detail/(\d+)/(\d+)', re.I)
RELATIVE_DAY_RE = re.compile(r'(today|tonight|tomorrow)', re.I)
SHORT_DATE_RE = re.compile(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s+(\d{1,2})/(\d{1,2})', re.I)
TIME_RE = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', re.I)


class DcMusicLiveScraper(BaseScraper):
    """Scrape a single venue's events from dcmusic.live.

    Classified as an aggregator: emits X-SOURCE "dcmusic.live" rather than
    the venue name, so cross-source dedup in combine_ics.py orders this after
    any authoritative venue source for the same event. The venue name is
    still carried in LOCATION (and used in feeds.name for the Manage Feeds
    dialog), so per-venue distinction is preserved everywhere except the
    event-card source attribution line.

    See `AGGREGATORS` in scripts/combine_ics.py.
    """

    name = "dcmusic.live"
    domain = "dcmusic.live"
    timezone = "America/New_York"

    def __init__(self, slug: str, source_name: Optional[str] = None,
                 address: Optional[str] = None, tz: Optional[str] = None):
        super().__init__()
        self.slug = slug
        if source_name:
            self.name = source_name
        if tz:
            self.timezone = tz
        self.address = address
        self.default_url = VENUE_URL_TEMPLATE.format(slug=slug)

    def fetch_events(self) -> list[dict[str, Any]]:
        url = VENUE_URL_TEMPLATE.format(slug=self.slug)
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        soup = BeautifulSoup(html, 'html.parser')
        anchors = [a for a in soup.find_all('a', href=True)
                   if self._is_event_card(a)]
        self.logger.info(f"Found {len(anchors)} event cards on /venues/{self.slug}")

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        events: list[dict[str, Any]] = []

        for a in anchors:
            event = self._parse_card(a, tz, now)
            if event:
                events.append(event)
        return events

    @staticmethod
    def _is_event_card(a) -> bool:
        # Event cards are anchors that contain an <article> and an <img alt="...">
        if not a.find('article'):
            return False
        return a.find('img') is not None

    def _parse_card(self, anchor, tz: ZoneInfo, now: datetime) -> Optional[dict]:
        href = anchor.get('href', '')

        # Title: prefer the img alt text (Title Case); fall back to the h5
        title = ''
        img = anchor.find('img')
        if img and img.get('alt'):
            title = img['alt'].strip()
        if not title:
            h = anchor.select_one('h5, h4, h3')
            if h:
                title = h.get_text(' ', strip=True)
        if not title:
            return None

        dtstart = self._extract_datetime(anchor, href, tz, now)
        if not dtstart:
            return None
        if dtstart < now - timedelta(hours=4):
            return None

        location = self.address or self.name

        return {
            'title': title,
            'dtstart': dtstart,
            'dtend': dtstart + timedelta(hours=2, minutes=30),
            'url': href,
            'location': location,
            'description': '',
        }

    def _extract_datetime(self, anchor, href: str, tz: ZoneInfo,
                          now: datetime) -> Optional[datetime]:
        # Best signal: Tockify URLs encode a millisecond timestamp.
        m = TOCKIFY_DETAIL_RE.search(href)
        if m:
            ts_ms = int(m.group(2))
            return datetime.fromtimestamp(ts_ms / 1000, tz=tz)

        # Fallback: parse the rendered date label + time.
        text = anchor.get_text(' ', strip=True)
        time_m = TIME_RE.search(text)
        hour, minute = (20, 0)
        if time_m:
            hour = int(time_m.group(1)) % 12
            if time_m.group(3).lower() == 'pm':
                hour += 12
            minute = int(time_m.group(2) or 0)

        rel = RELATIVE_DAY_RE.search(text)
        if rel:
            base = now.date()
            if rel.group(1).lower() == 'tomorrow':
                base = base + timedelta(days=1)
            return datetime(base.year, base.month, base.day, hour, minute, tzinfo=tz)

        sd = SHORT_DATE_RE.search(text)
        if sd:
            month = int(sd.group(1))
            day = int(sd.group(2))
            year = now.year
            candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
            if candidate < now - timedelta(days=14):
                year += 1
                candidate = datetime(year, month, day, hour, minute, tzinfo=tz)
            return candidate

        return None


def main():
    parser = argparse.ArgumentParser(description="Scrape a venue's events from dcmusic.live")
    parser.add_argument('--slug', required=True, help='Venue slug, e.g. "jojo"')
    parser.add_argument('--name', required=True, help='Source display name')
    parser.add_argument('--address', help='Venue address for richer LOCATION')
    parser.add_argument('--timezone', default='America/New_York')
    parser.add_argument('--output', '-o', help='Output ICS file')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    scraper = DcMusicLiveScraper(
        slug=args.slug,
        source_name=args.name,
        address=args.address,
        tz=args.timezone,
    )
    scraper.run(args.output)


if __name__ == '__main__':
    main()

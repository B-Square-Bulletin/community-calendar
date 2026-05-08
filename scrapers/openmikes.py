#!/usr/bin/env python3
"""
Scraper for openmikes.org's per-city listing pages.

The site is a community-curated directory of recurring open mics. Each
listing is a long-running weekly program rather than a single event,
so the scraper synthesizes occurrences within the SCRAPE_MONTHS horizon.

Listing structure on the city page:

  <div class="listingdetails">
    <a class="listing__name">Tuesday Night Open Mic</a>
    <a class="listing__when">Every Tuesday at 9pm</a>
    <span class="listing__club">Saloon</span>
    <address class="adr">
      <a class="street-address">1205 U Street Northwest</a>
      <span class="locality">Washington</span>
      <span class="region">DC</span>
    </address>
  </div>

Usage:
    python scrapers/openmikes.py \\
        --city-slug Washington-DC --name "openmikes.org DC" \\
        --output cities/dc-music/openmikes_dc.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import argparse
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.request import urlopen, Request
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


WEEKDAYS = {
    'sunday': 6, 'monday': 0, 'tuesday': 1, 'wednesday': 2,
    'thursday': 3, 'friday': 4, 'saturday': 5,
}

WHEN_RE = re.compile(
    r'every\s+(?P<day>sunday|monday|tuesday|wednesday|thursday|friday|saturday)'
    r'\s+at\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)',
    re.I,
)


class OpenMikesScraper(BaseScraper):
    name = "openmikes.org"
    domain = "openmikes.org"
    timezone = "America/New_York"

    def __init__(self, city_slug: str, source_name: Optional[str] = None,
                 tz: Optional[str] = None):
        super().__init__()
        self.city_slug = city_slug
        if source_name:
            self.name = source_name
        if tz:
            self.timezone = tz
        self.default_url = f"https://openmikes.org/open-mics-in-{city_slug}"

    def fetch_events(self) -> list[dict[str, Any]]:
        url = self.default_url
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        soup = BeautifulSoup(html, 'html.parser')
        listings = soup.find_all('div', class_='listingdetails')
        self.logger.info(f"Found {len(listings)} listing(s) on {url}")

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        horizon = now + timedelta(days=self.months_ahead * 31)

        events: list[dict[str, Any]] = []
        for listing in listings:
            events.extend(self._expand_listing(listing, tz, now, horizon))
        return events

    def _expand_listing(self, listing, tz, now, horizon) -> list[dict[str, Any]]:
        name_el = listing.select_one('.listing__name')
        when_el = listing.select_one('.listing__when')
        club_el = listing.select_one('.listing__club')
        if not (name_el and when_el):
            return []

        program = name_el.get_text(' ', strip=True)
        when_text = when_el.get_text(' ', strip=True)
        venue = club_el.get_text(' ', strip=True) if club_el else ''

        m = WHEN_RE.search(when_text)
        if not m:
            self.logger.debug(f"Skipping {program}: can't parse {when_text!r}")
            return []
        weekday = WEEKDAYS[m.group('day').lower()]
        hour = int(m.group('hour')) % 12
        if m.group('ampm').lower() == 'pm':
            hour += 12
        minute = int(m.group('minute') or 0)

        # Build location from address block
        addr = listing.select_one('address.adr')
        location_parts = []
        if venue:
            location_parts.append(venue)
        if addr:
            for cls in ('street-address', 'locality', 'region'):
                el = addr.find(class_=cls)
                if el:
                    txt = el.get_text(' ', strip=True)
                    if txt and txt not in location_parts:
                        location_parts.append(txt)
        location = ', '.join(location_parts)

        host_el = self._find_detail(listing, 'Host')
        host = host_el.get_text(' ', strip=True) if host_el else ''
        title = f"{program} at {venue}" if venue else program
        description = f"Host: {host}" if host else ''

        # Synthesize one event per upcoming weekday occurrence within horizon.
        events = []
        # Start at "today" then walk forward to next matching weekday
        first_day = now.date()
        days_until = (weekday - first_day.weekday()) % 7
        # If today is the weekday but the time has passed, push to next week
        candidate = datetime(
            first_day.year, first_day.month, first_day.day,
            hour, minute, tzinfo=tz,
        ) + timedelta(days=days_until)
        if candidate < now:
            candidate += timedelta(days=7)

        while candidate <= horizon:
            events.append({
                'title': title,
                'dtstart': candidate,
                'dtend': candidate + timedelta(hours=2),
                'url': self.default_url,
                'location': location,
                'description': description,
            })
            candidate += timedelta(days=7)

        self.logger.info(
            f"  {program} @ {venue}: {len(events)} occurrence(s) "
            f"(every {m.group('day')} at {when_text})"
        )
        return events

    @staticmethod
    def _find_detail(listing, label):
        for d in listing.find_all('div', class_='listing__detail'):
            desc = d.find(class_='listing__detail__desc')
            if desc and label.lower() in desc.get_text(strip=True).lower():
                return d.find(class_='listing__detail__value')
        return None


def main():
    parser = argparse.ArgumentParser(description="Scrape openmikes.org city listings")
    parser.add_argument('--city-slug', required=True,
                        help='Slug as in URL, e.g. "Washington-DC"')
    parser.add_argument('--name', default='openmikes.org', help='Source display name')
    parser.add_argument('--timezone', default='America/New_York')
    parser.add_argument('--output', '-o', help='Output ICS file')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    scraper = OpenMikesScraper(
        city_slug=args.city_slug,
        source_name=args.name,
        tz=args.timezone,
    )
    scraper.run(args.output)


if __name__ == '__main__':
    main()

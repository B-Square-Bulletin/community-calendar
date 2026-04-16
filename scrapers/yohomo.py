#!/usr/bin/env python3
"""
Scraper for YOHOMO (yohomo.ca) — Toronto's queer events aggregator.

Webflow CMS site. The listing page has all events with dates/times.
Detail pages add venue, address, and description.

Usage:
    python scrapers/yohomo.py --output cities/toronto/yohomo.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import argparse
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from lib.base import BaseScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "https://www.yohomo.ca"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
}


class YohomoScraper(BaseScraper):
    """Scraper for YOHOMO queer events via Webflow CMS."""

    name = "YOHOMO"
    domain = "yohomo.ca"
    timezone = "America/Toronto"

    def _fetch(self, url: str) -> str | None:
        req = Request(url, headers=HEADERS)
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8')
        except (HTTPError, URLError) as e:
            self.logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def _parse_listing(self, html: str) -> list[dict]:
        """Parse the listing page for event slugs, dates, and times."""
        events = []
        # Split on each w-dyn-item
        items = re.split(r'role="listitem"[^>]*class="event w-dyn-item"', html)

        current_year = datetime.now().year

        for item in items[1:]:  # skip before first item
            # Extract slug
            slug_match = re.search(r'href="(/event/[^"]+)"', item)
            if not slug_match:
                continue
            slug = slug_match.group(1)

            # Extract date parts from the listing
            # Pattern: day-of-week . month day-number
            date_section = re.search(r'section-event-row-date(.*?)item-event-hours', item, re.DOTALL)
            if not date_section:
                continue

            date_text = date_section.group(1)
            date_parts = re.findall(r'text-style-allcaps"?>([^<]+)<', date_text)
            # Filter out dots and empty strings
            date_parts = [p.strip() for p in date_parts if p.strip() and p.strip() != '.']

            # Expected: ['Thu', 'Apr', '16'] or ['Thu', 'Apr 16']
            month_str = None
            day_str = None
            for part in date_parts:
                # Check for "Apr 16" combined
                m = re.match(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})', part)
                if m:
                    month_str = m.group(1)
                    day_str = m.group(2)
                    break
                # Check for standalone month
                if re.match(r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec', part):
                    month_str = part[:3]
                # Check for standalone day number
                if re.match(r'^\d{1,2}$', part):
                    day_str = part

            if not month_str or not day_str:
                continue

            # Extract time
            time_match = re.search(r'item-event-hours.*?text-style-allcaps"?>(\d{1,2}:\d{2}\s*[ap]m)', item, re.DOTALL)
            time_str = time_match.group(1).strip() if time_match else None

            # Parse the date
            try:
                date_string = f"{month_str} {day_str} {current_year}"
                event_date = datetime.strptime(date_string, "%b %d %Y")
                # If date is in the past by more than a month, assume next year
                now = datetime.now()
                if event_date.month < now.month - 1:
                    event_date = event_date.replace(year=current_year + 1)
            except ValueError:
                continue

            # Parse time if available
            if time_str:
                try:
                    t = datetime.strptime(time_str, "%I:%M %p")
                    event_date = event_date.replace(hour=t.hour, minute=t.minute)
                except ValueError:
                    pass

            # Title from slug
            title = slug.replace('/event/', '').replace('-', ' ').title()

            events.append({
                'slug': slug,
                'date': event_date,
                'title': title,
            })

        self.logger.info(f"Found {len(events)} events on listing page")
        return events

    def _fetch_detail(self, slug: str) -> dict:
        """Fetch venue, address, and description from a detail page."""
        html = self._fetch(f"{BASE_URL}{slug}")
        if not html:
            return {}

        result = {}

        # Title from detail page (more accurate than slug)
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if title_match:
            result['title'] = title_match.group(1).strip()

        # Venue
        venue_match = re.search(r'event-item-location[^>]*>\s*<p[^>]*>([^<]+)', html)
        if venue_match:
            result['venue'] = venue_match.group(1).strip()

        # Address
        addr_match = re.search(r'class="address"[^>]*>([^<]+)', html)
        if addr_match:
            result['address'] = addr_match.group(1).strip()

        # Description — rich text block may contain multiple paragraphs
        desc_match = re.search(r'text-rich-text events[^"]*">(.*?)</div>', html, re.DOTALL)
        if desc_match:
            # Strip HTML tags and collapse whitespace
            desc = re.sub(r'<[^>]+>', ' ', desc_match.group(1))
            desc = re.sub(r'\s+', ' ', desc).strip()
            if desc:
                result['description'] = desc

        return result

    def fetch_events(self) -> list[dict[str, Any]]:
        html = self._fetch(BASE_URL)
        if not html:
            return []

        listing = self._parse_listing(html)
        if not listing:
            return []

        # Filter to future events
        now = datetime.now()
        listing = [e for e in listing if e['date'] >= now]
        self.logger.info(f"{len(listing)} future events, fetching details...")

        # Fetch detail pages in parallel
        details = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._fetch_detail, e['slug']): e['slug'] for e in listing}
            for future in as_completed(futures):
                slug = futures[future]
                try:
                    details[slug] = future.result()
                except Exception:
                    details[slug] = {}

        # Build final events
        events = []
        for e in listing:
            detail = details.get(e['slug'], {})
            title = detail.get('title', e['title'])
            venue = detail.get('venue', '')
            address = detail.get('address', '')
            location = f"{venue}, {address}".strip(', ') if venue or address else ''
            description = detail.get('description', '')

            events.append({
                'title': title,
                'dtstart': e['date'],
                'dtend': None,
                'location': location,
                'description': description,
                'url': f"{BASE_URL}{e['slug']}",
            })

        self.logger.info(f"Found {len(events)} events with details")
        return events


def main():
    parser = argparse.ArgumentParser(description="Scrape YOHOMO queer events")
    parser.add_argument('--output', '-o', help='Output ICS file')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    scraper = YohomoScraper()
    scraper.run(args.output)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Scraper for The Pocket DC, the small-room music venue in 7DrumCity's
basement at 4221 Connecticut Ave NW.

The Pocket's events live on a Webflow-driven embed at
https://thepocket.7drumcity.com/shows-preview, with each event rendered as
a `div.uui-layout88_item-2.w-dyn-item`. Date and time are split into
`.event-month-2`, `.event-day-2`, and `.event-time-new-2`. Year is not in
the markup; we infer "this year unless the month is past, otherwise next".
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.request import urlopen, Request
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


SHOWS_URL = "https://thepocket.7drumcity.com/shows-preview"
SITE_URL = "https://thepocket.7drumcity.com"

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
)}


class ThePocketScraper(BaseScraper):
    name = "The Pocket"
    domain = "7drumcity.com"
    timezone = "America/New_York"
    default_url = SITE_URL

    _location = "The Pocket, 4221 Connecticut Ave NW, Washington, DC 20008"

    def fetch_events(self) -> list[dict[str, Any]]:
        req = Request(SHOWS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', class_='uui-layout88_item-2')
        self.logger.info(f"Found {len(items)} event cards")

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        events: list[dict[str, Any]] = []

        for item in items:
            event = self._parse_item(item, tz, now)
            if event:
                events.append(event)

        return events

    def _parse_item(self, item, tz: ZoneInfo, now: datetime) -> Optional[dict]:
        month_el = item.select_one('.event-month-2')
        day_el = item.select_one('.event-day-2')
        time_el = item.select_one('.event-time-new-2')
        if not (month_el and day_el):
            return None

        month_text = month_el.get_text(strip=True)[:3]
        month = MONTHS.get(month_text)
        if not month:
            return None

        try:
            day = int(day_el.get_text(strip=True))
        except ValueError:
            return None

        # Year inference: assume the upcoming occurrence
        year = now.year
        candidate = datetime(year, month, day, tzinfo=tz)
        if candidate < now - timedelta(days=14):
            year += 1
            candidate = datetime(year, month, day, tzinfo=tz)

        # Time
        hour, minute = 20, 0
        if time_el:
            t = self._parse_time(time_el.get_text(strip=True))
            if t:
                hour, minute = t
        dtstart = datetime(year, month, day, hour, minute, tzinfo=tz)

        # Drop past events
        if dtstart < now - timedelta(hours=4):
            return None

        # Title: the visible h3 (without `w-condition-invisible`)
        title = None
        for h in item.select('h3.uui-heading-xxsmall-4'):
            cls = h.get('class') or []
            if 'w-condition-invisible' not in cls:
                title = h.get_text(' ', strip=True)
                break
        if not title:
            return None

        supports_el = item.select_one('h4.supports-line')
        supports = supports_el.get_text(' ', strip=True) if supports_el else ''
        full_title = f"{title} w/ {supports}" if supports else title

        # Event URL
        link = item.select_one('a.link-block-2')
        href = link.get('href', '') if link else ''
        if href.startswith('/'):
            href = SITE_URL + href

        return {
            'title': full_title,
            'dtstart': dtstart,
            'dtend': dtstart + timedelta(hours=3),
            'url': href,
            'location': self._location,
            'description': '',
        }

    @staticmethod
    def _parse_time(s: str) -> Optional[tuple[int, int]]:
        m = re.match(r'\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*$', s, re.I)
        if not m:
            return None
        hour = int(m.group(1)) % 12
        if m.group(3).lower() == 'pm':
            hour += 12
        return hour, int(m.group(2) or 0)


if __name__ == '__main__':
    ThePocketScraper.main()

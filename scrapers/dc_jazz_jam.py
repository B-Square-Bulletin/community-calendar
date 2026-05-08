#!/usr/bin/env python3
"""
Scraper for the DC Jazz Jam weekly jazz session at Haydee's.
https://dcjazzjam.com

Each weekly session has a WordPress post with the date encoded in the title
("Sunday 5/10/26: ...") and a fixed time (6:30-9:00pm) and venue (Haydee's,
3102 Mount Pleasant St NW). The site exposes a standard RSS feed, but
RSS published_parsed reflects the post date, not the event date — so we
parse the event date from the title.
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import re
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Optional

from bs4 import BeautifulSoup

from lib.rss import RssScraper


# Pattern matches the leading date in titles like:
#   "Sunday 5/10/26: DC Jazz Jam's Mother's Day jam ..."
DATE_RE = re.compile(r'(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{2,4})')


class DcJazzJamScraper(RssScraper):
    name = "DC Jazz Jam"
    domain = "dcjazzjam.com"
    rss_url = "https://dcjazzjam.com/feed/"
    timezone = "America/New_York"
    default_url = "https://dcjazzjam.com"

    # Fixed venue and time per dcjazzjam.com — every Sunday at Haydee's.
    _location = "Haydee's, 3102 Mount Pleasant St NW, Washington, DC 20010"
    _start_hour = 18
    _start_minute = 30
    _duration_hours = 2.5  # 6:30-9:00pm

    def parse_entry(self, entry: dict) -> Optional[dict[str, Any]]:
        title = entry.get('title', '').strip()
        if not title:
            return None

        m = DATE_RE.search(title)
        if not m:
            return None

        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self.timezone)
        try:
            month = int(m.group('m'))
            day = int(m.group('d'))
            year = int(m.group('y'))
            if year < 100:
                year += 2000
            dtstart = datetime(year, month, day, self._start_hour, self._start_minute, tzinfo=tz)
        except ValueError:
            return None

        # Drop past events.
        if dtstart < datetime.now(tz) - timedelta(hours=4):
            return None

        dtend = dtstart + timedelta(hours=self._duration_hours)

        description_html = entry.get('summary', '') or entry.get('description', '')
        description = self._clean_description(description_html)

        return {
            'title': title,
            'dtstart': dtstart,
            'dtend': dtend,
            'url': entry.get('link', ''),
            'location': self._location,
            'description': description,
        }

    def _clean_description(self, description_html: str) -> str:
        if not description_html:
            return ''
        text = unescape(BeautifulSoup(description_html, 'html.parser').get_text(' ', strip=True))
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 500:
            text = text[:500].rstrip() + '…'
        return text


if __name__ == '__main__':
    DcJazzJamScraper.main()

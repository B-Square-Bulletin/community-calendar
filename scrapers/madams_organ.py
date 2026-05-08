#!/usr/bin/env python3
"""
Scraper for Madam's Organ via the venue's official MEC RSS feed.

The site exposes an events RSS feed at https://madamsorgan.com/events/feed/
with MEC-specific namespaced fields for start/end date and time.
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from datetime import datetime, timedelta
from html import unescape
import re
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.rss import RssScraper


RSS_URL = "https://madamsorgan.com/events/feed/"
LOCATION = "Madam's Organ Blues Bar, 2461 18th Street NW, Washington, DC 20009"


class MadamsOrganScraper(RssScraper):
    name = "Madam's Organ"
    domain = "madamsorgan.com"
    rss_url = RSS_URL
    timezone = "America/New_York"
    default_url = "https://madamsorgan.com/events/"

    def parse_entry(self, entry: dict) -> Optional[dict[str, Any]]:
        title = (entry.get("title") or "").strip()
        start_date = (entry.get("mec_startdate") or "").strip()
        start_hour = (entry.get("mec_starthour") or "").strip()
        if not (title and start_date and start_hour):
            return None

        tz = ZoneInfo(self.timezone)
        dtstart = self._parse_datetime(start_date, start_hour, tz)
        if dtstart is None:
            return None

        if dtstart < datetime.now(tz) - timedelta(hours=4):
            return None

        end_date = (entry.get("mec_enddate") or start_date).strip()
        end_hour = (entry.get("mec_endhour") or "").strip()
        dtend = self._parse_datetime(end_date, end_hour, tz) if end_hour else None
        if dtend is None or dtend <= dtstart:
            dtend = dtstart + timedelta(hours=3)

        description = self._clean_description(entry)

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": entry.get("link") or self.default_url,
            "location": LOCATION,
            "description": description,
        }

    @staticmethod
    def _parse_datetime(date_str: str, time_str: str, tz: ZoneInfo) -> Optional[datetime]:
        try:
            base = datetime.strptime(date_str, "%Y-%m-%d")
            tm = datetime.strptime(time_str.lower(), "%I:%M %p")
        except ValueError:
            return None

        return base.replace(hour=tm.hour, minute=tm.minute, tzinfo=tz)

    def _clean_description(self, entry: dict) -> str:
        html = ""
        content = entry.get("content") or []
        if content:
            html = content[0].get("value", "")
        if not html:
            html = entry.get("summary", "")

        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 700:
            text = text[:700].rstrip() + "…"
        return text


if __name__ == "__main__":
    MadamsOrganScraper.main()

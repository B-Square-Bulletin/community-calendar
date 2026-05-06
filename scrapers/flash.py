#!/usr/bin/env python3
"""
Scraper for Flash Nightclub's official schedule page.

Flash exposes server-rendered event cards at:
https://www.flashdc.com/schedule

Each card includes:
- `time[itemprop="startDate"]` with an ISO local datetime
- `span[itemprop="name"]` for the event title
- `a[itemprop="url"]` for the official event-detail path
- `.server-content` with lineup / room details
- `.btn-buy-now` with the ticket URL
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from datetime import datetime, timedelta
import re
from typing import Any, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


SCHEDULE_URL = "https://www.flashdc.com/schedule"
SITE_URL = "https://www.flashdc.com"
LOCATION = "Flash Nightclub, 645 Florida Ave NW, Washington, DC 20001"


class FlashScraper(BaseScraper):
    name = "Flash"
    domain = "flashdc.com"
    timezone = "America/New_York"
    default_url = SCHEDULE_URL

    def fetch_events(self) -> list[dict[str, Any]]:
        html = self.fetch_text_with_curl(SCHEDULE_URL)
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article.listing")
        self.logger.info(f"Found {len(articles)} schedule cards")

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        events: list[dict[str, Any]] = []

        for article in articles:
            event = self._parse_article(article, tz, now)
            if event:
                events.append(event)

        return events

    def _parse_article(
        self,
        article,
        tz: ZoneInfo,
        now: datetime,
    ) -> Optional[dict[str, Any]]:
        time_el = article.select_one('time[itemprop="startDate"]')
        title_el = article.select_one('[itemprop="name"]')
        link_el = article.select_one('a[itemprop="url"]')
        if not (time_el and title_el and link_el):
            return None

        dt_raw = (time_el.get("datetime") or "").strip()
        if not dt_raw:
            return None
        try:
            dtstart = datetime.strptime(dt_raw, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz)
        except ValueError:
            return None

        if dtstart < now - timedelta(hours=4):
            return None

        title = title_el.get_text(" ", strip=True)
        event_url = urljoin(SITE_URL, link_el.get("href", ""))
        description = self._build_description(article)
        image_el = article.select_one('img[itemprop="photo"]')
        image_url = image_el.get("src") if image_el else None

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtstart + timedelta(hours=4),
            "url": event_url,
            "location": LOCATION,
            "description": description,
            "image_url": image_url,
        }

    def _build_description(self, article) -> str:
        parts: list[str] = []

        content = article.select_one("div.server-content")
        if content:
            text = content.get_text("\n", strip=True)
            lines = [self._clean_line(line) for line in text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                parts.append(" | ".join(lines))

        doors_el = article.select_one("p.mt-5")
        if doors_el:
            doors = self._clean_line(doors_el.get_text(" ", strip=True))
            if doors:
                parts.append(doors)

        ticket_el = article.select_one("a.btn-buy-now")
        if ticket_el and ticket_el.get("href"):
            parts.append(f"Tickets: {ticket_el['href']}")

        return " | ".join(parts)

    @staticmethod
    def _clean_line(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text


if __name__ == "__main__":
    FlashScraper.main()

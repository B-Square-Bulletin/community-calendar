#!/usr/bin/env python3
"""Scraper for Toronto Community Housing events and board meetings."""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


def _clean(text: str) -> str:
    text = unescape(text or "")
    return re.sub(r"\s+", " ", text).strip()


class TorontoCommunityHousingScraper(BaseScraper):
    name = "Toronto Community Housing"
    domain = "torontohousing.ca"
    timezone = "America/Toronto"
    page_url = "https://torontohousing.ca/events"
    default_url = page_url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def fetch_html(self) -> str:
        req = Request(self.page_url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def parse_time_block(self, text: str) -> tuple[datetime | None, datetime | None]:
        text = _clean(text)
        m = re.search(
            r"([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2}\s*[ap]\.m\.)\s+to\s+(\d{1,2}:\d{2}\s*[ap]\.m\.)",
            text,
            re.I,
        )
        if not m:
            return None, None
        day, start_s, end_s = m.groups()
        start = datetime.strptime(f"{day} {start_s.lower().replace('.', '')}", "%A, %B %d, %Y %I:%M %p")
        end = datetime.strptime(f"{day} {end_s.lower().replace('.', '')}", "%A, %B %d, %Y %I:%M %p")
        tz = ZoneInfo(self.timezone)
        return start.replace(tzinfo=tz), end.replace(tzinfo=tz)

    def fetch_events(self) -> list[dict]:
        soup = BeautifulSoup(self.fetch_html(), "html.parser")
        cards = soup.select("a.node.node--type-event.node--view-mode-listing-item")
        now = datetime.now(ZoneInfo(self.timezone))
        events = []

        for card in cards:
            title = _clean(card.select_one("h3").get_text(" ", strip=True)) if card.select_one("h3") else ""
            excerpt = _clean(card.select_one("p").get_text(" ", strip=True)) if card.select_one("p") else ""
            time_el = card.select_one("time")
            address_el = card.select_one("p.address")
            category_el = card.select_one("span.taxonomy")

            if not title or not time_el:
                continue

            dtstart, dtend = self.parse_time_block(time_el.get_text(" ", strip=True))
            if not dtstart or dtend < now:
                continue

            location = _clean(address_el.get_text(" ", strip=True)) if address_el else ""
            category = _clean(category_el.get_text(" ", strip=True)) if category_el else ""
            description_parts = []
            if excerpt:
                description_parts.append(excerpt)
            if category:
                description_parts.append(f"Category: {category}")

            url = urljoin(self.page_url, card.get("href", ""))
            events.append(
                {
                    "title": title,
                    "dtstart": dtstart,
                    "dtend": dtend,
                    "url": url,
                    "location": location,
                    "description": "\n\n".join(description_parts),
                }
            )

        return events


if __name__ == "__main__":
    TorontoCommunityHousingScraper.main()

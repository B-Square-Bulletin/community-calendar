#!/usr/bin/env python3
"""Scraper for Metrolinx Board meeting dates."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

from lib.base import BaseScraper


class MetrolinxBoardScraper(BaseScraper):
    name = "Metrolinx Board"
    domain = "metrolinx.com"
    timezone = "America/Toronto"
    page_url = "https://www.metrolinx.com/en/about-us/the-board/board-meetings"
    default_url = page_url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def fetch_html(self) -> str:
        req = Request(self.page_url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def extract_upcoming_dates(self, html: str) -> list[datetime.date]:
        match = re.search(
            r'Upcoming Meetings</h2><ul[^>]*>(.*?)</ul>',
            html,
            re.S,
        )
        if not match:
            return []

        dates = []
        for value in re.findall(r"<li>([^<]+)</li>", match.group(1)):
            value = value.strip()
            try:
                dates.append(datetime.strptime(value, "%B %d, %Y").date())
            except ValueError:
                continue
        return dates

    def fetch_events(self) -> list[dict]:
        html = self.fetch_html()
        dates = self.extract_upcoming_dates(html)
        today = datetime.now().date()
        events = []
        for day in dates:
            if day < today:
                continue
            events.append(
                {
                    "title": "Metrolinx Board Meeting",
                    "dtstart": day,
                    "dtend": day + timedelta(days=1),
                    "url": self.page_url,
                    "description": "Board meeting date published on the Metrolinx Board Meetings page.",
                    "uid": f"{day.isoformat()}@{self.domain}",
                }
            )
        return events


if __name__ == "__main__":
    MetrolinxBoardScraper.main()

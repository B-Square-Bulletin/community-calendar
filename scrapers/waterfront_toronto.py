#!/usr/bin/env python3
"""Scraper for Waterfront Toronto board meetings and public events."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lib.base import BaseScraper


class WaterfrontTorontoScraper(BaseScraper):
    name = "Waterfront Toronto"
    domain = "waterfrontoronto.ca"
    timezone = "America/Toronto"
    page_url = "https://www.waterfrontoronto.ca/events"
    default_url = page_url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def fetch_html(self) -> str:
        req = Request(self.page_url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def extract_event_rows(self, html: str) -> list[dict[str, Any]]:
        match = re.search(
            r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>',
            html,
            re.S,
        )
        if not match:
            raise ValueError("No drupal-settings-json payload found")

        settings = json.loads(match.group(1))
        calendar = settings.get("fullCalendarView", [{}])[0]
        options = json.loads(calendar.get("calendar_options", "{}"))
        return options.get("events", [])

    def parse_dt(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo(self.timezone))
        except ValueError:
            return None

    def fetch_events(self) -> list[dict[str, Any]]:
        html = self.fetch_html()
        rows = self.extract_event_rows(html)
        now = datetime.now(ZoneInfo(self.timezone))
        events = []

        for row in rows:
            title = (row.get("title") or "").strip()
            dtstart = self.parse_dt(row.get("start", ""))
            if not title or not dtstart or dtstart < now:
                continue

            dtend = self.parse_dt(row.get("end", "")) or dtstart
            url = urljoin(self.page_url, row.get("url", ""))
            events.append(
                {
                    "title": title,
                    "dtstart": dtstart,
                    "dtend": dtend,
                    "url": url,
                    "uid": f"{row.get('eid') or row.get('id')}@{self.domain}",
                }
            )

        return events


if __name__ == "__main__":
    WaterfrontTorontoScraper.main()

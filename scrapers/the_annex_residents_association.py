#!/usr/bin/env python3
"""Synthetic recurring board meetings for The Annex Residents' Association."""

from __future__ import annotations

from calendar import monthcalendar, THURSDAY
from datetime import date, datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lib.base import BaseScraper


class TheAnnexResidentsAssociationScraper(BaseScraper):
    name = "The Annex Residents' Association"
    domain = "theara.org"
    timezone = "America/Toronto"
    contact_url = "https://www.theara.org/contact_ara"
    default_url = contact_url
    description = (
        "The ARA Board of Directors meets on the second Thursday of every month, "
        "excluding July and August, at 7:00 p.m. Meetings are open to the public."
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def fetch_html(self) -> str:
        req = Request(self.contact_url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def second_thursday(self, year: int, month: int) -> date:
        weeks = monthcalendar(year, month)
        thursdays = [week[THURSDAY] for week in weeks if week[THURSDAY] != 0]
        return date(year, month, thursdays[1])

    def fetch_events(self) -> list[dict]:
        html = self.fetch_html()
        marker = "second Thursday of every month (excluding July and August) at 7:00 p.m."
        if marker not in html:
            raise ValueError("Expected published recurring board-meeting rule not found")

        tz = ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        start_month = date(today.year, today.month, 1)
        events = []

        for offset in range(self.months_ahead + 1):
            year = start_month.year + ((start_month.month - 1 + offset) // 12)
            month = ((start_month.month - 1 + offset) % 12) + 1
            if month in (7, 8):
                continue
            day = self.second_thursday(year, month)
            dtstart = datetime(day.year, day.month, day.day, 19, 0, tzinfo=tz)
            dtend = datetime(day.year, day.month, day.day, 20, 30, tzinfo=tz)
            if dtend < datetime.now(tz):
                continue
            events.append(
                {
                    "title": "ARA Board Meeting",
                    "dtstart": dtstart,
                    "dtend": dtend,
                    "url": self.contact_url,
                    "location": "Location announced by email / Zoom",
                    "description": self.description,
                    "uid": f"ara-board-{day.isoformat()}@{self.domain}",
                }
            )

        return events


if __name__ == "__main__":
    TheAnnexResidentsAssociationScraper.main()

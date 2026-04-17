#!/usr/bin/env python3
"""Scraper for OCAD University public events and exhibitions."""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import base64
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from icalendar import Calendar

from lib.base import BaseScraper


class OCADUScraper(BaseScraper):
    name = "OCAD University"
    domain = "ocadu.ca"
    timezone = "America/Toronto"
    listing_url = "https://www.ocadu.ca/events"

    def fetch_listing(self) -> str:
        return self.fetch_text_with_curl(self.listing_url, referer="https://www.ocadu.ca/")

    def fetch_detail(self, url: str) -> str:
        return self.fetch_text_with_curl(url, referer=self.listing_url)

    def extract_event_urls(self, html_text: str) -> list[str]:
        soup = BeautifulSoup(html_text, "html.parser")
        urls: list[str] = []
        seen: set[str] = set()

        for link in soup.select(".news-title a[href^='/events-and-exhibitions/']"):
            href = link.get("href")
            if not href:
                continue
            full_url = urljoin(self.listing_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            urls.append(full_url)

        return urls

    def parse_calendar_payload(self, soup: BeautifulSoup) -> tuple[datetime | None, datetime | None]:
        add_to_calendar = soup.select_one("a[href^='data:text/calendar'][href*='base64,']")
        if not add_to_calendar:
            return None, None

        href = add_to_calendar.get("href", "")
        payload = href.split("base64,", 1)[-1]
        if not payload:
            return None, None

        try:
            cal = Calendar.from_ical(base64.b64decode(payload))
        except Exception:
            return None, None

        for component in cal.walk("VEVENT"):
            dtstart = component.decoded("DTSTART", None)
            dtend = component.decoded("DTEND", None)
            return dtstart, dtend

        return None, None

    @staticmethod
    def clean_text(node) -> str:
        if not node:
            return ""
        text = node.get_text(" ", strip=True)
        return re.sub(r"\s+", " ", unescape(text)).strip()

    def parse_detail(self, url: str, html_text: str) -> dict | None:
        soup = BeautifulSoup(html_text, "html.parser")

        title_node = soup.select_one("h1.pageheader--title") or soup.select_one("h1")
        title = self.clean_text(title_node)
        if not title:
            return None

        dtstart, dtend = self.parse_calendar_payload(soup)
        if not dtstart:
            return None

        info_panel = soup.select_one(".pageheader--information.desktop-only") or soup.select_one(".pageheader--information.mobile-only")
        location = ""
        website_url = ""
        if info_panel:
            location_label = info_panel.select_one("label.location")
            if location_label and location_label.parent:
                location = self.clean_text(location_label.parent)
                location = re.sub(r"^Information\s*", "", location)
                location = re.sub(r"^location\s*", "", location, flags=re.I)

            website_label = info_panel.select_one("label.event-website")
            if website_label and website_label.parent:
                website_link = website_label.parent.select_one("a[href]")
                if website_link:
                    website_url = website_link.get("href", "").strip()

        description_parts: list[str] = []
        headline = soup.select_one(".pageheader--headline p")
        headline_text = self.clean_text(headline)
        if headline_text:
            description_parts.append(headline_text)

        for block in soup.select(".field--paragraph.field--text-long"):
            text = self.clean_text(block)
            if text and text not in description_parts:
                description_parts.append(text)

        description = "\n\n".join(description_parts).strip()

        if hasattr(dtstart, "tzinfo") and dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=ZoneInfo(self.timezone))
        if dtend and hasattr(dtend, "tzinfo") and dtend.tzinfo is None:
            dtend = dtend.replace(tzinfo=ZoneInfo(self.timezone))

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend or dtstart,
            "location": location,
            "url": website_url or url,
            "description": description,
            "uid": f"{url.rstrip('/').split('/')[-1]}@{self.domain}",
        }

    def fetch_events(self) -> list[dict]:
        listing_html = self.fetch_listing()
        event_urls = self.extract_event_urls(listing_html)
        now = datetime.now(ZoneInfo(self.timezone))
        events: list[dict] = []

        for url in event_urls:
            try:
                detail_html = self.fetch_detail(url)
                event = self.parse_detail(url, detail_html)
            except Exception as exc:
                self.logger.warning(f"Failed to parse {url}: {exc}")
                continue

            if not event:
                continue

            dtend = event.get("dtend") or event["dtstart"]
            if hasattr(dtend, "tzinfo") and dtend.tzinfo is None:
                dtend = dtend.replace(tzinfo=ZoneInfo(self.timezone))
            if dtend < now:
                continue

            events.append(event)

        return events


if __name__ == "__main__":
    OCADUScraper.main()

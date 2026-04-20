#!/usr/bin/env python3
"""Scraper for Japanese Canadian Cultural Centre events."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import unquote, urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from lib.base import BaseScraper


def _clean(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


class JCCCScraper(BaseScraper):
    name = "Japanese Canadian Cultural Centre"
    domain = "jccc.on.ca"
    timezone = "America/Toronto"
    page_url = "https://jccc.on.ca/visit/events"
    default_url = page_url
    default_location = "Japanese Canadian Cultural Centre"
    max_pages = 10
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def __init__(self):
        super().__init__()
        self.tz = ZoneInfo(self.timezone)

    def fetch_html(self, url: str) -> str:
        response = requests.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.text

    def listing_url(self, page: int) -> str:
        return f"{self.page_url}?page={page}"

    def parse_listing_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards = []
        for article in soup.select("article.node--type-event"):
            title_el = article.select_one("h2 a")
            if not title_el:
                continue
            title = _clean(title_el.get_text(" ", strip=True))
            url = urljoin(self.page_url, title_el.get("href", ""))
            date_texts = [
                _clean(node.get_text(" ", strip=True))
                for node in article.select(".field--name-field-dates .field__item")
                if _clean(node.get_text(" ", strip=True))
            ]
            if not title or not url or not date_texts:
                continue
            cards.append({"title": title, "url": url, "date_texts": date_texts})
        return cards

    def parse_datetime(self, value: str) -> datetime:
        for fmt in ("%B %d, %Y %I:%M%p", "%b %d, %Y %I:%M%p"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=self.tz)
            except ValueError:
                continue
        raise ValueError(f"Unrecognized datetime string: {value}")

    def parse_date(self, value: str) -> date:
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Unrecognized date string: {value}")

    def parse_date_entry(self, text: str) -> tuple[date | datetime, date | datetime]:
        text = _clean(text)

        match = re.fullmatch(
            r"([A-Za-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2}[ap]m)\s*-\s*"
            r"([A-Za-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2}[ap]m)",
            text,
            re.I,
        )
        if match:
            start, end = match.groups()
            return self.parse_datetime(start), self.parse_datetime(end)

        match = re.fullmatch(
            r"([A-Za-z]+ \d{1,2}, \d{4})\s+(\d{1,2}:\d{2}[ap]m)\s*-\s*(\d{1,2}:\d{2}[ap]m)",
            text,
            re.I,
        )
        if match:
            day, start_time, end_time = match.groups()
            return (
                self.parse_datetime(f"{day} {start_time}"),
                self.parse_datetime(f"{day} {end_time}"),
            )

        match = re.fullmatch(
            r"([A-Za-z]+ \d{1,2}, \d{4})\s*-\s*([A-Za-z]+ \d{1,2}, \d{4})",
            text,
            re.I,
        )
        if match:
            start, end = match.groups()
            start_date = self.parse_date(start)
            end_date = self.parse_date(end) + timedelta(days=1)
            return start_date, end_date

        match = re.fullmatch(
            r"([A-Za-z]+ \d{1,2})\s*-\s*([A-Za-z]+ \d{1,2}, \d{4})",
            text,
            re.I,
        )
        if match:
            start_partial, end_full = match.groups()
            end_date = self.parse_date(end_full)
            start_date = self.parse_date(f"{start_partial}, {end_date.year}")
            return start_date, end_date + timedelta(days=1)

        match = re.fullmatch(r"([A-Za-z]+ \d{1,2}, \d{4})", text, re.I)
        if match:
            start_date = self.parse_date(match.group(1))
            return start_date, start_date + timedelta(days=1)

        raise ValueError(f"Unrecognized date string: {text}")

    def event_is_current_or_future(self, dtstart: date | datetime, dtend: date | datetime) -> bool:
        now = datetime.now(self.tz)
        if isinstance(dtstart, datetime):
            end_dt = dtend if isinstance(dtend, datetime) else datetime.combine(dtend, datetime.min.time()).replace(tzinfo=self.tz)
            return end_dt >= now
        return dtend > now.date()

    def sort_key(self, value: date | datetime) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.combine(value, datetime.min.time()).replace(tzinfo=self.tz)

    def parse_data_uri_location(self, article: BeautifulSoup) -> str:
        link = article.select_one('a.dropdown-item[href^="data:text/calendar"]')
        if not link:
            return self.default_location
        href = link.get("href", "")
        payload = unquote(href.split(",", 1)[1]) if "," in href else ""
        match = re.search(r"^LOCATION:(.+)$", payload, re.M)
        return _clean(match.group(1)) if match else self.default_location

    def parse_detail_page(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one("article.node--type-event")
        if not article:
            return {"description": "", "categories": [], "location": self.default_location}

        description = ""
        body = article.select_one(".field--name-body.field--type-text-with-summary")
        if body:
            description = _clean(body.get_text("\n", strip=True))

        categories = []
        for link in article.select('a[href*="/taxonomy/term/"]'):
            label = _clean(link.get_text(" ", strip=True))
            if label and label not in categories:
                categories.append(label)

        return {
            "description": description,
            "categories": categories,
            "location": self.parse_data_uri_location(article),
        }

    def fetch_events(self) -> list[dict]:
        listing_items: dict[str, dict] = {}
        for page in range(self.max_pages):
            cards = self.parse_listing_page(self.fetch_html(self.listing_url(page)))
            if not cards:
                break
            for card in cards:
                entry = listing_items.setdefault(
                    card["url"],
                    {"title": card["title"], "url": card["url"], "date_texts": []},
                )
                for date_text in card["date_texts"]:
                    if date_text not in entry["date_texts"]:
                        entry["date_texts"].append(date_text)

        events = []
        for item in listing_items.values():
            detail = self.parse_detail_page(self.fetch_html(item["url"]))
            description_parts = []
            if detail["description"]:
                description_parts.append(detail["description"])
            if detail["categories"]:
                description_parts.append(f"Categories: {', '.join(detail['categories'])}")
            description = "\n\n".join(description_parts)

            for date_text in item["date_texts"]:
                dtstart, dtend = self.parse_date_entry(date_text)
                if not self.event_is_current_or_future(dtstart, dtend):
                    continue
                events.append(
                    {
                        "title": item["title"],
                        "dtstart": dtstart,
                        "dtend": dtend,
                        "url": item["url"],
                        "location": detail["location"],
                        "description": description,
                    }
                )

        return sorted(events, key=lambda event: self.sort_key(event["dtstart"]))


if __name__ == "__main__":
    JCCCScraper.main()

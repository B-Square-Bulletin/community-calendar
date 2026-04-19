#!/usr/bin/env python3
"""
Scraper for Luma collection pages.

Luma collection pages expose only a teaser slice of events in JSON-LD, but the
page also embeds a calendar API id that can be used to fetch the full future
collection via Luma's public calendar endpoint. This adapter derives that id
from the public page and emits normalized ICS with per-event URLs intact.

Usage:
    python scrapers/luma_collection.py \
        --url "https://luma.com/plutotoronto" \
        --name "Pluto Toronto" \
        --timezone "America/Toronto" \
        --output cities/toronto/luma_pluto_toronto.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from lib import BaseScraper


CALENDAR_APP_ARG_RE = re.compile(r'app-argument=luma://calendar/(cal-[A-Za-z0-9]+)')
CALENDAR_API_ID_RE = re.compile(r'"calendar_api_id":"(cal-[A-Za-z0-9]+)"')
API_URL = "https://api2.luma.com/calendar/get-items"


def _names(value: Any) -> list[str]:
    """Extract organizer/performer names from a JSON-LD value."""
    items = value if isinstance(value, list) else [value]
    names = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get('name', '')).strip()
            if name and name not in names:
                names.append(name)
        elif isinstance(item, str):
            name = item.strip()
            if name and name not in names:
                names.append(name)
    return names


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _location_string(value: Any) -> str:
    """Build a location string from Luma geo_address_info."""
    if not isinstance(value, dict):
        return ""

    label = _clean_text(value.get("address"))
    short_address = _clean_text(value.get("short_address"))
    city_state = _clean_text(value.get("city_state"))

    if label and short_address and label not in short_address:
        base = f"{label}, {short_address}"
    else:
        base = label or short_address

    if city_state and city_state not in base:
        return f"{base}, {city_state}" if base else city_state
    return base


def _iso_datetime(value: Any) -> Optional[datetime]:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _event_url(value: Any) -> Optional[str]:
    text = _clean_text(value)
    if not text:
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"https://luma.com/{text.lstrip('/')}"


def _price_text(ticket_info: Any) -> Optional[str]:
    if not isinstance(ticket_info, dict):
        return None
    if ticket_info.get("is_free"):
        return "Free"

    price = ticket_info.get("price")
    if not isinstance(price, dict):
        return None

    cents = price.get("cents")
    currency = _clean_text(price.get("currency")).upper()
    if cents is None:
        return None

    try:
        amount = float(cents) / 100.0
    except (TypeError, ValueError):
        return None

    if currency:
        return f"{currency} {amount:.2f}"
    return f"{amount:.2f}"


class LumaCollectionScraper(BaseScraper):
    """Scrape a Luma collection page via Luma's public collection API."""

    name = "Luma Collection"
    domain = "luma.com"
    timezone = "America/Toronto"

    def __init__(
        self,
        url: str,
        source_name: Optional[str] = None,
        timezone_name: str = "America/Toronto",
        default_url: Optional[str] = None,
        pagination_limit: int = 100,
    ):
        super().__init__()
        self.url = url.rstrip("/")
        if source_name:
            self.name = source_name
        self.timezone = timezone_name
        if default_url:
            self.default_url = default_url
        self.pagination_limit = pagination_limit

    def fetch_events(self) -> list[dict[str, Any]]:
        html_text = self.fetch_text_with_curl(
            self.url,
            accept="text/html,application/xhtml+xml",
        )
        calendar_api_id = self._extract_calendar_api_id(html_text)
        if not calendar_api_id:
            self.logger.warning("No Luma calendar_api_id found at %s", self.url)
            return []

        events = []
        seen = set()
        now = datetime.now(timezone.utc)
        for entry in self._fetch_entries(calendar_api_id):
            parsed = self._parse_entry(entry, now)
            if parsed:
                key = parsed.get("uid") or parsed.get("url") or parsed.get("title")
                if key in seen:
                    continue
                seen.add(key)
                events.append(parsed)

        self.logger.info(
            "Found %s future events from %s via %s",
            len(events),
            self.url,
            calendar_api_id,
        )
        return events

    def _extract_calendar_api_id(self, html_text: str) -> Optional[str]:
        for pattern in (CALENDAR_APP_ARG_RE, CALENDAR_API_ID_RE):
            match = pattern.search(html_text)
            if match:
                return match.group(1)
        return None

    def _fetch_entries(self, calendar_api_id: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            params = [
                f"calendar_api_id={calendar_api_id}",
                f"pagination_limit={self.pagination_limit}",
                "period=future",
            ]
            if cursor:
                params.append(f"pagination_cursor={cursor}")

            body = self.fetch_text_with_curl(
                f"{API_URL}?{'&'.join(params)}",
                accept="application/json,text/plain,*/*",
                referer=self.url,
            )
            payload = json.loads(body)
            page_entries = payload.get("entries") or []
            if not isinstance(page_entries, list):
                break
            entries.extend(page_entries)

            if not payload.get("has_more"):
                break

            cursor = _clean_text(payload.get("next_cursor"))
            if not cursor:
                break

        return entries

    def _parse_entry(self, item: Any, now: datetime) -> Optional[dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        event = item.get("event")
        if not isinstance(event, dict):
            return None

        dtstart = _iso_datetime(event.get("start_at"))
        if not dtstart:
            return None
        if dtstart < now:
            return None

        dtend = _iso_datetime(event.get("end_at"))

        title = _clean_text(event.get("name")) or "Untitled"
        location = _location_string(event.get("geo_address_info"))
        event_url = _event_url(event.get("url"))

        organizers = _names(item.get("hosts"))
        tags = _names(item.get("tags"))
        price = _price_text(item.get("ticket_info"))
        detail_lines = []
        if organizers:
            detail_lines.append(f"Hosted by: {', '.join(organizers)}")
        if tags:
            detail_lines.append(f"Tags: {', '.join(tags)}")
        if price:
            detail_lines.append(f"Tickets: {price}")
        if item.get("guest_count") is not None:
            detail_lines.append(f"Interested: {item['guest_count']}")

        image_url = _event_url(event.get("cover_url"))
        uid = _clean_text(event.get("api_id") or item.get("api_id") or event_url) or None

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "location": location,
            "description": "\n\n".join(detail_lines).strip(),
            "url": event_url,
            "uid": uid,
            "image_url": image_url,
        }


def main():
    parser = argparse.ArgumentParser(description="Scrape Luma collection pages")
    parser.add_argument("--url", required=True, help="Luma collection page URL")
    parser.add_argument("--name", default="Luma Collection", help="Source display name")
    parser.add_argument("--timezone", default="America/Toronto", help="IANA timezone for emitted ICS")
    parser.add_argument("--default-url", help="Explicit fallback URL when a specific event URL is missing")
    parser.add_argument("--pagination-limit", type=int, default=100, help="Items to request per API page")
    parser.add_argument("--output", "-o", help="Output ICS file")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    scraper = LumaCollectionScraper(
        url=args.url,
        source_name=args.name,
        timezone_name=args.timezone,
        default_url=args.default_url,
        pagination_limit=args.pagination_limit,
    )
    scraper.run(args.output)


if __name__ == "__main__":
    main()

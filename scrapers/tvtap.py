#!/usr/bin/env python3
"""
Scraper for Teton Valley Trails and Pathways (TVTAP) events.

TVTAP runs a Gatsby site backed by Contentful. The build emits a static JSON
blob at /page-data/events/page-data.json containing the full
`allContentfulEventPost` collection. We pull that and filter to upcoming
events.

Usage:
    python scrapers/tvtap.py --output cities/tetonvalley/tvtap.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

from lib.base import BaseScraper
from lib.utils import DEFAULT_HEADERS


class TVTAPScraper(BaseScraper):
    """Scraper for TVTAP via the Gatsby+Contentful page-data JSON."""

    name = "Teton Valley Trails & Pathways"
    domain = "tvtap.org"
    timezone = "America/Denver"

    PAGE_DATA_URL = "https://tvtap.org/page-data/events/page-data.json"
    EVENT_BASE_URL = "https://tvtap.org/events"
    DEFAULT_LOCATION = "Teton Valley, Idaho"

    DATE_FORMATS = (
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M%p",
        "%B %d, %Y",
    )

    def fetch_events(self) -> list[dict[str, Any]]:
        self.logger.info(f"Fetching {self.PAGE_DATA_URL}")
        resp = requests.get(self.PAGE_DATA_URL, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        edges = (
            payload.get("result", {})
            .get("data", {})
            .get("allContentfulEventPost", {})
            .get("edges", [])
        )
        self.logger.info(f"Contentful returned {len(edges)} event records")

        tz = ZoneInfo(self.timezone)
        cutoff_past = datetime.now(tz) - timedelta(days=1)

        events: list[dict[str, Any]] = []
        for edge in edges:
            node = edge.get("node") or {}
            parsed = self._parse_node(node, tz)
            if not parsed:
                continue
            if parsed["dtstart"] < cutoff_past:
                continue
            events.append(parsed)

        return events

    def _parse_date(self, raw: Optional[str], tz: ZoneInfo) -> Optional[datetime]:
        if not raw:
            return None
        raw = raw.strip()
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=tz)
            except ValueError:
                continue
        self.logger.warning(f"Could not parse date: {raw!r}")
        return None

    def _parse_node(self, node: dict, tz: ZoneInfo) -> Optional[dict[str, Any]]:
        title = (node.get("title") or "").strip()
        if not title:
            return None

        dtstart = self._parse_date(node.get("date"), tz)
        if not dtstart:
            return None

        dtend = self._parse_date(node.get("endDate"), tz)
        slug = node.get("slug")
        url = f"{self.EVENT_BASE_URL}/{slug}/" if slug else self.EVENT_BASE_URL

        excerpt = (node.get("excerpt") or "").strip()

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": url,
            "location": self.DEFAULT_LOCATION,
            "description": excerpt,
        }


if __name__ == "__main__":
    TVTAPScraper.main()

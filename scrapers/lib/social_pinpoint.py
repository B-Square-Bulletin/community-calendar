"""Social Pinpoint / Have Your Say events scraper base.

These pages embed one or more `the_hive_events_feed` blocks whose `blockSets`
payload contains:
  - `eventsUrl`
  - `eventApiParams`

The UI uses those params to POST to the upstream events API. This scraper
extracts the embedded block configs, fetches the underlying JSON, and maps the
results into calendar events.
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .base import BaseScraper

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    text = html_mod.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(text: Any) -> str:
    return html_mod.unescape(text or "").strip()


def _extract_json_object(source: str, start: int) -> Optional[tuple[dict[str, Any], int]]:
    """Parse the JSON object starting at `start`, handling nested braces."""
    if start < 0 or start >= len(source) or source[start] != "{":
        return None

    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(source)):
        ch = source[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                snippet = source[start:idx + 1]
                return json.loads(snippet), idx + 1

    return None


class SocialPinpointScraper(BaseScraper):
    """Reusable scraper for Social Pinpoint / Have Your Say event pages."""

    page_url: str = ""
    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def fetch_html(self, url: str) -> str:
        req = Request(url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def extract_block_sets(self, html: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        marker = "blockSets:"
        pos = 0
        while True:
            pos = html.find(marker, pos)
            if pos == -1:
                break
            brace_start = html.find("{", pos)
            parsed = _extract_json_object(html, brace_start)
            if parsed:
                block, end = parsed
                blocks.append(block)
                pos = end
            else:
                pos = brace_start + 1
        return blocks

    def should_include_block(self, block: dict[str, Any]) -> bool:
        """Keep only current/future event blocks."""
        time_finish = block.get("eventApiParams", {}).get("time_finish")
        if not time_finish:
            return True
        try:
            finish = datetime.strptime(time_finish, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return True
        now = datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)
        return finish >= now

    def expand_api_params(self, params: dict[str, Any]) -> dict[str, str]:
        """Increase the feed limit so we fetch more than the UI card count."""
        expanded = {}
        for key, value in params.items():
            if value is None:
                expanded[key] = ""
            else:
                expanded[key] = str(value)
        expanded["limit"] = "0,200"
        return expanded

    def fetch_api_records(self, events_url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        data = urlencode(self.expand_api_params(params)).encode()
        headers = {
            **self.headers,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": self.page_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        req = Request(events_url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("result", [])

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=ZoneInfo(self.timezone)
            )
        except ValueError:
            return None

    def map_record(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        title = _clean_text(record.get("event_title"))
        dtstart = self._parse_datetime(record.get("event_start_date", ""))
        if not title or not dtstart:
            return None

        now = datetime.now(ZoneInfo(self.timezone))
        dtend = self._parse_datetime(record.get("event_end_date", "")) or dtstart
        if dtend < now:
            return None

        venue = _clean_text(record.get("event_venue"))
        address = _strip_html((record.get("event_address") or {}).get("address", ""))
        event_type = _clean_text(record.get("event_type"))
        if venue and address:
            location = f"{venue}, {address}"
        else:
            location = venue or address
        if not location and event_type.lower() == "online":
            location = "Online"

        description_parts = []
        project_title = _clean_text(record.get("project_title"))
        if project_title:
            description_parts.append(f"Project: {project_title}")
        desc = _strip_html(record.get("event_description", ""))
        if desc:
            description_parts.append(desc)
        if event_type and event_type.lower() != "online":
            description_parts.append(f"Type: {event_type}")
        rsvp = record.get("event_rsvp_link", "")
        if rsvp:
            description_parts.append(f"Registration: {rsvp}")

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": record.get("event_full") or rsvp or record.get("project_url") or self.page_url,
            "location": location,
            "description": "\n\n".join(part for part in description_parts if part),
            "uid": f"{record.get('event_id')}@{self.domain}" if record.get("event_id") else None,
        }

    def fetch_events(self) -> list[dict[str, Any]]:
        html = self.fetch_html(self.page_url)
        blocks = [block for block in self.extract_block_sets(html) if self.should_include_block(block)]
        self.logger.info("Found %d eligible event-feed block(s)", len(blocks))

        seen_event_ids: set[str] = set()
        events: list[dict[str, Any]] = []

        for block in blocks:
            events_url = block.get("eventsUrl")
            params = block.get("eventApiParams") or {}
            if not events_url or not params:
                continue

            try:
                records = self.fetch_api_records(events_url, params)
            except (HTTPError, URLError, TimeoutError) as exc:
                self.logger.error("Failed to fetch %s: %s", events_url, exc)
                continue

            self.logger.info(
                "Fetched %d record(s) from block %s",
                len(records),
                block.get("title") or block.get("description") or "untitled",
            )

            for record in records:
                event_id = str(record.get("event_id") or "")
                if event_id and event_id in seen_event_ids:
                    continue
                parsed = self.map_record(record)
                if not parsed:
                    continue
                if event_id:
                    seen_event_ids.add(event_id)
                events.append(parsed)

        return events

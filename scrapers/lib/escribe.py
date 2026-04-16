"""eScribe meetings calendar scraper base."""

from __future__ import annotations

import html as html_mod
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .base import BaseScraper


def _clean_text(value: Any) -> str:
    text = html_mod.unescape(value or "")
    text = re.sub(r"<br\s*/?>", ", ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


class EScribeScraper(BaseScraper):
    """Reusable scraper for public eScribe meeting calendars."""

    endpoint_url: str = ""
    root_url: str = ""
    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Content-Type": "application/json; charset=UTF-8",
    }

    def build_request_body(self) -> bytes:
        today = datetime.now(ZoneInfo(self.timezone)).date()
        cutoff = today + timedelta(days=self.months_ahead * 31)
        return json.dumps({
            "calendarStartDate": today.isoformat(),
            "calendarEndDate": cutoff.isoformat(),
        }).encode()

    def fetch_records(self) -> list[dict[str, Any]]:
        req = Request(
            self.endpoint_url,
            data=self.build_request_body(),
            headers=self.headers,
            method="POST",
        )
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("d", [])

    def parse_datetime(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=ZoneInfo(self.timezone)
            )
        except ValueError:
            return None

    def map_record(self, record: dict[str, Any]) -> Optional[dict[str, Any]]:
        title = _clean_text(record.get("MeetingName"))
        dtstart = self.parse_datetime(record.get("StartDate", ""))
        if not title or not dtstart:
            return None

        dtend = self.parse_datetime(record.get("EndDate", "")) or dtstart
        if dtend < datetime.now(ZoneInfo(self.timezone)):
            return None

        location = _clean_text(record.get("Description")) or _clean_text(record.get("Location"))

        doc_links = []
        for link in record.get("MeetingDocumentLink") or []:
            label = _clean_text(link.get("Title"))
            url = urljoin(self.root_url, link.get("Url", ""))
            if label and url:
                doc_links.append(f"{label}: {url}")

        description_parts = []
        meeting_type = _clean_text(record.get("MeetingType"))
        if meeting_type and meeting_type != title:
            description_parts.append(f"Meeting type: {meeting_type}")
        if doc_links:
            description_parts.append("\n".join(doc_links[:3]))

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": urljoin(self.root_url, record.get("Url", "")) or self.default_url,
            "location": location,
            "description": "\n\n".join(description_parts),
            "uid": f"{record.get('ID')}@{self.domain}" if record.get("ID") else None,
        }

    def fetch_events(self) -> list[dict[str, Any]]:
        records = self.fetch_records()
        self.logger.info("Fetched %d raw meeting record(s)", len(records))
        events = []
        for record in records:
            parsed = self.map_record(record)
            if parsed:
                events.append(parsed)
        return events

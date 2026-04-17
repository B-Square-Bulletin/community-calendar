"""Base scraper for Wild Apricot RSS event feeds."""

import os
import re
import subprocess
from datetime import timedelta
from html import unescape
from typing import Any, Optional

import feedparser
from bs4 import BeautifulSoup

from .rss import RssScraper


class WildApricotRssScraper(RssScraper):
    """Reusable base for Wild Apricot RSS feeds."""

    rss_fallback_urls: list[str] = []
    debug_file_env: Optional[str] = None
    location_patterns: list[str] = []
    location_split_pattern: str = (
        r",\s+The route\b|,\s+which is\b|,\s+for a total distance\b|"
        r"\. View the map\b|\.\s+The route\b"
    )
    description_cutoffs: list[str] = []

    def fetch_events(self) -> list[dict[str, Any]]:
        content = self._fetch_rss_content()
        feed = feedparser.parse(content)
        self.logger.info(f"Found {len(feed.entries)} entries in RSS feed")

        events = []
        for entry in feed.entries:
            event = self.parse_entry(entry)
            if event:
                events.append(event)
                self.logger.info(f"Found event: {event['title']} on {event['dtstart']}")

        return events

    def _fetch_rss_content(self) -> str:
        urls = self.rss_fallback_urls or [self.rss_url]
        for url in urls:
            self.logger.info(f"Fetching RSS feed: {url}")
            result = subprocess.run(
                ["curl", "-sL", "-A", "Mozilla/5.0", "--max-time", "30", url],
                capture_output=True,
                text=True,
            )
            content = result.stdout or ""
            if result.returncode == 0 and "<rss" in content[:1000]:
                return content

        if self.debug_file_env:
            debug_file = os.environ.get(self.debug_file_env)
            if debug_file and os.path.exists(debug_file):
                self.logger.warning(f"Falling back to local RSS sample: {debug_file}")
                with open(debug_file, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()

        raise RuntimeError(f"Failed to fetch RSS from any known endpoint for {self.name}")

    def parse_entry(self, entry: dict) -> Optional[dict[str, Any]]:
        dt_start = self.parse_rss_date(entry)
        if not dt_start:
            return None

        title = self.clean_title(entry.get("title", ""))
        if not title:
            return None

        description_html = entry.get("description", "") or ""
        text = self.html_to_text(description_html)
        location = self.extract_location(text)
        description = self.clean_description(text)
        dt_end = dt_start + self.default_duration(title, text)

        return {
            "title": title,
            "dtstart": dt_start,
            "dtend": dt_end,
            "url": entry.get("link", ""),
            "location": location,
            "description": description,
        }

    def clean_title(self, title: str) -> str:
        title = re.sub(r"\s*\([^)]+\d{4}\)\s*$", "", title).strip()
        return re.sub(r"\s+", " ", title)

    def html_to_text(self, description_html: str) -> str:
        soup = BeautifulSoup(description_html, "html.parser")
        text = unescape(soup.get_text(" ", strip=True))
        return re.sub(r"\s+", " ", text).strip()

    def extract_location(self, text: str) -> Optional[str]:
        for pattern in self.location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip(" \"'")
                if self.location_split_pattern:
                    location = re.split(
                        self.location_split_pattern,
                        location,
                        maxsplit=1,
                        flags=re.IGNORECASE,
                    )[0]
                location = re.sub(r"\s+", " ", location)
                if 5 < len(location) < 200:
                    return location
        return None

    def clean_description(self, text: str) -> str:
        for cutoff in self.description_cutoffs:
            idx = text.find(cutoff)
            if idx > 0:
                text = text[:idx].strip()
                break
        if len(text) > 700:
            text = text[:700].rstrip() + "..."
        return text

    def default_duration(self, title: str, text: str) -> timedelta:
        return timedelta(hours=2)

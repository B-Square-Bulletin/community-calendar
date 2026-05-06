#!/usr/bin/env python3
"""
Scraper for Bossa Bistro + Lounge's official events pages.

Discovery happens from the public listing page:
https://bossadc.com/events/

Each upcoming event links to a detail page that exposes:
- `time[datetime]` with the event datetime
- a visible `Location:` field (e.g. Downstairs / Upstairs)
- a meta description summarizing the show
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import html
import re
import subprocess
from typing import Any, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


LISTING_URL = "https://bossadc.com/events/"
SITE_URL = "https://bossadc.com"
BASE_LOCATION = "Bossa Bistro + Lounge, 2463 18th Street NW, Washington, DC 20009"


class BossaScraper(BaseScraper):
    name = "Bossa Bistro + Lounge"
    domain = "bossadc.com"
    timezone = "America/New_York"
    default_url = LISTING_URL
    max_workers = 6

    def fetch_events(self) -> list[dict[str, Any]]:
        listing_html = self._fetch_text(LISTING_URL)
        soup = BeautifulSoup(listing_html, "html.parser")
        items = soup.select("ul.tour-dates.current-dates li.group")
        self.logger.info(f"Found {len(items)} upcoming listing rows")

        seeds: list[dict[str, str]] = []
        for item in items:
            link = item.select_one("span.sub-head a")
            room_el = item.select_one("span.main-head")
            if not link:
                continue
            href = link.get("href", "").strip()
            if not href:
                continue
            seeds.append({
                "title": link.get_text(" ", strip=True),
                "url": urljoin(SITE_URL, href),
                "room": room_el.get_text(" ", strip=True) if room_el else "",
            })

        events: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._fetch_detail, seed): seed["url"]
                for seed in seeds
            }
            for future in as_completed(futures):
                event = future.result()
                if event:
                    events.append(event)

        return sorted(events, key=lambda e: e["dtstart"])

    def _fetch_detail(self, seed: dict[str, str]) -> Optional[dict[str, Any]]:
        detail_html = self._fetch_text(seed["url"], referer=LISTING_URL)
        soup = BeautifulSoup(detail_html, "html.parser")
        time_el = soup.select_one('time[datetime]')
        if not time_el:
            return None

        dt_raw = (time_el.get("datetime") or "").strip()
        try:
            dtstart = datetime.strptime(dt_raw, "%Y-%m-%d %H:%M").replace(
                tzinfo=ZoneInfo(self.timezone)
            )
        except ValueError:
            return None

        now = datetime.now(ZoneInfo(self.timezone))
        if dtstart < now - timedelta(hours=4):
            return None

        title_el = soup.select_one("h1.entry-title") or soup.select_one("h1.page-title")
        title = title_el.get_text(" ", strip=True) if title_el else seed["title"]

        room = self._extract_labeled_value(soup, "Location:") or seed["room"]
        location = f"{room}, {BASE_LOCATION}" if room else BASE_LOCATION

        description = self._build_description(soup)
        image_url = self._extract_meta_content(soup, "property", "og:image")

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtstart + timedelta(hours=3),
            "url": seed["url"],
            "location": location,
            "description": description,
            "image_url": image_url,
        }

    def _fetch_text(self, url: str, referer: str = "") -> str:
        # Bossa's ModSecurity blocks the generic Mozilla user-agent path that
        # our shared curl helper uses. A minimal Accept header succeeds.
        cmd = ["curl", "-sL", "-H", "Accept: text/html", "--max-time", "30"]
        if referer:
            cmd.extend(["-e", referer])
        cmd.append(url)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if result.returncode != 0 or not result.stdout:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"curl fetch failed for {url}: {stderr or result.returncode}")
        return result.stdout

    def _build_description(self, soup: BeautifulSoup) -> str:
        parts: list[str] = []

        meta_desc = self._extract_meta_content(soup, "name", "description")
        if meta_desc:
            parts.append(self._clean_text(meta_desc))

        cost = self._find_prefixed_text(soup, "Cost:")
        if cost:
            parts.append(cost)

        more_info = self._find_prefixed_text(soup, "More info:")
        if more_info:
            parts.append(more_info)

        return " | ".join(parts)

    @staticmethod
    def _extract_meta_content(
        soup: BeautifulSoup,
        attr_name: str,
        attr_value: str,
    ) -> str:
        meta = soup.find("meta", attrs={attr_name: attr_value})
        return meta.get("content", "").strip() if meta else ""

    @staticmethod
    def _extract_labeled_value(soup: BeautifulSoup, label: str) -> str:
        for paragraph in soup.select("p"):
            span = paragraph.find("span")
            if not span:
                continue
            if span.get_text(" ", strip=True) != label:
                continue
            text = paragraph.get_text(" ", strip=True)
            value = text.replace(label, "", 1).strip()
            return value
        return ""

    def _find_prefixed_text(self, soup: BeautifulSoup, prefix: str) -> str:
        for paragraph in soup.select("p"):
            text = self._clean_text(paragraph.get_text(" ", strip=True))
            if text.startswith(prefix):
                return text
        return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text


if __name__ == "__main__":
    BossaScraper.main()

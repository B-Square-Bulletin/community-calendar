#!/usr/bin/env python3
"""
Scraper for UC Davis Arts calendar
https://arts.ucdavis.edu/calendar

Provides ICS feed at monthly URLs.
"""

import sys

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])

from lib import IcsScraper
from lib.timeutil import utc_now


class UCDavisArtsScraper(IcsScraper):
    """Scraper for UC Davis Arts calendar."""

    name = "UC Davis Arts"
    domain = "arts.ucdavis.edu"

    BASE_URL = "https://arts.ucdavis.edu/calendar/ical"

    def get_ics_urls(self) -> list[str]:
        """Generate monthly ICS URLs."""
        urls = []
        now = utc_now()

        for i in range(self.months_ahead + 1):
            year = now.year + (now.month + i - 1) // 12
            month = (now.month + i - 1) % 12 + 1
            urls.append(f"{self.BASE_URL}/{year}-{month:02d}")

        return urls


if __name__ == "__main__":
    UCDavisArtsScraper.main()

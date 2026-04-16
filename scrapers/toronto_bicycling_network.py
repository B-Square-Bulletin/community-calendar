#!/usr/bin/env python3
"""Toronto Bicycling Network via Wild Apricot RSS."""

import sys
from datetime import timedelta

sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.wild_apricot_rss import WildApricotRssScraper


class TorontoBicyclingNetworkScraper(WildApricotRssScraper):
    name = "Toronto Bicycling Network"
    domain = "tbn.ca"
    rss_url = "https://tbn.ca/events/RSS"
    timezone = "America/Toronto"
    debug_file_env = "TBN_RSS_FILE"
    rss_fallback_urls = [
        "https://tbn.ca/events/RSS",
        "https://www.tbn.ca/widget/events/RSS",
        "http://tbn.ca/page-1856786/EventModule/7161113/RSS",
    ]
    location_patterns = [
        r"Starting Point:\s*([^.<]+)",
        r"\bThis ride starts from\s+([^.<]+)",
        r"\bis located at\s+([^.<]+)",
        r"\bMeet [^.]*? at\s+([^.<]+)",
        r"\blocated at\s+([^.<]+)",
    ]
    description_cutoffs = [
        "If you have not registered for the ride",
        "PLEASE REGISTER",
        "REMINDER: DON'T FORGET TO REGISTER",
        "Questions or suggestions",
        "Not a member, but you want to try this out?",
        "To join the club rides, you must be a member",
    ]

    def default_duration(self, title: str, text: str) -> timedelta:
        blob = f"{title} {text}".lower()
        if any(term in blob for term in ["dining", "dinner", "lunch", "social", "meeting"]):
            return timedelta(hours=2)
        if any(term in blob for term in ["ride", "tourist", "cruise", "cycling", "bike", "hike", "walk", "ski", "skate"]):
            return timedelta(hours=3)
        return timedelta(hours=2)


if __name__ == "__main__":
    TorontoBicyclingNetworkScraper.main()

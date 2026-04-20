#!/usr/bin/env python3
"""
Scraper/normalizer for Luma ICS feeds.

Luma's public ICS feeds often omit the standard URL property while embedding
the event-specific link in the description preamble:

    Get up-to-date information at: https://luma.com/abcdef12

This adapter fetches the raw ICS feed, extracts that per-event URL, writes it
into the URL field, and emits normalized ICS for the standard pipeline.

Usage:
    python scrapers/luma.py \
        --url "https://api2.luma.com/ics/get?entity=discover&id=discplace-Cx3JMS6vXKAbhV5" \
        --name "Luma Toronto Discover" \
        --timezone "America/Toronto" \
        --output cities/toronto/luma_toronto_discover.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import argparse
import logging
import re

from lib import IcsScraper


URL_LINE_RE = re.compile(r'^\s*Get up-to-date information at:\s*(https?://\S+)\s*', re.IGNORECASE)
MORE_INFO_RE = re.compile(r'^\s*More info:\s*(https?://\S+)\s*', re.IGNORECASE)


class LumaScraper(IcsScraper):
    """Normalize Luma ICS feeds so event-specific URLs are populated."""

    name = "Luma"
    domain = "luma.com"
    timezone = "America/Toronto"

    def __init__(self, ics_url: str, source_name: str, timezone_name: str, fallback_url: str | None = None):
        super().__init__()
        self.ics_url = ics_url
        self.name = source_name
        self.timezone = timezone_name
        if fallback_url:
            self.default_url = fallback_url

    def transform_event(self, event: dict) -> dict:
        description = event.get('description') or ''
        url = event.get('url') or ''

        lines = description.splitlines()
        if lines:
            first = lines[0].strip()
            match = URL_LINE_RE.match(first) or MORE_INFO_RE.match(first)
            if match and not url:
                event['url'] = match.group(1).rstrip('.,);]')
                lines = lines[1:]

        while lines and not lines[0].strip():
            lines = lines[1:]

        event['description'] = '\n'.join(lines).strip()
        return event


def main():
    parser = argparse.ArgumentParser(description="Normalize Luma ICS feeds")
    parser.add_argument('--url', required=True, help='Raw Luma ICS URL')
    parser.add_argument('--name', required=True, help='Source display name')
    parser.add_argument('--timezone', default='America/Toronto', help='IANA timezone for emitted ICS')
    parser.add_argument('--fallback-url', help='Optional source-level fallback URL')
    parser.add_argument('--output', '-o', help='Output ICS file')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    scraper = LumaScraper(
        ics_url=args.url,
        source_name=args.name,
        timezone_name=args.timezone,
        fallback_url=args.fallback_url,
    )
    scraper.run(args.output)


if __name__ == '__main__':
    main()

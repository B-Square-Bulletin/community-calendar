#!/usr/bin/env python3
"""Seed the feeds table from feeds.txt for a given city.

Usage: SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/seed_feeds_from_txt.py <city>

Parses cities/<city>/feeds.txt and inserts each entry into the feeds table.
Skips entries that already exist (matched by city + url).
"""

import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, "scrapers")
from lib.feed_utils import parse_feeds_txt


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/seed_feeds_from_txt.py <city>"
        )
        sys.exit(1)

    city = sys.argv[1]
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")

    if not supabase_url or not service_key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        sys.exit(1)

    feeds_path = os.path.join("cities", city, "feeds.txt")
    if not os.path.exists(feeds_path):
        print(f"Not found: {feeds_path}")
        sys.exit(1)

    feeds = parse_feeds_txt(feeds_path)
    if not feeds:
        print(f"No feeds found in {feeds_path}")
        sys.exit(1)

    print(f"Parsed {len(feeds)} feeds from {feeds_path}")

    inserted = 0
    skipped = 0
    errors = 0

    for feed in feeds:
        url = feed.get("url") or feed.get("path")
        row = {
            "city": city,
            "url": url,
            "name": feed["name"],
            "feed_type": feed["type"],
            "status": "active",
        }
        if feed.get("scraper_cmd"):
            row["scraper_cmd"] = feed["scraper_cmd"]

        data = json.dumps(row).encode()
        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/feeds",
            data=data,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=ignore-duplicates,return=minimal",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 201:
                    inserted += 1
                    print(f"  + {feed['name']}")
                else:
                    skipped += 1
                    print(f"  = {feed['name']} (already exists)")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if "duplicate" in body.lower() or e.code == 409:
                skipped += 1
                print(f"  = {feed['name']} (already exists)")
            else:
                errors += 1
                print(f"  ! {feed['name']}: {e.code} {body}")

    print(f"\nDone: {inserted} inserted, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()

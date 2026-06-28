#!/usr/bin/env python3
"""One-time seed: parse all feeds.txt files and insert into feeds table.

Usage: SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/seed_feeds_table.py

Parses each cities/*/feeds.txt and inserts rows into the feeds table.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path


def main():
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")

    if not supabase_url or not service_key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        sys.exit(1)

    sys.path.insert(0, 'scrapers')
    from lib.feed_utils import parse_feeds_txt

    all_feeds = []
    for feeds_file in sorted(Path('cities').glob('*/feeds.txt')):
        city = feeds_file.parent.name
        feeds = parse_feeds_txt(str(feeds_file))
        # Attach city to each feed
        for f in feeds:
            url = f.get('url') or f.get('path')
            feed_type = f['type']
            # Detect curator feeds
            if feed_type == 'ics_url' and 'my-picks' in url:
                feed_type = 'curator'
            f['city'] = city
            f['url'] = url
            f['feed_type'] = feed_type
        all_feeds.extend(feeds)
        print(f"{city}: {len(feeds)} feeds")

    print(f"\nTotal: {len(all_feeds)} feeds")

    # Insert in batches
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    batch_size = 50
    inserted = 0
    for i in range(0, len(all_feeds), batch_size):
        batch = all_feeds[i:i+batch_size]
        # Build rows for Supabase
        rows = []
        for f in batch:
            row = {
                "city": f["city"],
                "url": f["url"],
                "name": f["name"],
                "feed_type": f["feed_type"],
            }
            if f.get("scraper_cmd"):
                row["scraper_cmd"] = f["scraper_cmd"]
            rows.append(row)

        body = json.dumps(rows).encode()
        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/feeds",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
            inserted += len(rows)
            print(f"  Inserted {inserted}/{len(all_feeds)}")
        except urllib.error.URLError as e:
            error_body = e.read().decode() if hasattr(e, 'read') else str(e)
            print(f"  Error at batch {i}: {error_body}")
            sys.exit(1)

    print(f"\nDone: {inserted} feeds inserted")


if __name__ == '__main__':
    main()

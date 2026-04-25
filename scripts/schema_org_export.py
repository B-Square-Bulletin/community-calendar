#!/usr/bin/env python3
"""Export community calendar events as schema.org-compliant JSON-LD.

Usage:
  python scripts/schema_org_export.py --city toronto --category "Music / Concerts" --limit 10
  python scripts/schema_org_export.py --city toronto  # all categories
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse

SUPABASE_URL = "https://dzpdualvwspgqghrysyz.supabase.co"
SUPABASE_KEY = "sb_publishable_NnzobdoFNU39fjs84UNq8Q_X45oiMG5"

# Map our categories to schema.org event types
# https://schema.org/Event and subtypes
CATEGORY_TO_SCHEMA_TYPE = {
    "Music / Concerts": "MusicEvent",
    "Dance / Performance": "DanceEvent",
    "Comedy / Improv": "ComedyEvent",
    "Education / Workshops": "EducationEvent",
    "Food / Drink": "FoodEvent",
    "Sports / Fitness": "SportsEvent",
    "Film / Cinema": "ScreeningEvent",
    "Books / Literature / Poetry": "LiteraryEvent",
}


def parse_location(loc_str):
    """Parse a location string into a schema.org Place object."""
    if not loc_str:
        return None

    # Try to split "Venue, Address" patterns
    parts = [p.strip() for p in loc_str.split(",", 1)]
    place = {
        "@type": "Place",
        "name": parts[0],
    }
    if len(parts) > 1:
        place["address"] = {
            "@type": "PostalAddress",
            "streetAddress": parts[1].strip(),
        }
    return place


def event_to_jsonld(event):
    """Convert a single event record to a schema.org JSON-LD object."""
    category = event.get("category") or ""
    schema_type = CATEGORY_TO_SCHEMA_TYPE.get(category, "Event")

    item = {
        "@type": schema_type,
        "name": event["title"],
        "startDate": event["start_time"],
        "url": event.get("url"),
    }

    if event.get("end_time") and event["end_time"] != event["start_time"]:
        item["endDate"] = event["end_time"]

    if event.get("description"):
        item["description"] = event["description"]

    if event.get("location"):
        item["location"] = parse_location(event["location"])

    if event.get("image_url"):
        item["image"] = event["image_url"]

    if event.get("source_urls"):
        # Provide all known URLs as sameAs
        urls = list(event["source_urls"].values())
        if len(urls) == 1:
            item["sameAs"] = urls[0]
        elif len(urls) > 1:
            item["sameAs"] = urls

    # eventAttendanceMode — all our events are offline
    item["eventAttendanceMode"] = "https://schema.org/OfflineEventAttendanceMode"

    # Remove None values
    return {k: v for k, v in item.items() if v is not None}


def fetch_events(city, category=None, limit=50):
    """Fetch events from Supabase."""
    params = {
        "select": "*",
        "city": f"eq.{city}",
        "start_time": "gte.2026-04-21",
        "order": "start_time.asc",
        "limit": str(limit),
    }
    if category:
        params["category"] = f"eq.{category}"

    url = f"{SUPABASE_URL}/rest/v1/events?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Export events as schema.org JSON-LD")
    parser.add_argument("--city", required=True)
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    events = fetch_events(args.city, args.category, args.limit)
    if not events:
        print("No events found.", file=sys.stderr)
        sys.exit(1)

    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Community Calendar: {args.city.title()}"
              + (f" — {args.category}" if args.category else ""),
        "numberOfItems": len(events),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "item": event_to_jsonld(e),
            }
            for i, e in enumerate(events)
        ],
    }

    print(json.dumps(jsonld, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

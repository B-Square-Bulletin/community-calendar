#!/usr/bin/env python3
"""Generate per-city RSS feeds for GitHub Pages.

Two feeds per city, written to rss/:
  rss/<city>-full.xml   — every upcoming event (next 90 days), sorted by start
  rss/<city>-latest.xml — newly discovered events (first seen this build)

Grouping is a consumer concern only: items collapse one-per-stored-Group using
the route's ``duplicate_group`` and render the route's canonical
``duplicate_group_representative``. RSS never recomputes similarity, location,
or grouping. A grouped item lists its suppressed members as ``<category>``
elements so the next build still knows every member UID.

State model: the previous build's committed rss/<city>-full.xml lists every
event UID known then — item GUIDs plus each grouped item's member categories —
so "new" = current UIDs minus the previous known UIDs, and suppressed Group
members are not re-announced. The previous -latest.xml supplies pubDates for
items still in the window, so an item keeps its first-seen timestamp across
builds. No storage beyond the feeds themselves.

Usage (run after ics_to_json.py, before the metadata commit):
    python scripts/generate_rss.py <city>
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
SITE_BASE = os.environ.get("SITE_BASE", "https://b-square-bulletin.github.io/community-calendar")
FULL_WINDOW_DAYS = 90
LATEST_MAX_ITEMS = 100


def parse_dt(value):
    """Parse an events.json start_time into an aware datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def event_guid(ev):
    """The feed GUID for one listing: its source_uid, or a title+time fallback."""
    uid = ev.get("source_uid")
    if uid:
        return uid
    basis = f"{ev.get('title', '')}|{ev.get('start_time', '')}"
    return hashlib.md5(basis.encode("utf-8")).hexdigest()


def group_key(ev):
    """Identity of the stored Group a listing belongs to.

    Rows sharing a non-NULL ``duplicate_group`` are one Group. A NULL group is
    one row is one group, so Separate rows never collapse — keyed per row so two
    unrelated NULL rows cannot share a bucket.
    """
    group_id = ev.get("duplicate_group")
    if group_id:
        return ("group", group_id)
    return ("row", event_guid(ev))


def select_representative(members):
    """The route's canonical representative for a Group, chosen, not computed.

    ``duplicate_group_representative`` is the route's deterministic survivor;
    RSS renders that listing so the feed matches the app card. A Separate row
    carries no representative and is its own representative. If a declared
    representative is somehow absent from the window, fall back to the smallest
    GUID so the feed stays deterministic.
    """
    by_guid = {event_guid(ev): ev for _start, ev in members}
    declared = next(
        (
            ev.get("duplicate_group_representative")
            for _start, ev in members
            if ev.get("duplicate_group_representative")
        ),
        None,
    )
    if declared and declared in by_guid:
        return by_guid[declared]
    return min((ev for _start, ev in members), key=event_guid)


def group_upcoming(upcoming):
    """Collapse routed listings to one entry per stored Group, sorted by start.

    Each entry carries the representative listing, its GUID, and every member
    GUID (sorted) so callers can render one item while keeping membership
    visible for the next build's new-item computation.
    """
    buckets: dict[tuple[str, str], list[tuple[datetime, dict]]] = {}
    order: list[tuple[str, str]] = []
    for start, ev in upcoming:
        key = group_key(ev)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append((start, ev))

    groups = []
    for key in order:
        members = buckets[key]
        representative = select_representative(members)
        groups.append(
            {
                "key": key,
                "representative": representative,
                "guid": event_guid(representative),
                "member_guids": sorted({event_guid(ev) for _start, ev in members}),
                "start": next(start for start, ev in members if ev is representative),
            }
        )
    groups.sort(key=lambda group: group["start"])
    return groups


def esc(text):
    return html.escape(text or "", quote=False)


def render_item(ev, guid, pub_dt, app_link, member_guids=(), desc_cap=1000):
    start = parse_dt(ev.get("start_time"))
    datestr = (
        start.strftime("%a %b %-d, %-I:%M %p")
        if start and not ev.get("all_day")
        else (start.strftime("%a %b %-d") if start else "")
    )
    title_bits = [ev.get("title", "Untitled")]
    if datestr:
        title_bits.append(datestr)
    loc = (ev.get("location") or "").split(",")[0].strip()
    if loc:
        title_bits.append(loc)
    desc = (ev.get("description") or "").strip()
    source = ev.get("source") or ""
    if source:
        desc = f"{desc}\n\nSource: {source}" if desc else f"Source: {source}"
    link = ev.get("url") or app_link
    # Suppressed Group members ride along as categories so the previous full
    # feed still records every UID the route knows about.
    categories = "".join(f"      <category>{esc(uid)}</category>\n" for uid in member_guids)
    return (
        "    <item>\n"
        f"      <title>{esc(' — '.join(title_bits))}</title>\n"
        f"      <link>{esc(link)}</link>\n"
        f'      <guid isPermaLink="false">{esc(guid)}</guid>\n'
        f"      <pubDate>{format_datetime(pub_dt)}</pubDate>\n"
        f"      <description>{esc(desc[:desc_cap])}</description>\n"
        f"{categories}"
        "    </item>\n"
    )


def render_feed(title, description, app_link, self_url, items):
    now = format_datetime(datetime.now(UTC))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{esc(title)}</title>\n"
        f"    <link>{esc(app_link)}</link>\n"
        f'    <atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>\n'
        f"    <description>{esc(description)}</description>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n" + "".join(items) + "  </channel>\n"
        "</rss>\n"
    )


def read_feed_state(path):
    """Return (guid→pubDate, known_uids) from an existing feed, or ({}, set()).

    ``known_uids`` is every UID the feed references: the item GUIDs plus the
    ``<category>`` member UIDs a grouped item carries, so suppressed members
    stay known across builds.
    """
    if not path.exists():
        return {}, set()
    text = path.read_text(encoding="utf-8", errors="replace")
    pubdates = {}
    known = set()
    for m in re.finditer(r"<guid[^>]*>([^<]+)</guid>\s*<pubDate>([^<]+)</pubDate>", text):
        guid = html.unescape(m.group(1))
        pubdates[guid] = m.group(2)
        known.add(guid)
    for m in re.finditer(r"<category>([^<]+)</category>", text):
        known.add(html.unescape(m.group(1)))
    return pubdates, known


def pub_key(entry, now):
    """Sort key for latest-feed entries; unparseable pubDates sort last."""
    try:
        return parsedate_to_datetime(entry[0])
    except Exception:
        return now


def generate(city, events, outdir, state_dir, now):
    """Write both feeds for ``city``; return (full_items, latest_items).

    All inputs are injected so tests can drive two consecutive builds with a
    fixed clock, passing the first build's outdir as the second's state_dir.
    """
    horizon = now + timedelta(days=FULL_WINDOW_DAYS)
    upcoming = []
    for ev in events:
        start = parse_dt(ev.get("start_time"))
        if start and now - timedelta(hours=12) <= start <= horizon:
            upcoming.append((start, ev))
    upcoming.sort(key=lambda pair: pair[0])

    groups = group_upcoming(upcoming)

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    state_dir = Path(state_dir)
    full_path = outdir / f"{city}-full.xml"
    latest_path = outdir / f"{city}-latest.xml"
    app_link = f"{SITE_BASE}/xmlui/index.html?city={city}"
    city_title = city.capitalize()

    _, prev_full_known = read_feed_state(state_dir / full_path.name)
    prev_latest, _ = read_feed_state(state_dir / latest_path.name)

    # Full feed: one item per stored Group, pubDate = the event start.
    full_items = [
        render_item(
            group["representative"],
            group["guid"],
            group["start"],
            app_link,
            member_guids=[uid for uid in group["member_guids"] if uid != group["guid"]],
            desc_cap=300,
        )
        for group in groups
    ]
    full_path.write_text(
        render_feed(
            f"{city_title} Community Calendar — all upcoming events",
            f"Every event in the next {FULL_WINDOW_DAYS} days, regenerated daily.",
            app_link,
            f"{SITE_BASE}/rss/{full_path.name}",
            full_items,
        )
    )

    # Latest feed: a Group is new while any of its member UIDs is unknown to the
    # previous build's full feed (so a newly joining member is announced and a
    # suppressed one is not); otherwise carry the first-seen pubDate.
    latest = []
    for group in groups:
        members = set(group["member_guids"])
        if members and not members <= prev_full_known:
            pub_str = format_datetime(now)
        elif group["guid"] in prev_latest:
            pub_str = prev_latest[group["guid"]]
        else:
            continue
        latest.append((pub_str, group))

    latest.sort(key=lambda entry: pub_key(entry, now), reverse=True)
    latest = latest[:LATEST_MAX_ITEMS]

    latest_items = []
    for pub_str, group in latest:
        item = render_item(
            group["representative"],
            group["guid"],
            now,
            app_link,
            member_guids=[uid for uid in group["member_guids"] if uid != group["guid"]],
        )
        item = re.sub(r"<pubDate>[^<]+</pubDate>", f"<pubDate>{pub_str}</pubDate>", item)
        latest_items.append(item)

    latest_path.write_text(
        render_feed(
            f"{city_title} Community Calendar — new events",
            "Events newly added to the calendar, most recent first.",
            app_link,
            f"{SITE_BASE}/rss/{latest_path.name}",
            latest_items,
        )
    )
    return full_items, latest_items


def main():
    parser = argparse.ArgumentParser(description="Generate per-city RSS feeds")
    parser.add_argument("city")
    parser.add_argument("--events", help="Path to events.json (default cities/<city>/events.json)")
    parser.add_argument("--outdir", default=str(ROOT / "rss"))
    parser.add_argument(
        "--state-dir",
        default=str(ROOT / "rss"),
        help="Where to read the previous build's feeds (the latest-feed "
        "baseline). Defaults to the tracked rss/ directory, which is "
        "CI-owned published state; local runs pass --outdir elsewhere "
        "while still diffing against the real baseline here.",
    )
    args = parser.parse_args()

    events_path = Path(args.events) if args.events else ROOT / "cities" / args.city / "events.json"
    if not events_path.exists():
        print(f"generate_rss: {events_path} not found, skipping {args.city}")
        return 0

    events = json.loads(events_path.read_text())
    full_items, latest_items = generate(
        args.city, events, Path(args.outdir), Path(args.state_dir), datetime.now(UTC)
    )

    print(f"generate_rss: {args.city}: full={len(full_items)} latest={len(latest_items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

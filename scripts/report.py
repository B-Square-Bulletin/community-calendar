#!/usr/bin/env python3
"""
Generate feed health report after aggregation runs.

Scans .ics files in each city directory (produced by the workflow from
both URL downloads and scrapers) and counts future events in each.

Updates report.json with:
- Per-city, per-feed event counts
- Historical data (unlimited)
- Anomaly detection

Also POSTs health data to Supabase (dual-write transition).
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date, timezone, timedelta
from typing import Optional
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, "scrapers")
from lib.feed_utils import parse_feeds_txt

DEFAULT_TIMEZONE = "America/Los_Angeles"


def get_city_timezone(city, _project_root=None):
    """Load timezone string from cities/{city}/city.conf.

    Returns the timezone string, or None if city.conf is missing.
    _project_root is for testing; production callers omit it.
    """
    if _project_root is None:
        _project_root = Path(__file__).parent.parent
    conf = _project_root / "cities" / city / "city.conf"
    if conf.exists():
        for line in conf.read_text().splitlines():
            if line.startswith("# timezone:"):
                return line.split(":", 1)[1].strip()
    return None


# Anomaly thresholds
DROP_THRESHOLD = 0.5  # 50% drop from previous
MIN_EVENTS_FOR_DROP = 5  # Only flag drops if previous had at least this many


def count_future_events_in_ics(filepath: str) -> tuple[int, Optional[str]]:
    """Count VEVENT entries with future DTSTART in an ICS file."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except FileNotFoundError:
        return 0, "file_not_found"
    except Exception as e:
        return 0, str(e)[:100]

    count = 0
    for match in re.finditer(
        r"BEGIN:VEVENT\r?\n(.*?)\r?\nEND:VEVENT", content, re.DOTALL
    ):
        event = match.group(1)
        dt_match = re.search(r"DTSTART[^:]*:(\d{8}(?:T\d{6}Z?)?)", event)
        if not dt_match:
            continue
        dt_str = dt_match.group(1)
        try:
            if dt_str.endswith("Z"):
                dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
            elif "T" in dt_str:
                dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S").replace(
                    tzinfo=timezone.utc
                )
            else:
                dt = datetime.strptime(dt_str, "%Y%m%d").replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                count += 1
        except ValueError:
            count += 1  # count if unparseable, to be safe
    return count, None


def detect_anomalies(feed_name: str, current: int, history: list[dict]) -> list[dict]:
    """Detect anomalies for a feed. Returns list of anomaly dicts."""
    anomalies = []

    if not history:
        return anomalies

    prev = None
    for h in reversed(history):
        if h.get("error") is None:
            prev = h
            break

    if prev is None:
        return anomalies

    prev_count = prev["count"]

    if current == 0 and prev_count > 0:
        anomalies.append(
            {
                "type": "zero_events",
                "message": f"Feed returned 0 events (was {prev_count})",
                "severity": "high",
            }
        )
    elif prev_count >= MIN_EVENTS_FOR_DROP and current < prev_count:
        drop_pct = (prev_count - current) / prev_count
        if drop_pct >= DROP_THRESHOLD:
            anomalies.append(
                {
                    "type": "significant_drop",
                    "message": f"Events dropped {drop_pct:.0%} ({prev_count} → {current})",
                    "severity": "medium",
                }
            )

    return anomalies


def load_report(report_path: str) -> dict:
    """Load existing report or create new one."""
    try:
        with open(report_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"generated": None, "cities": {}, "anomalies": []}


def save_report(report: dict, report_path: str):
    """Save report to JSON file."""
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)


def update_report(cities: list[str], report_path: str = "report.json"):
    """Main function to update the report."""
    report = load_report(report_path)
    today = date.today().isoformat()
    now = datetime.now().isoformat()

    # Filter out stale cities no longer being processed (e.g. fork only
    # builds Bloomington but report.json still has upstream's 9 cities).
    cities_set = set(cities)
    report["cities"] = {
        city: data for city, data in report["cities"].items() if city in cities_set
    }
    report["anomalies"] = [
        a for a in report["anomalies"] if a.get("city") in cities_set
    ]

    all_anomalies = []

    for city in cities:
        city_dir = f"cities/{city}"

        if city not in report["cities"]:
            report["cities"][city] = {"feeds": {}}

        city_data = report["cities"][city]

        # Scan all .ics files in the city directory (skip combined.ics)
        for ics_path in sorted(glob.glob(f"{city_dir}/*.ics")):
            basename = os.path.basename(ics_path).replace(".ics", "")
            if basename == "combined":
                continue

            feed_name = basename

            if feed_name not in city_data["feeds"]:
                city_data["feeds"][feed_name] = {"history": []}

            feed_data = city_data["feeds"][feed_name]
            count, error = count_future_events_in_ics(ics_path)

            if error:
                all_anomalies.append(
                    {
                        "date": today,
                        "city": city,
                        "feed": feed_name,
                        "type": "error",
                        "message": f"Error: {error}",
                        "severity": "high",
                    }
                )
            else:
                anomalies = detect_anomalies(feed_name, count, feed_data["history"])
                for a in anomalies:
                    a["date"] = today
                    a["city"] = city
                    a["feed"] = feed_name
                    all_anomalies.append(a)

            entry = {"date": today, "count": count}
            if error:
                entry["error"] = error

            if feed_data["history"] and feed_data["history"][-1]["date"] == today:
                feed_data["history"][-1] = entry
            else:
                feed_data["history"].append(entry)

        # Remove feeds from report that no longer have .ics files
        current_basenames = {
            os.path.basename(p).replace(".ics", "")
            for p in glob.glob(f"{city_dir}/*.ics")
        } - {"combined"}
        stale = [k for k in city_data["feeds"] if k not in current_basenames]
        for k in stale:
            del city_data["feeds"][k]

    # Update anomalies (keep all historical anomalies)
    existing_today = {
        (a["city"], a["feed"], a["type"])
        for a in report["anomalies"]
        if a.get("date") == today
    }

    for a in all_anomalies:
        key = (a["city"], a["feed"], a["type"])
        if key not in existing_today:
            report["anomalies"].append(a)

    # URL quality analysis from events.json
    for city in cities:
        city_dir = f"cities/{city}"
        events_json = f"cities/{city}/events.json"
        try:
            with open(events_json, "r") as f:
                events = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        urls_with_url = [e for e in events if e.get("url")]
        total = len(urls_with_url)
        unique_urls = len(set(e["url"] for e in urls_with_url))

        # Group by domain
        from urllib.parse import urlparse

        by_domain = {}
        for e in urls_with_url:
            try:
                domain = urlparse(e["url"]).hostname or e["url"]
            except Exception:
                domain = e["url"]
            if domain not in by_domain:
                by_domain[domain] = {"urls": set(), "count": 0}
            by_domain[domain]["urls"].add(e["url"])
            by_domain[domain]["count"] += 1

        # Generic URLs: domains where all events share one URL, with >5 events
        generic_domains = []
        generic_count = 0
        for domain, info in by_domain.items():
            if len(info["urls"]) == 1 and info["count"] > 5:
                generic_domains.append(
                    {
                        "domain": domain,
                        "events": info["count"],
                        "url": list(info["urls"])[0],
                    }
                )
                generic_count += info["count"]
        generic_domains.sort(key=lambda g: -g["events"])

        # HTTP domains
        http_domains = set()
        http_count = 0
        for e in urls_with_url:
            if e["url"].startswith("http://"):
                try:
                    http_domains.add(urlparse(e["url"]).hostname)
                except Exception:
                    pass
                http_count += 1

        # Source specificity
        by_source = {}
        for e in urls_with_url:
            src = e.get("source") or "(none)"
            if src not in by_source:
                by_source[src] = {"count": 0, "urls": set()}
            by_source[src]["count"] += 1
            by_source[src]["urls"].add(e["url"])
        source_specificity = sorted(
            [
                {
                    "source": src,
                    "events": info["count"],
                    "unique_urls": len(info["urls"]),
                    "specificity_pct": round(len(info["urls"]) / info["count"] * 100),
                }
                for src, info in by_source.items()
            ],
            key=lambda x: -x["events"],
        )[:15]

        # Category breakdown
        by_category = {}
        for e in events:
            cat = e.get("category") or "(uncategorized)"
            by_category[cat] = by_category.get(cat, 0) + 1
        category_breakdown = sorted(
            [{"category": cat, "count": cnt} for cat, cnt in by_category.items()],
            key=lambda x: -x["count"],
        )

        # Image coverage
        with_image = sum(1 for e in events if e.get("image_url"))
        by_source_images = {}
        for e in events:
            src = e.get("source") or "(none)"
            if src not in by_source_images:
                by_source_images[src] = {"total": 0, "with_image": 0}
            by_source_images[src]["total"] += 1
            if e.get("image_url"):
                by_source_images[src]["with_image"] += 1
        image_by_source = sorted(
            [
                {
                    "source": src,
                    "total": info["total"],
                    "with_image": info["with_image"],
                }
                for src, info in by_source_images.items()
                if info["with_image"] > 0
            ],
            key=lambda x: -x["with_image"],
        )

        report["cities"][city]["categories"] = category_breakdown
        report["cities"][city]["images"] = {
            "total": len(events),
            "with_image": with_image,
            "by_source": image_by_source,
        }

        # Geo-filtered events (from combine_ics.py sidecar)
        geo_filtered_path = f"{city_dir}/geo_filtered.json"
        try:
            with open(geo_filtered_path, "r") as f:
                geo_filtered = json.load(f)
            if geo_filtered:
                report["cities"][city]["geo_filtered"] = geo_filtered
            else:
                report["cities"][city].pop("geo_filtered", None)
        except (FileNotFoundError, json.JSONDecodeError):
            report["cities"][city].pop("geo_filtered", None)

        report["cities"][city]["url_quality"] = {
            "total_with_url": total,
            "total_events": len(events),
            "unique_urls": unique_urls,
            "generic_count": generic_count,
            "generic_domains": generic_domains,
            "http_count": http_count,
            "http_domains": len(http_domains),
            "source_specificity": source_specificity,
        }

    # Timezone anomaly detection
    for city in cities:
        events_json = f"cities/{city}/events.json"
        try:
            with open(events_json, "r") as f:
                events = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        tz_name = get_city_timezone(city)
        if tz_name is None:
            continue
        tz = ZoneInfo(tz_name)
        ref = datetime(2026, 3, 15, 12, 0, 0, tzinfo=tz)
        offset_hours = int(ref.utcoffset().total_seconds() / 3600)

        by_source = {}
        for e in events:
            st = e.get("start_time", "")
            if "T" not in st:
                continue
            src = e.get("source", "unknown")
            try:
                hour = int(st[11:13])
                minute = int(st[14:16])
            except (ValueError, IndexError):
                continue
            by_source.setdefault(src, []).append(
                {
                    "hour": hour,
                    "minute": minute,
                    "title": e.get("title", "")[:60],
                    "start_time": st[:16],
                }
            )

        tz_anomalies = []
        for src, entries in by_source.items():
            if len(entries) < 3:
                continue
            suspicious = [e for e in entries if 0 <= e["hour"] < 5]
            if len(suspicious) < 2:
                continue
            shifted = [((e["hour"] - offset_hours) % 24) for e in suspicious]
            daytime = sum(1 for h in shifted if 8 <= h <= 18)
            if daytime >= len(suspicious) * 0.7:
                samples = []
                for e, sh in zip(suspicious[:5], shifted[:5]):
                    samples.append(
                        {
                            "start_time": e["start_time"],
                            "shows": f"{e['hour']:02d}:{e['minute']:02d}",
                            "likely": f"{sh:02d}:{e['minute']:02d}",
                            "title": e["title"],
                        }
                    )
                tz_anomalies.append(
                    {
                        "source": src,
                        "count": len(suspicious),
                        "total": len(entries),
                        "offset": offset_hours,
                        "samples": samples,
                    }
                )

        if tz_anomalies:
            report["cities"][city]["tz_anomalies"] = tz_anomalies

    # TZID inventory: distinct timezones found in each city's ICS files
    for city in cities:
        city_dir = f"cities/{city}"
        city_tz = get_city_timezone(city)
        tzid_counts = {}  # tzid → {count, files}
        for ics_path in sorted(glob.glob(f"{city_dir}/*.ics")):
            basename = os.path.basename(ics_path)
            if basename == "combined.ics":
                continue
            try:
                with open(ics_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue
            for m in re.finditer(r"DTSTART;TZID=([^:;]+)", content):
                tzid = m.group(1)
                if tzid not in tzid_counts:
                    tzid_counts[tzid] = {"count": 0, "files": set()}
                tzid_counts[tzid]["count"] += 1
                tzid_counts[tzid]["files"].add(basename)
            # Count bare datetimes (no TZID, no Z)
            bare = len(re.findall(r"^DTSTART:\d{8}T\d{6}$", content, re.MULTILINE))
            if bare:
                key = "(bare — assumes city tz)"
                if key not in tzid_counts:
                    tzid_counts[key] = {"count": 0, "files": set()}
                tzid_counts[key]["count"] += bare
                tzid_counts[key]["files"].add(basename)
            # Count UTC datetimes
            utc = len(re.findall(r"^DTSTART:\d{8}T\d{6}Z$", content, re.MULTILINE))
            if utc:
                key = "UTC (Z suffix)"
                if key not in tzid_counts:
                    tzid_counts[key] = {"count": 0, "files": set()}
                tzid_counts[key]["count"] += utc
                tzid_counts[key]["files"].add(basename)

        if tzid_counts:
            inventory = []
            for tzid, info in sorted(tzid_counts.items(), key=lambda x: -x[1]["count"]):
                inventory.append(
                    {
                        "tzid": tzid,
                        "count": info["count"],
                        "files": len(info["files"]),
                        "matches_city": tzid == city_tz,
                        "sample_files": sorted(info["files"])[:5],
                    }
                )
            report["cities"][city]["tzid_inventory"] = {
                "city_timezone": city_tz,
                "distinct_tzids": len(inventory),
                "tzids": inventory,
            }

    report["generated"] = now

    save_report(report, report_path)

    # Dual-write: POST health data to Supabase
    _maybe_post_health(report, cities)

    # Print summary
    print(f"Report updated: {report_path}")
    print(f"Cities: {len(report['cities'])}")
    total_feeds = sum(len(c["feeds"]) for c in report["cities"].values())
    print(f"Total feeds: {total_feeds}")
    if all_anomalies:
        print(f"New anomalies: {len(all_anomalies)}")
        for a in all_anomalies:
            print(f"  [{a['severity']}] {a['city']}/{a['feed']}: {a['message']}")


def _maybe_post_health(report: dict, cities: list[str]):
    """POST health data to Supabase edge function (dual-write transition).

    Skips silently if SUPABASE_URL / SUPABASE_SERVICE_KEY not set.
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        print("Skipping Supabase health post (credentials not configured)")
        return

    edge_url = f"{supabase_url}/functions/v1/report-health"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    for city in cities:
        payload = _build_health_payload(report, city)
        if not payload:
            continue

        body = json.dumps(payload).encode()
        for attempt in range(3):
            try:
                req = urllib.request.Request(edge_url, data=body, headers=headers)
                with urllib.request.urlopen(req) as resp:
                    result = json.loads(resp.read().decode())
                print(
                    f"  ✅ Supabase health post: {city} — "
                    f"inserted={result.get('inserted', '?')}, "
                    f"skipped={result.get('skipped', '?')}"
                )
                break
            except urllib.error.HTTPError as e:
                print(
                    f"  ⚠️  Health post HTTP {e.code} for {city} "
                    f"(attempt {attempt + 1}/3): {e.read().decode()[:200]}"
                )
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                print(
                    f"  ⚠️  Health post failed for {city} (attempt {attempt + 1}/3): {e}"
                )
            if attempt < 2:
                time.sleep(2**attempt)


def _build_health_payload(report: dict, city: str, _project_root=None) -> dict | None:
    """Build the {city, feeds, anomalies} payload for the edge function.

    _project_root is for testing; production callers omit it.
    """
    if city not in report["cities"]:
        return None

    city_data = report["cities"][city]
    feeds_meta = _load_feeds_meta(city)

    # Compute checked_date from city timezone
    tz_name = get_city_timezone(city, _project_root=_project_root)
    if tz_name is None:
        print(f"  ⚠️  No city.conf for {city} — falling back to {DEFAULT_TIMEZONE}")
        tz_name = DEFAULT_TIMEZONE
    try:
        tz = ZoneInfo(tz_name)
        checked_date = datetime.now(tz).strftime("%Y-%m-%d")
    except (KeyError, Exception):
        # ZoneInfoNotFoundError is a KeyError in Python 3.9+
        checked_date = date.today().isoformat()

    feeds_payload = []
    for feed_name, feed_data in city_data.get("feeds", {}).items():
        meta = feeds_meta.get(feed_name, {})

        # Determine latest entry
        history = feed_data.get("history", [])
        latest = history[-1] if history else {}

        feeds_payload.append(
            {
                "feed_name": feed_name,
                "source_name": meta.get("name"),
                "source_url": meta.get("source_url"),
                "feed_type": meta.get("type", "scraper"),
                "scraper_cmd": meta.get("scraper_cmd"),
                "event_count": latest.get("count", 0),
                "error": latest.get("error"),
                "checked_date": checked_date,
            }
        )

    # Anomalies for this city from today
    today_anomalies = [a for a in report.get("anomalies", []) if a.get("city") == city]
    anomalies_payload = []
    for a in today_anomalies:
        anomalies_payload.append(
            {
                "feed_name": a.get("feed", a.get("feed_name", "")),
                "type": a.get("type", ""),
                "severity": a.get("severity", "medium"),
                "message": a.get("message", ""),
                "previous_count": a.get("previous_count"),
                "current_count": a.get("current_count"),
            }
        )

    return {
        "city": city,
        "feeds": feeds_payload,
        "anomalies": anomalies_payload,
    }


def _load_feeds_meta(city: str) -> dict[str, dict]:
    """Parse feeds.txt for a city, returning {basename → metadata} map.

    TODO(Phase 6): Replace with a direct Supabase feeds table query.
    The feeds table is the source of truth; feeds.txt is a generated
    compatibility artifact.  See AGENTS.md and CONTEXT.md.
    """
    feeds_file = Path("cities") / city / "feeds.txt"
    if not feeds_file.exists():
        return {}

    feeds = parse_feeds_txt(str(feeds_file))
    return {f["basename"]: f for f in feeds}


def parse_build_errors(log_path: str) -> list[dict]:
    """Parse build.log for error patterns. Returns list of error dicts."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    errors = []
    today = date.today().isoformat()

    # Patterns that indicate errors
    error_patterns = [
        re.compile(r"error: the following arguments are required", re.IGNORECASE),
        re.compile(r"HTTP Error \d+", re.IGNORECASE),
        re.compile(r"ConnectionError", re.IGNORECASE),
        re.compile(r"Timeout", re.IGNORECASE),
        re.compile(r": error:", re.IGNORECASE),
        re.compile(r"(?<!Timeout)Error:", re.IGNORECASE),
    ]

    # Pattern to extract Python script name from a line
    py_file_pattern = re.compile(r"(\w[\w-]*\.py)")

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Check for traceback blocks
        if "Traceback (most recent call last)" in line:
            # Collect the full traceback through the final error line
            tb_lines = [line]
            j = i + 1
            last_error_line = line
            while j < len(lines):
                tb_line = lines[j].rstrip()
                tb_lines.append(tb_line)
                if tb_line and not tb_line.startswith(" ") and j > i + 1:
                    last_error_line = tb_line
                    break
                j += 1

            # Extract source from traceback file references
            source = None
            for tb in tb_lines:
                m = re.search(r'File ".*?/(\w[\w-]*\.py)"', tb)
                if m:
                    source = m.group(1).replace(".py", "")

            errors.append({"date": today, "line": last_error_line, "source": source})
            i = j + 1
            continue

        # Check single-line error patterns
        for pattern in error_patterns:
            if pattern.search(line):
                # Extract source script name
                source = None
                m = py_file_pattern.search(line)
                if m:
                    source = m.group(1).replace(".py", "")
                # Also check the preceding line for script name context
                if not source and i > 0:
                    m = py_file_pattern.search(lines[i - 1])
                    if m:
                        source = m.group(1).replace(".py", "")

                errors.append({"date": today, "line": line.strip(), "source": source})
                break

        i += 1

    # Deduplicate by (line, source)
    seen = set()
    unique = []
    for e in errors:
        key = (e["line"], e["source"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return unique


def main():
    parser = argparse.ArgumentParser(description="Generate feed health report")
    parser.add_argument(
        "--cities",
        type=str,
        default="santarosa,bloomington,davis",
        help="Comma-separated list of cities",
    )
    parser.add_argument(
        "--output", type=str, default="report.json", help="Output JSON file path"
    )
    parser.add_argument(
        "--build-log",
        type=str,
        default=None,
        help="Path to build.log for error extraction",
    )
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",")]
    update_report(cities, args.output)

    # Parse build errors if log provided
    if args.build_log:
        report = load_report(args.output)
        build_errors = parse_build_errors(args.build_log)
        report["errors"] = build_errors
        save_report(report, args.output)
        if build_errors:
            print(f"Build errors found: {len(build_errors)}")
            for e in build_errors:
                print(f"  [{e.get('source', '?')}] {e['line'][:120]}")
        else:
            print("No build errors found in log.")


if __name__ == "__main__":
    main()

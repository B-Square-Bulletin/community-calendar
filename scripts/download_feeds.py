#!/usr/bin/env python3
"""Download all live ICS feeds for a city.

Usage: python scripts/download_feeds.py <city>

Queries the feeds table in Supabase for active ics_url/curator feeds,
downloads each to an auto-named .ics file in cities/<city>/, and injects
X-SOURCE headers. Falls back to feeds.txt if SUPABASE_URL is not set.
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from feed_slug import slugify
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


def parse_feeds_txt(feeds_file: Path):
    """Parse feeds.txt, yielding (url, friendly_name, fallback_url) tuples.

    Structured comment format:
        # Friendly Name | https://fallback-url/
        https://feed-url/

    A comment line immediately before a URL line is the metadata for that URL.
    Category headers (comments before blank lines or other comments) are ignored.
    """
    pending_name = None
    pending_fallback = None

    with feeds_file.open() as f:
        for line in f:
            stripped = line.strip()

            if stripped.startswith("#"):
                body = stripped[1:].strip()
                if "|" in body:
                    parts = body.split("|", 1)
                    pending_name = parts[0].strip()
                    pending_fallback = parts[1].strip() or None
                else:
                    pending_name = body
                    pending_fallback = None
                continue

            if not stripped or not stripped.startswith("https://"):
                # Blank line or local file ref resets pending comment
                pending_name = None
                pending_fallback = None
                continue

            yield stripped, pending_name, pending_fallback
            pending_name = None
            pending_fallback = None


def inject_source_headers(filepath: Path, friendly_name: str, fallback_url: str | None) -> None:
    """Inject X-SOURCE (and optionally X-SOURCE-URL) into each VEVENT in an ICS file."""
    try:
        with filepath.open("rb") as f:
            raw = f.read()
    except Exception:
        return

    if b"BEGIN:VCALENDAR" not in raw:
        return  # Not valid ICS

    # Detect line ending style from raw bytes
    crlf = b"\r\n" if b"\r\n" in raw else b"\n"

    name_bytes = friendly_name.encode("utf-8")
    headers = b"X-SOURCE:" + name_bytes + crlf
    if fallback_url:
        headers += b"X-SOURCE-URL:" + fallback_url.encode("utf-8") + crlf

    marker = b"BEGIN:VEVENT" + crlf
    parts = raw.split(marker)

    result = [parts[0]]
    for part in parts[1:]:
        vevent_head = part.split(b"END:VEVENT")[0]
        if b"X-SOURCE:" not in vevent_head:
            result.append(headers + part)
        else:
            result.append(part)

    with filepath.open("wb") as out:
        out.write(marker.join(result))


def fetch_feeds_from_db(city: str):
    """Query the feeds table for active ics_url and curator feeds.
    Returns list of (url, name, fallback_url) tuples, or None if DB not available."""
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        return None

    query_url = (
        f"{supabase_url}/rest/v1/feeds"
        f"?select=id,url,name,status,fallback_url"
        f"&city=eq.{city}"
        f"&status=in.(active,pending)"
        f"&feed_type=in.(ics_url,curator)"
        f"&order=name.asc"
    )
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    req = urllib.request.Request(query_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            feeds = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"  ⚠️  Failed to query feeds table: {e}")
        return None

    return feeds  # list of dicts with id, url, name, status


def mark_feeds_active(feeds_to_activate):
    """Mark pending feeds as active after successful download."""
    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_url or not service_key:
        return
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for feed in feeds_to_activate:
        patch_url = f"{supabase_url}/rest/v1/feeds?id=eq.{feed['id']}"
        data = json.dumps({"status": "active"}).encode()
        req = urllib.request.Request(patch_url, data=data, headers=headers, method="PATCH")
        try:
            urllib.request.urlopen(req)
            print(f"  ✅ Marked active: {feed['name']}")
        except urllib.error.URLError as e:
            print(f"  ⚠️  Failed to mark active: {feed['name']}: {e}")


# HACK: browncounty.com's MEC v7.25.0 exports UTC values but labels them with
# TZID=America/Indiana/Indianapolis, making every event 4 hours early (EDT).
# Fix: parse as stated TZ → convert to UTC → use that UTC value as local time.
# Other MEC feeds (e.g. York University v7.17.1) use proper UTC "Z" format and
# are NOT affected — but watch for this bug if we add more MEC feeds with TZID.
_MEC_TZ_FIX_URLS = {
    "browncounty.com",
}


def _needs_mec_tz_fix(url: str) -> bool:
    return any(domain in url for domain in _MEC_TZ_FIX_URLS)


def fix_mec_timezone(filepath: Path) -> None:
    """Rewrite DTSTART/DTEND in an ICS file to undo MEC's double timezone conversion."""
    with filepath.open(encoding="utf-8", errors="ignore") as f:
        content = f.read()

    def fix_dt_line(match):
        field = match.group(1)  # DTSTART or DTEND
        tzid = match.group(2)  # e.g. America/Indiana/Indianapolis
        timestr = match.group(3)  # e.g. 20260404T080000
        try:
            tz = ZoneInfo(tzid)
            dt = datetime.strptime(timestr, "%Y%m%dT%H%M%S").replace(tzinfo=tz)
            # The UTC value is what the local time should actually be
            corrected = dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%S")
            return f"{field};TZID={tzid}:{corrected}"
        except Exception:
            return match.group(0)

    fixed = re.sub(r"(DTSTART|DTEND);TZID=([^:]+):(\d{8}T\d{6})", fix_dt_line, content)

    with filepath.open("w", encoding="utf-8") as f:
        f.write(fixed)


USER_AGENT = "Mozilla/5.0 (compatible; CommunityCalendar/1.0)"

# Seconds to wait between consecutive requests to the same host. Localist
# (events.in.gov) throttles when two requests land within the same second,
# causing the alternating pass/fail signature seen in the build report.
_HOST_DELAY_SECONDS = 1.0


class _RateLimited(Exception):
    """HTTP 429 Too Many Requests — retryable."""


def _host_of(url: str) -> str:
    return urlparse(url).netloc


def _retry_if_rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, _RateLimited)


@retry(
    retry=retry_if_exception_type(_RateLimited),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _download_body(url: str) -> bytes:
    """Download a feed body, retrying with exponential backoff on 429/503."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code in (429, 503):
            raise _RateLimited(url) from e
        raise


def fetch_with_curl_fallback(url: str, outfile: Path) -> bytes | None:
    """Download url to outfile, retrying transient 429/503s and falling back to curl.

    urllib exposes the HTTP status code (so we can detect 429/503 and retry);
    curl is the fallback for CDNs that reject urllib's TLS fingerprint.
    """
    # A failed fetch must not leave a stale file from a prior run behind:
    # download_feeds treats a non-empty outfile as success.
    outfile.unlink(missing_ok=True)

    try:
        outfile.write_bytes(_download_body(url))
        return outfile.read_bytes()
    except Exception:
        # Any urllib failure (rate limit, network error, timeout, HTTP error)
        # falls through to curl, which never raises for a single feed.
        pass

    cmd = ["curl", "-sL", "-A", USER_AGENT, "--retry", "3", url, "-o", str(outfile)]
    subprocess.run(cmd)
    if outfile.exists() and outfile.stat().st_size > 0:
        return outfile.read_bytes()
    return None


def download_feeds(city: str) -> None:
    output_dir = Path("cities") / city
    output_dir.mkdir(parents=True, exist_ok=True)

    # Try DB first, fall back to feeds.txt
    db_feeds = fetch_feeds_from_db(city)
    if db_feeds is not None:
        print(f"  Using feeds table ({len(db_feeds)} feeds)")
        feed_list = [(f["url"], f["name"], f.get("fallback_url")) for f in db_feeds]
        pending_feeds = [f for f in db_feeds if f.get("status") == "pending"]
    else:
        feeds_file = Path("cities") / city / "feeds.txt"
        if not feeds_file.exists():
            print(f"No feeds.txt found for {city}")
            return
        feed_list = list(parse_feeds_txt(feeds_file))
        pending_feeds = []
        print(f"  Using feeds.txt ({len(feed_list)} feeds)")

    count = 0
    last_host = None
    for url, friendly_name, fallback_url in feed_list:
        filename = slugify(url) + ".ics"
        outfile = output_dir / filename

        # Throttle consecutive requests to the same host so rate-limited
        # sources (events.in.gov) aren't hammered back-to-back.
        host = _host_of(url)
        if host and host == last_host:
            time.sleep(_HOST_DELAY_SECONDS)
        last_host = host

        fetch_with_curl_fallback(url, outfile)

        # Report result
        if outfile.exists() and outfile.stat().st_size > 0:
            try:
                with outfile.open() as ics:
                    events = ics.read().count("BEGIN:VEVENT")
            except Exception:
                events = 0

            # Inject source headers from feeds.txt metadata
            if friendly_name:
                inject_source_headers(outfile, friendly_name, fallback_url)

            # Fix MEC timezone bug for known-affected feeds
            if _needs_mec_tz_fix(url):
                fix_mec_timezone(outfile)
                print(f"  🔧 Applied MEC timezone fix to {filename}")

            print(
                f"  ✅ {filename}: {events} events"
                f"{' (source: ' + friendly_name + ')' if friendly_name else ''}"
            )
        else:
            print(f"  ❌ {filename}: empty or failed")

        count += 1

    print(f"Downloaded {count} feeds for {city}")

    # Mark pending feeds as active
    if pending_feeds:
        mark_feeds_active(pending_feeds)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/download_feeds.py <city>", file=sys.stderr)
        sys.exit(1)
    download_feeds(sys.argv[1])

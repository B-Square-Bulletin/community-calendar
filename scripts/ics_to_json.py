#!/usr/bin/env python3
"""
Convert ICS calendar files to JSON format for Supabase ingestion.
"""

import argparse
import contextlib
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape as html_unescape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, "scrapers")

from lib.timeutil import parse_naive_ics


def strip_html_tags(text):
    """Remove HTML tags from text, preserving the text content."""
    if not text or "<" not in text:
        return text
    return re.sub(r"<[^>]+>", "", text)


def clean_text(raw):
    """Canonical text cleaning: HTML-unescape, then strip tags.

    This is the one cleaning path shared by the stored event fields and the
    confidence route, so routing sees exactly what the reader sees. The #145
    root cause was routing on the raw ICS ``SUMMARY`` while the stored title
    was cleaned, so an entity-encoded copy never matched its decoded twin.
    """
    return strip_html_tags(html_unescape(raw or ""))


def clean_title(raw):
    """Cleaned title, using the same canonical path as every stored field."""
    return clean_text(raw)


# Default timezone when city.conf is missing or has no timezone
DEFAULT_TIMEZONE = "America/Los_Angeles"


def load_city_timezone(city):
    """Load timezone from cities/{city}/city.conf, fall back to default."""
    if not city:
        return ZoneInfo(DEFAULT_TIMEZONE)
    conf = Path(__file__).parent.parent / "cities" / city / "city.conf"
    if conf.exists():
        for line in conf.read_text().splitlines():
            if line.startswith("# timezone:"):
                tz_name = line.split(":", 1)[1].strip()
                return ZoneInfo(tz_name)
    return ZoneInfo(DEFAULT_TIMEZONE)


def parse_ics_datetime(dt_str, local_tz=None):
    """Parse an ICS datetime string to ISO format string.

    If the input contains a TZID parameter (e.g. ";TZID=America/New_York:20250115T190000"),
    that timezone is used instead of local_tz. This ensures events from other timezones
    are correctly interpreted even when they appear in a different city's calendar.
    """
    if not dt_str:
        return None

    if local_tz is None:
        local_tz = ZoneInfo(DEFAULT_TIMEZONE)

    # Extract TZID parameter if present, then strip params to get bare datetime
    if ";" in dt_str:
        tzid_match = re.search(r"TZID=([^:;]+)", dt_str)
        if tzid_match:
            # Invalid TZID — fall back to city timezone
            with contextlib.suppress(KeyError, ValueError):
                local_tz = ZoneInfo(tzid_match.group(1))
        dt_str = dt_str.split(":")[-1]

    dt_str = dt_str.strip()

    try:
        if dt_str.endswith("Z"):
            # UTC time - convert to city's local time
            dt = parse_naive_ics(dt_str, "%Y%m%dT%H%M%SZ")
            dt = dt.replace(tzinfo=timezone.utc).astimezone(local_tz)
            return dt.isoformat()
        elif "T" in dt_str:
            # Local time (already in correct timezone) - attach tz so offset is included
            dt = parse_naive_ics(dt_str, "%Y%m%dT%H%M%S")
            dt = dt.replace(tzinfo=local_tz)
            return dt.isoformat()
        else:
            # All-day event — anchor to midnight in the city's local timezone
            dt = parse_naive_ics(dt_str, "%Y%m%d")
            dt = dt.replace(tzinfo=local_tz)
            return dt.isoformat()
    except ValueError:
        return None


def is_all_day_event(raw_dt_str):
    """Check if a DTSTART string represents an all-day event (VALUE=DATE, no time component)."""
    if not raw_dt_str:
        return False
    # VALUE=DATE parameter means all-day
    if "VALUE=DATE" in raw_dt_str.upper() and "VALUE=DATE-TIME" not in raw_dt_str.upper():
        return True
    # No T in the value portion means date-only
    value = raw_dt_str.split(":")[-1].strip()
    return "T" not in value and len(value) == 8 and value.isdigit()


def unfold_ics_lines(content):
    """Unfold ICS continuation lines (lines starting with space or tab)."""
    # ICS spec: long lines are folded by inserting CRLF + space/tab
    content = re.sub(r"\r?\n[ \t]", "", content)
    return content


def extract_field(event_content, field_name):
    """Extract a field value from VEVENT content."""
    # Match field with optional parameters: FIELD;PARAM=VALUE:content or FIELD:content
    # Use word boundary or end-of-field-name to avoid X-SOURCE matching X-SOURCE-ID
    pattern = rf"^{field_name}(?:;[^:]*)?:([^\r\n]*)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        value = match.group(1)
        # Unescape ICS escapes
        value = (
            value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
        )
        return value.strip()
    return None


def extract_raw_datetime(event_content, field_name):
    """Extract a raw datetime property line including any TZID parameter.

    Returns the full match (e.g. "DTSTART;TZID=America/New_York:20250115T190000")
    so parse_ics_datetime can extract and use the TZID.
    For bare properties (no params), returns just the value (e.g. "20250115T190000").
    """
    pattern = rf"^({field_name}(?:;[^:]*)?):([^\r\n]*)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        params = match.group(1)  # e.g. "DTSTART;TZID=America/New_York" or "DTSTART"
        value = match.group(2).strip()
        if ";" in params:
            # Has parameters — return full line so parse_ics_datetime can extract TZID
            return params + ":" + value
        return value
    return None


def extract_image_url(event_content):
    """Extract first image URL from ATTACH or vendor image fields."""
    # Match ATTACH with image FMTTYPE
    pattern = r"^ATTACH;[^:]*FMTTYPE=image/[^:]*:(.+)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Match Tockify featured image
    pattern = r"^X-TKF-FEATURED-IMAGE:(.+)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Match LiveWhale image (IU events) - unescape \, and request a larger size
    pattern = r"^X-LIVEWHALE-IMAGE:(.+)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        url = match.group(1).strip().replace("\\,", ",")
        # Replace thumbnail dimensions with a larger display size
        url = re.sub(r"/width/\d+/height/\d+/", "/width/400/height/300/", url)
        return url
    # Match RFC 7986 IMAGE field (e.g. Skedda/Aqus events)
    # Prefer FULLSIZE, accept any display type
    for display in ("fullsize", "badge", "thumbnail", ""):
        pat = (
            rf"^IMAGE;[^:]*DISPLAY={display}[^:]*:(https?://.+)"
            if display
            else r"^IMAGE;[^:]*:(https?://.+)"
        )
        match = re.search(pat, event_content, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    # Match WordPress X-WP-IMAGES-URL (format: size\;url\;w\;h\,...,size\;url\;...)
    pattern = r"^X-WP-IMAGES-URL:(.+)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        raw = match.group(1).strip()
        # Parse comma-separated entries: size\;url\;w\;h
        for size in ("large", "full", "medium"):
            m = re.search(rf"(?:^|,){size}\\;(https?://[^\\,]+)", raw, re.IGNORECASE)
            if m:
                return m.group(1)
    # Match Bedework image (Duke) - relative URL, base is calendar.duke.edu
    pattern = r"^X-BEDEWORK-IMAGE:(/public/Images/.+)"
    match = re.search(pattern, event_content, re.IGNORECASE | re.MULTILINE)
    if match:
        return "https://calendar.duke.edu" + match.group(1).strip()
    return None


def token_set_similarity(a, b):
    """Compare word sets, ignore order. Returns 0-1.
    'Family Storytime' vs 'Bilingual Family Storytime' scores high because
    the shared words dominate. Uses overlap/min-size ratio."""
    from difflib import SequenceMatcher as SM

    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    sorted_inter = " ".join(sorted(intersection))
    remaining_a = " ".join(sorted(words_a - intersection))
    remaining_b = " ".join(sorted(words_b - intersection))
    combined_a = (sorted_inter + " " + remaining_a).strip()
    combined_b = (sorted_inter + " " + remaining_b).strip()
    ratios = [
        SM(None, sorted_inter, combined_a).ratio() if combined_a else 1.0,
        SM(None, sorted_inter, combined_b).ratio() if combined_b else 1.0,
        SM(None, combined_a, combined_b).ratio(),
    ]
    return max(ratios)


# ===========================================================================
# Confidence route (#150): one build-time Merge/Group/Separate decision.
#
# It runs on cleaned events and never deletes a row because of similarity:
# Merge is the exact-full-title equivalence class, Group is similarity plus
# guards and keeps every row. See docs/adr for the two-band split.
# ===========================================================================

# Algorithm namespace. Bump when the decision rules change. A version change
# intentionally changes every duplicate_group id; group ids are not identity.
ROUTE_VERSION = "cr1"

# Title similarity needed to Group. 0.80 recovers the low-scoring true
# duplicates (e.g. the Wine & Paint pair at 0.857) without gathering the
# false-match noise that sits below it.
ROUTE_THRESHOLD = 0.80

# Build invariants. A similarity chain or all-day bucket that blows past these
# bounds is a bug, not a tuning problem, so the build fails closed. The
# comparison budget is ~6x the observed full-artifact comparison count.
ROUTE_MAX_GROUP_SIZE = 25
ROUTE_MAX_COMPARISONS = 250_000

# Squad/gender tokens. `fr` is deliberately excluded: it appears in ordinary
# titles, and a one-sided mismatch blocks Group.
VARIANT_TOKENS = ("jv", "varsity", "freshman", "freshmen", "sophomore", "boys", "girls")

# Street/region abbreviation expansion for location compatibility. Deterministic
# text normalisation only — no geocoding and no network lookup.
_LOCATION_ABBREVIATIONS = {
    "e": "east",
    "w": "west",
    "n": "north",
    "s": "south",
    "st": "street",
    "ave": "avenue",
    "av": "avenue",
    "rd": "road",
    "dr": "drive",
    "blvd": "boulevard",
    "ln": "lane",
    "ct": "court",
    "pl": "place",
    "hwy": "highway",
}

# US state names and codes. A location that names a state is explicitly
# incompatible with one that names a different state: the same street name in
# two states is two venues. Names are canonical, codes map onto them.
_US_STATE_TOKENS = {
    **{
        name: name
        for name in (
            "alabama",
            "alaska",
            "arizona",
            "arkansas",
            "california",
            "colorado",
            "connecticut",
            "delaware",
            "florida",
            "georgia",
            "hawaii",
            "idaho",
            "illinois",
            "indiana",
            "iowa",
            "kansas",
            "kentucky",
            "louisiana",
            "maine",
            "maryland",
            "massachusetts",
            "michigan",
            "minnesota",
            "mississippi",
            "missouri",
            "montana",
            "nebraska",
            "nevada",
            "new hampshire",
            "new jersey",
            "new mexico",
            "new york",
            "north carolina",
            "north dakota",
            "ohio",
            "oklahoma",
            "oregon",
            "pennsylvania",
            "rhode island",
            "south carolina",
            "south dakota",
            "tennessee",
            "texas",
            "utah",
            "vermont",
            "virginia",
            "washington",
            "west virginia",
            "wisconsin",
            "wyoming",
        )
    },
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "new hampshire",
    "nj": "new jersey",
    "nm": "new mexico",
    "ny": "new york",
    "nc": "north carolina",
    "nd": "north dakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhode island",
    "sc": "south carolina",
    "sd": "south dakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "west virginia",
    "wi": "wisconsin",
    "wy": "wyoming",
}

# The source-priority data file is the single source of truth for which
# sources are aggregators (also read by combine_ics.py and xmlui/helpers.js).
_SOURCE_PRIORITY_PATH = Path(__file__).resolve().parent.parent / "source_priority.json"
try:
    AGGREGATORS = set(json.loads(_SOURCE_PRIORITY_PATH.read_text())["aggregators"])
except (OSError, json.JSONDecodeError, KeyError, TypeError):
    AGGREGATORS = set()


class RouteInvariantError(RuntimeError):
    """Raised when the confidence route breaks a build invariant (fail closed)."""


@dataclass(frozen=True)
class RouteOutcome:
    """The route's public decision for one input listing."""

    source_uid: str
    outcome: str  # "merge" | "group" | "separate"
    duplicate_group: str | None
    survivor_uid: str | None
    normalized_title: str
    merged_from: tuple[str, ...] = ()


@dataclass
class RouteResult:
    """Routed events plus the diagnostics later tickets consume."""

    events: list[dict[str, Any]]
    outcomes: list[RouteOutcome]
    diagnostics: dict[str, Any]
    input_events: list[dict[str, Any]]


def normalize_route_title(title):
    """Normalised full title for the exact-title Merge test.

    Entity-decode, strip tags, drop a leading article, lowercase, keep
    alphanumerics. Deliberately no truncation: a 40-character prefix would make
    two unrelated titles compare equal on the destructive Merge path.
    """
    cleaned = clean_title(title)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    for article in ("the ", "a ", "an "):
        if lowered.startswith(article):
            cleaned = cleaned[len(article) :]
            break
    return "".join(c.lower() for c in cleaned if c.isalnum())


def normalize_location(location):
    """Lowercase, strip punctuation, and expand known abbreviations."""
    if not location:
        return ""
    text = re.sub(r"[.,]", " ", location.lower())
    return " ".join(_LOCATION_ABBREVIATIONS.get(token, token) for token in text.split() if token)


def _region_tokens(tokens):
    return {_US_STATE_TOKENS[token] for token in tokens if token in _US_STATE_TOKENS}


def _locations_compatible(a, b):
    """Core location rule; both inputs are non-empty."""
    norm_a, norm_b = normalize_location(a), normalize_location(b)
    if norm_a == norm_b:
        return True
    tokens_a, tokens_b = norm_a.split(), norm_b.split()
    regions_a, regions_b = _region_tokens(tokens_a), _region_tokens(tokens_b)
    if regions_a and regions_b and regions_a != regions_b:
        return False
    shared = [t for t in tokens_a if t in set(tokens_b) and not t.isdigit()]
    number_a = next((t for t in tokens_a if t.isdigit()), None)
    number_b = next((t for t in tokens_b if t.isdigit()), None)
    if number_a and number_b and number_a != number_b:
        return False
    return len(shared) >= 2


def locations_compatible_both(a, b):
    """Merge predicate: a missing location on either side is disqualifying."""
    if not a or not b:
        return False
    return _locations_compatible(a, b)


def locations_compatible_or_empty(a, b):
    """Group predicate: a missing location is never disqualifying."""
    if not a or not b:
        return True
    return _locations_compatible(a, b)


def variant_key(title):
    """The squad/gender designation named by a title, as a sorted token key."""
    words = set(re.split(r"[^a-z0-9]+", (title or "").lower()))
    return ",".join(sorted(token for token in VARIANT_TOKENS if token in words))


def is_all_day_listing(event):
    """All-day flag first; a midnight start is only the fallback when it is absent."""
    flag = event.get("all_day")
    if flag is True:
        return True
    if flag is False:
        return False
    start = event.get("start_time") or ""
    return len(start) >= 16 and start[11:16] == "00:00"


def instant_epoch(event):
    """UTC epoch seconds for a listing's start, or None if unparseable.

    True instant compare: ``18:00+00:00`` and ``14:00-04:00`` are equal.
    """
    start = event.get("start_time") or ""
    try:
        parsed = datetime.fromisoformat(start)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


def structured_source_names(event):
    """Structured source names for a listing.

    Prefers the per-source URL map (already structured). A single source string
    is accepted as one opaque name; a comma-joined legacy string is never split
    back into names, because that text is ambiguous.
    """
    names: list[str] = []
    urls = event.get("source_urls")
    if isinstance(urls, dict):
        names = [name for name in urls if name]
    if names:
        return names
    source = (event.get("source") or "").strip()
    # A lone source string is one opaque name. A comma-joined legacy string is
    # never split back into names, because that text is ambiguous.
    return [source] if source else []


def is_aggregator(source_name):
    """Whether a source is a known aggregator (lower priority for dedup)."""
    return source_name in AGGREGATORS


def _survivor_sort_key(event):
    """Primary sources first, then smallest source_uid, then smallest url."""
    names = structured_source_names(event)
    aggregator_only = bool(names) and all(is_aggregator(name) for name in names)
    return (1 if aggregator_only else 0, event.get("source_uid") or "", event.get("url") or "")


def _group_id(source_uids):
    """Opaque, deterministic, versioned id over sorted surviving member uids."""
    key = "\x1f".join(sorted(source_uids))
    return f"{ROUTE_VERSION}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def _fold_sources(members):
    """Union member sources and URLs, primaries before aggregators."""
    names: list[str] = []
    urls: dict[str, str] = {}
    for member in members:
        member_names = structured_source_names(member)
        for name in member_names:
            if name not in names:
                names.append(name)
        member_urls = member.get("source_urls")
        if isinstance(member_urls, dict):
            for name, url in member_urls.items():
                if name and url and name not in urls:
                    urls[name] = url
        url = member.get("url")
        if url:
            for name in member_names:
                urls.setdefault(name, url)
    primaries = sorted(name for name in names if not is_aggregator(name))
    aggregators = sorted(name for name in names if is_aggregator(name))
    ordered = primaries + aggregators
    return ", ".join(ordered), ({name: urls[name] for name in ordered if name in urls} or None)


def confidence_route(
    events,
    *,
    threshold=ROUTE_THRESHOLD,
    location_guard=True,
    variant_guard=True,
    timed_only_guard=True,
    max_group_size=ROUTE_MAX_GROUP_SIZE,
    max_comparisons=ROUTE_MAX_COMPARISONS,
):
    """Make one deterministic Merge/Group/Separate decision for every listing.

    Pure over a plain event list: no I/O, no database, no network. Merge is an
    exact-full-title equivalence class over both-present compatible locations
    and deletes its non-survivors. Group is a same-instant connected component
    of similarity edges over the survivors, bounded by the guards and the
    component/comparison budgets. Everything else is Separate — authoritative,
    and never re-collapsed downstream.

    Listings without a ``source_uid`` are never merged or grouped (identity is
    never invented from title and time); ``validate_route_result`` fails the
    build closed when any are present.
    """
    input_events = list(events)
    identified = [e for e in input_events if (e.get("source_uid") or "").strip()]
    missing_identity = [e for e in input_events if not (e.get("source_uid") or "").strip()]

    cleaned = [clean_title(event.get("title")) for event in identified]
    normalized = [normalize_route_title(title) for title in cleaned]

    buckets: dict[int, list[int]] = defaultdict(list)
    unparseable = 0
    for index, event in enumerate(identified):
        epoch = instant_epoch(event)
        if epoch is None:
            unparseable += 1
            continue
        buckets[epoch].append(index)

    comparisons = 0

    # Merge: union-find over exact-title edges alone.
    merge_parent = list(range(len(identified)))

    def merge_find(x):
        while merge_parent[x] != x:
            merge_parent[x] = merge_parent[merge_parent[x]]
            x = merge_parent[x]
        return x

    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        by_title: dict[str, list[int]] = defaultdict(list)
        for index in bucket:
            if normalized[index]:
                by_title[normalized[index]].append(index)
        for indices in by_title.values():
            for position_a in range(len(indices)):
                for position_b in range(position_a + 1, len(indices)):
                    comparisons += 1
                    a, b = indices[position_a], indices[position_b]
                    loc_ok = (not location_guard) or locations_compatible_both(
                        identified[a].get("location"), identified[b].get("location")
                    )
                    if loc_ok:
                        merge_parent[merge_find(a)] = merge_find(b)

    merge_classes: dict[int, list[int]] = defaultdict(list)
    for index in range(len(identified)):
        merge_classes[merge_find(index)].append(index)

    survivors: list[int] = []
    deleted: list[int] = []
    merged_from: dict[int, list[str]] = defaultdict(list)
    merge_survivor_of: dict[int, int] = {}
    merge_class_count = 0
    for members in merge_classes.values():
        if len(members) == 1:
            survivors.append(members[0])
            merge_survivor_of[members[0]] = members[0]
            continue
        merge_class_count += 1
        ordered = sorted(members, key=lambda index: _survivor_sort_key(identified[index]))
        survivor = ordered[0]
        survivors.append(survivor)
        for member in members:
            merge_survivor_of[member] = survivor
        for member in ordered[1:]:
            deleted.append(member)
            merged_from[survivor].append(identified[member]["source_uid"])

    # Group: union-find over similarity edges among the survivors only.
    group_parent = list(range(len(survivors)))

    def group_find(x):
        while group_parent[x] != x:
            group_parent[x] = group_parent[group_parent[x]]
            x = group_parent[x]
        return x

    survivor_position = {index: position for position, index in enumerate(survivors)}
    for bucket in buckets.values():
        positions = []
        for index in bucket:
            if index not in survivor_position:
                continue
            if timed_only_guard and is_all_day_listing(identified[index]):
                continue
            positions.append(survivor_position[index])
        for position_a in range(len(positions)):
            for position_b in range(position_a + 1, len(positions)):
                comparisons += 1
                a = survivors[positions[position_a]]
                b = survivors[positions[position_b]]
                if location_guard and not locations_compatible_or_empty(
                    identified[a].get("location"), identified[b].get("location")
                ):
                    continue
                if token_set_similarity(cleaned[a], cleaned[b]) < threshold:
                    continue
                if variant_guard and variant_key(cleaned[a]) != variant_key(cleaned[b]):
                    continue
                group_parent[group_find(positions[position_a])] = group_find(positions[position_b])

    components: dict[int, list[int]] = defaultdict(list)
    for position in range(len(survivors)):
        components[group_find(position)].append(position)

    survivor_group: dict[int, str | None] = dict.fromkeys(survivors)
    group_members: dict[str, list[str]] = {}
    observed_max_group_size = 0
    for component in components.values():
        if len(component) < 2:
            continue
        member_uids = [identified[survivors[position]]["source_uid"] for position in component]
        group_id = _group_id(member_uids)
        group_members[group_id] = sorted(member_uids)
        observed_max_group_size = max(observed_max_group_size, len(component))
        for position in component:
            survivor_group[survivors[position]] = group_id

    # Build the surviving artifact and the per-event outcomes in input order.
    surviving = set(survivors)
    result_events: list[dict[str, Any]] = []
    outcomes: list[RouteOutcome] = []
    identified_index = 0
    for event in input_events:
        if not (event.get("source_uid") or "").strip():
            surfaced = dict(event)
            surfaced["duplicate_group"] = None
            result_events.append(surfaced)
            outcomes.append(
                RouteOutcome(
                    source_uid="",
                    outcome="separate",
                    duplicate_group=None,
                    survivor_uid=None,
                    normalized_title=normalize_route_title(event.get("title")),
                )
            )
            continue
        index = identified_index
        identified_index += 1
        source_uid = identified[index]["source_uid"]
        merged_members = merged_from.get(index, [])
        if index in surviving:
            surfaced = dict(identified[index])
            if merged_members:
                members = [identified[member] for member in merge_classes[merge_find(index)]]
                source, source_urls = _fold_sources(members)
                surfaced["source"] = source
                surfaced["source_urls"] = source_urls
            surfaced["duplicate_group"] = survivor_group.get(index)
            result_events.append(surfaced)
            if merged_members:
                outcome = "merge"
            elif survivor_group.get(index):
                outcome = "group"
            else:
                outcome = "separate"
            outcomes.append(
                RouteOutcome(
                    source_uid=source_uid,
                    outcome=outcome,
                    duplicate_group=survivor_group.get(index),
                    survivor_uid=None,
                    normalized_title=normalized[index],
                    merged_from=tuple(sorted(merged_members)),
                )
            )
        else:
            survivor_index = merge_survivor_of[index]
            outcomes.append(
                RouteOutcome(
                    source_uid=source_uid,
                    outcome="merge",
                    duplicate_group=None,
                    survivor_uid=identified[survivor_index]["source_uid"],
                    normalized_title=normalized[index],
                )
            )

    separate = sum(1 for outcome in outcomes if outcome.outcome == "separate")
    diagnostics: dict[str, Any] = {
        "version": ROUTE_VERSION,
        "threshold": threshold,
        "guards": {
            "location": location_guard,
            "variant": variant_guard,
            "timed_only": timed_only_guard,
        },
        "input": len(input_events),
        "merge_classes": merge_class_count,
        "merge_deleted": len(deleted),
        "groups": len(group_members),
        "grouped_members": sum(len(members) for members in group_members.values()),
        "separate": separate,
        "comparisons": comparisons,
        "max_group_size": observed_max_group_size,
        "max_group_size_budget": max_group_size,
        "comparison_budget": max_comparisons,
        "missing_identity": len(missing_identity),
        "missing_identity_titles": [event.get("title") or "" for event in missing_identity][:10],
        "unparseable_start": unparseable,
        "merge_from": {
            identified[survivor]["source_uid"]: sorted(members)
            for survivor, members in merged_from.items()
        },
        "group_members": group_members,
    }
    return RouteResult(result_events, outcomes, diagnostics, input_events)


def _route_outcome_record(outcome):
    return {
        "source_uid": outcome.source_uid,
        "outcome": outcome.outcome,
        "duplicate_group": outcome.duplicate_group,
        "survivor_uid": outcome.survivor_uid,
        "merged_from": list(outcome.merged_from),
    }


def route_diagnostics_payload(result):
    """Serialisable route diagnostics, including every per-event outcome."""
    diagnostics = dict(result.diagnostics)
    diagnostics["outcomes"] = [_route_outcome_record(outcome) for outcome in result.outcomes]
    return diagnostics


def validate_route_result(result):
    """Fail closed if the route broke a build invariant.

    Recomputes the destructive-band guarantee from the original inputs: every
    deleted row must have an exact-full-title survivor, at the same instant,
    with both locations present and compatible.
    """
    diagnostics = result.diagnostics
    violations: list[str] = []

    if diagnostics["missing_identity"]:
        titles = ", ".join(diagnostics.get("missing_identity_titles") or [])
        violations.append(
            f"{diagnostics['missing_identity']} event(s) missing source_uid "
            f"(non-mergeable, non-groupable): {titles}"
        )
    if diagnostics["comparisons"] > diagnostics["comparison_budget"]:
        violations.append(
            f"comparison budget exceeded: {diagnostics['comparisons']} > "
            f"{diagnostics['comparison_budget']}"
        )
    if diagnostics["max_group_size"] > diagnostics["max_group_size_budget"]:
        violations.append(
            f"group component size {diagnostics['max_group_size']} exceeds budget "
            f"{diagnostics['max_group_size_budget']}"
        )

    input_by_uid: dict[str, dict[str, Any]] = {}
    for event in result.input_events:
        source_uid = (event.get("source_uid") or "").strip()
        if source_uid:
            input_by_uid.setdefault(source_uid, event)

    surviving_uids = [event.get("source_uid") for event in result.events]
    if len(surviving_uids) != len(set(surviving_uids)):
        violations.append("duplicate survivors: a source_uid appears in two surviving rows")

    surviving_set = set(surviving_uids)
    for outcome in result.outcomes:
        if outcome.outcome != "merge" or not outcome.survivor_uid:
            continue
        if outcome.source_uid in surviving_set:
            continue  # the survivor itself, not a deleted row
        deleted_event = input_by_uid.get(outcome.source_uid)
        survivor_event = input_by_uid.get(outcome.survivor_uid)
        if deleted_event is None or survivor_event is None:
            violations.append(
                f"merge of {outcome.source_uid} references an unknown survivor "
                f"{outcome.survivor_uid}"
            )
            continue
        if normalize_route_title(deleted_event.get("title")) != normalize_route_title(
            survivor_event.get("title")
        ):
            violations.append(
                f"merge deleted {outcome.source_uid} without an exact-title survivor "
                f"({outcome.survivor_uid})"
            )
        if not locations_compatible_both(
            deleted_event.get("location"), survivor_event.get("location")
        ):
            violations.append(f"merge deleted {outcome.source_uid} across incompatible locations")
        if instant_epoch(deleted_event) != instant_epoch(survivor_event):
            violations.append(f"merge deleted {outcome.source_uid} across instants")

    groups: dict[str, list[str]] = defaultdict(list)
    for event in result.events:
        group_id = event.get("duplicate_group")
        if group_id:
            groups[group_id].append(event.get("source_uid") or "")
    for group_id, members in groups.items():
        if len(members) < 2:
            violations.append(f"group {group_id} has fewer than two surviving members")
        instants = {instant_epoch(input_by_uid[uid]) for uid in members if uid in input_by_uid}
        if len(instants) > 1:
            violations.append(f"group {group_id} spans multiple instants")

    if violations:
        raise RouteInvariantError(
            "confidence route invariant violation(s): " + "; ".join(violations)
        )


def cluster_by_title_similarity(events, threshold=0.85):
    """Cluster events within same timeslot by title similarity.
    Uses union-find to group similar titles, sorts clusters alphabetically.

    Tuning
    ------
    Threshold controls how similar titles must be to cluster together.
    Genuine duplicates (same event from different sources) score 0.98-1.0:
      "One-On-One Tech Help" vs "Tech Help"                          → 1.000
      "Vineyard Garden Wine Tasting" vs "Picnic Lunch and ..."       → 1.000
      "Bilingual Family Storytime" vs "Family Storytime"             → 1.000

    False matches (different events sharing common words) score 0.56-0.78:
      "Community Coffee Tasting" vs "Community Yoga"                 → 0.783
      "BiblioBus at ... Farmers Market" vs "VALLEJO FARMERS MARKET"  → 0.778
      "Mushroom Hike" vs "Mushroom Identification"                   → 0.762
      "Karaoke Sundays" vs "Sabroso Sundays"                        → 0.733
      "Honky Tonk Open Mic" vs "Open Mic Night"                     → 0.727

    Threshold of 0.85 cleanly separates the two groups.
    """
    from collections import defaultdict

    # Group by timeslot
    slots = defaultdict(list)
    slot_order = []
    for e in events:
        key = e.get("start_time", "") or ""
        if key not in slots:
            slot_order.append(key)
        slots[key].append(e)

    result = []
    for key in slot_order:
        group = slots[key]
        if len(group) <= 1:
            result.extend(group)
            continue

        # Union-find
        parent = list(range(len(group)))

        def find(x, parent=parent):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b, parent=parent):
            parent[find(a, parent)] = find(b, parent)

        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                ta = group[i].get("title", "")
                tb = group[j].get("title", "")
                if not ta or not tb or token_set_similarity(ta, tb) < threshold:
                    continue
                # Don't cluster events at different locations
                la = group[i].get("location", "") or ""
                lb = group[j].get("location", "") or ""
                if la and lb and la != lb:
                    continue
                union(i, j)

        clusters = defaultdict(list)
        for i in range(len(group)):
            clusters[find(i)].append(group[i])

        for c in clusters.values():
            c.sort(key=lambda e: (e.get("title", "") or "").lower())

        sorted_clusters = sorted(
            clusters.values(), key=lambda c: (c[0].get("title", "") or "").lower()
        )

        cluster_idx = 0
        for cluster in sorted_clusters:
            if len(cluster) > 1:
                for e in cluster:
                    e["cluster_id"] = cluster_idx
                cluster_idx += 1
            result.extend(cluster)

    return result


def ics_to_json(ics_file, output_file=None, future_only=True, city=None, diagnostics_file=None):
    """Convert an ICS file to JSON format for Supabase.

    The confidence route runs on the cleaned events before the JSON is written,
    so the artifact carries one deterministic Merge/Group/Separate decision per
    listing. The route diagnostics (per-event outcomes, counts, invariants) are
    written to ``diagnostics_file`` (default: ``<output>.route.json``).
    """
    local_tz = load_city_timezone(city)
    content = Path(ics_file).read_text(encoding="utf-8", errors="ignore")

    # Unfold continuation lines
    content = unfold_ics_lines(content)

    events: list[dict[str, Any]] = []
    # Use 24 hours ago to avoid filtering out same-day events due to timezone differences
    from datetime import timedelta

    now = datetime.now(timezone.utc) - timedelta(hours=24)

    # Extract all VEVENT blocks
    pattern = r"BEGIN:VEVENT\r?\n(.*?)\r?\nEND:VEVENT"
    matches = re.findall(pattern, content, re.DOTALL)

    for event_content in matches:
        # Extract fields. Title/location/description share one cleaning path so
        # routing sees exactly what the reader sees (#145 root cause).
        title = clean_title(extract_field(event_content, "SUMMARY"))
        raw_dtstart = extract_raw_datetime(event_content, "DTSTART")
        start_time = parse_ics_datetime(raw_dtstart, local_tz)
        end_time = parse_ics_datetime(extract_raw_datetime(event_content, "DTEND"), local_tz)
        all_day = is_all_day_event(raw_dtstart)
        location = clean_text(extract_field(event_content, "LOCATION"))
        description = clean_text(extract_field(event_content, "DESCRIPTION"))
        url = extract_field(event_content, "URL")
        if not url:
            url = extract_field(event_content, "X-SOURCE-URL")
        source = extract_field(event_content, "X-SOURCE")
        source_id = extract_field(event_content, "X-SOURCE-ID")
        source_urls_raw = extract_field(event_content, "X-SOURCE-URLS")
        uid = extract_field(event_content, "UID")

        # Extract image URL from ATTACH or X-TKF-FEATURED-IMAGE
        image_url = extract_image_url(event_content)

        # Extract ICS CATEGORIES (raw tags for LLM classification)
        ics_cats_raw = extract_field(event_content, "CATEGORIES")
        ics_categories = [c.strip() for c in ics_cats_raw.split(",")] if ics_cats_raw else []

        # Skip if no title or start time
        if not title or not start_time:
            continue

        # Filter to future events if requested
        if future_only and start_time:
            try:
                event_dt = datetime.fromisoformat(start_time)
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
                if event_dt < now:
                    continue
            except ValueError:
                pass

        source_urls = {}
        if source_urls_raw:
            with contextlib.suppress(json.JSONDecodeError):
                source_urls = json.loads(source_urls_raw)

        event = {
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "location": location or "",
            "description": description or "",
            "url": url or "",
            "city": city or "",
            "source": source or "",
            "source_id": source_id or "",
            "source_uid": uid or "",
            "source_urls": source_urls if source_urls else None,
            # Kept as an unused passthrough for the one compatibility build;
            # duplicate_group is the only active grouping authority.
            "cluster_id": None,
            "ics_categories": ics_categories if ics_categories else None,
            "image_url": image_url,
            "all_day": all_day,
            "duplicate_group": None,
        }
        events.append(event)

    # Sort by start time, then route every listing to one decision.
    events.sort(key=lambda x: x["start_time"] or "")
    route_result = confidence_route(events)
    validate_route_result(route_result)
    events = route_result.events

    # Output
    json_output = json.dumps(events, indent=2, ensure_ascii=False)

    if output_file:
        Path(output_file).write_text(json_output, encoding="utf-8")
        diagnostics_path = (
            Path(diagnostics_file)
            if diagnostics_file
            else Path(output_file).with_name(Path(output_file).stem + ".route.json")
        )
        diagnostics_path.write_text(
            json.dumps(route_diagnostics_payload(route_result), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        diagnostics = route_result.diagnostics
        print(
            f"Converted {len(events)} events to {output_file} "
            f"({diagnostics['merge_deleted']} merged, {diagnostics['groups']} groups)"
        )
    else:
        print(json_output)

    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert ICS to JSON for Supabase")
    parser.add_argument("input", help="Input ICS file")
    parser.add_argument("-o", "--output", help="Output JSON file (stdout if not specified)")
    parser.add_argument("--city", help="City name (e.g., santarosa, sebastopol)")
    parser.add_argument(
        "--all", action="store_true", help="Include past events (default: future only)"
    )

    args = parser.parse_args()

    ics_to_json(args.input, args.output, future_only=not args.all, city=args.city)

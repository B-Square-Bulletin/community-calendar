"""
Shared feed metadata parsing utilities.

Unifies the diverged parse_feeds_txt() implementations from:
  - download_feeds.py    (ICS-only, tuple generator)
  - seed_feeds_from_txt.py (ICS + scrapers, typed dicts)
  - seed_feeds_table.py    (ICS + scrapers, typed dicts with city)
  - combine_ics.py         (scraper-only, stem→name map)

And the duplicated slugify() from:
  - add_feed.py
  - download_feeds.py
"""

import re
from pathlib import Path
from urllib.parse import urlparse


def slugify(url: str) -> str:
    """Generate a readable filename slug from a URL.

    Mirrors the logic from download_feeds.py (most comprehensive variant)
    so all callers produce consistent filenames.
    """
    parsed = urlparse(url)

    # Meetup: extract group slug
    if 'meetup.com' in parsed.netloc:
        match = re.search(r'meetup\.com/([^/]+)', url)
        if match:
            group = match.group(1)
            group = re.sub(r'[^a-zA-Z0-9]+', '_', group).lower().strip('_')
            return f"meetup_{group}"

    # Tockify: extract calendar name
    if 'tockify.com' in parsed.netloc:
        match = re.search(r'/ics/([^/]+)', url)
        if match:
            return f"tockify_{match.group(1)}"

    # CivicPlus (city/county sites): include catID to avoid collisions
    if '/iCalendar/iCalendar.aspx' in parsed.path:
        domain = parsed.netloc.replace('www.', '').split('.')[0]
        cat_match = re.search(r'catID=(\d+)', parsed.query)
        cat_id = f"_{cat_match.group(1)}" if cat_match else ''
        return f"civicplus_{domain}{cat_id}"

    # Google Calendar: extract calendar ID prefix
    if 'calendar.google.com' in parsed.netloc:
        match = re.search(r'ical/([^%/]+)', url)
        if match:
            cal_id = match.group(1)
            cal_id = re.sub(r'[^a-zA-Z0-9]+', '_', cal_id).lower().strip('_')
            return f"gcal_{cal_id}"

    # LibCal: extract institution and calendar ID
    if 'libcal.com' in parsed.netloc:
        match = re.match(r'([^.]+)\.libcal\.com', parsed.netloc)
        inst = match.group(1) if match else 'libcal'
        cid_match = re.search(r'cid=(\d+)', url)
        cid = f"_{cid_match.group(1)}" if cid_match else ''
        return f"libcal_{inst}{cid}"

    # CampusLabs / beINvolved
    if 'campuslabs.com' in parsed.netloc:
        match = re.match(r'([^.]+)\.campuslabs\.com', parsed.netloc)
        inst = match.group(1) if match else 'campuslabs'
        return f"campuslabs_{inst}"

    # LiveWhale (e.g., events.iu.edu/live/ical/events/group_id/56)
    if '/live/ical/' in parsed.path:
        domain = parsed.netloc.replace('www.', '').split('.')[0]
        gid_match = re.search(r'group_id/(\d+)', url)
        gid = f"_{gid_match.group(1)}" if gid_match else ''
        return f"{domain}_livewhale{gid}"

    # General case: domain + meaningful path parts
    domain = parsed.netloc.replace('www.', '').split('.')[0]
    path_parts = [p for p in parsed.path.split('/')
                  if p and p not in ('events', 'ical', 'feed', 'calendar',
                                     'list', 'public', 'basic.ics')]

    if path_parts:
        slug = f"{domain}_{'_'.join(path_parts[:2])}"
    else:
        slug = domain

    slug = re.sub(r'[^a-zA-Z0-9]+', '_', slug).lower().strip('_')
    return slug[:50]


def parse_feeds_txt(path: str) -> list[dict]:
    """Parse feeds.txt into typed dicts, one per source.

    Returns list of dicts:
      ICS feeds:
        {type: 'ics_url', name, url, basename, fallback_url?}

      Scrapers:
        {type: 'scraper', name, path, basename, scraper_cmd?, source_url?}

    basename is computed: slugify(url) for ICS, Path(path).stem for scrapers.
    source_url for scrapers is extracted from --url or --default-url in the
    # cmd: line (null if absent).
    """
    file_path = Path(path)
    if not file_path.exists():
        return []

    lines = file_path.read_text().splitlines()
    feeds = []

    pending_name = None
    pending_fallback = None
    pending_cmd = None

    for line in lines:
        stripped = line.strip()

        # Skip blank lines, section headers, and generated-file banners
        if not stripped or stripped.startswith('# ---'):
            continue
        if stripped.startswith('# Generated from') or 'source inventory' in stripped:
            continue

        # Comment line: could be metadata
        if stripped.startswith('#'):
            body = stripped[1:].strip()

            # Scraper command
            if body.startswith('cmd:'):
                pending_cmd = body[4:].strip()
                # Extract --name for scrapers
                m = re.search(r'--name\s+"([^"]+)"', body)
                if m and not pending_name:
                    pending_name = m.group(1)
                continue

            # Category headers to skip (not metadata)
            if body in ('Scraper', 'Squarespace', 'Songkick',
                        'Chamber of Commerce'):
                continue

            # Friendly name with optional fallback URL
            if '|' in body:
                parts = body.split('|', 1)
                pending_name = parts[0].strip()
                pending_fallback = parts[1].strip() or None
            elif body:
                pending_name = body
                pending_fallback = None
            continue

        # URL line (ICS feed)
        if stripped.startswith('https://'):
            basename = slugify(stripped)
            feeds.append({
                'type': 'ics_url',
                'name': pending_name or stripped,
                'url': stripped,
                'basename': basename,
                'fallback_url': pending_fallback,
            })
            pending_name = None
            pending_fallback = None
            pending_cmd = None
            continue

        # Path line (scraper output)
        if stripped.startswith('cities/') or (
            stripped.endswith('.ics') and '/' in stripped
        ):
            basename = Path(stripped).stem
            # Extract --url or --default-url from the pending command
            source_url = None
            if pending_cmd:
                m = re.search(r'(?:--url|--default-url)\s+"([^"]+)"', pending_cmd)
                if m:
                    source_url = m.group(1)
            feeds.append({
                'type': 'scraper',
                'name': pending_name or basename.replace('_', ' ').title(),
                'path': stripped,
                'basename': basename,
                'scraper_cmd': pending_cmd,
                'source_url': source_url,
            })
            pending_name = None
            pending_cmd = None
            continue

        # Catch-all reset on unrecognized lines
        pending_name = None
        pending_fallback = None
        pending_cmd = None

    return feeds


def build_stem_name_map(path: str) -> dict[str, str]:
    """Build {basename → display_name} map for combine_ics.py fallback
    attribution.

    Only includes scraper entries (ICS feeds don't need this mapping since
    X-SOURCE is injected at download time).
    """
    feeds = parse_feeds_txt(path)
    return {
        f['basename']: f['name']
        for f in feeds
        if f['type'] == 'scraper'
    }

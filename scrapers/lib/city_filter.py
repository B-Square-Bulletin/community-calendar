"""City allowlist loading and location matching for geo-filtering.

Shared by the combine-time filter (`scripts/combine_ics.py`) and the
scrape-time prefilter (per-scraper), so there is one geo-filter definition
rather than two that can drift.
"""

import re
from pathlib import Path


def load_allowed_cities(input_dir):
    """Load allowed/excluded cities and allowed ZIP codes from city.conf.

    Returns (allowed_cities, excluded_cities, allowed_zips) tuple.
    Lines starting with '!' are excluded cities (filtered even without address
    indicators). A `# zips:` header line lists the ZIP codes of the allowed
    towns; a ZIP-only address that belongs to one of them is in-area even
    without the town name spelled out.
    """
    cities_file = Path(input_dir) / "city.conf"
    if not cities_file.exists():
        return None, None, None

    allowed = set()
    excluded = set()
    allowed_zips: set[str] = set()
    for line in cities_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            directive_zips = parse_zips_directive(line)
            if directive_zips is not None:
                allowed_zips.update(directive_zips)
            continue
        # Strip trailing comment (e.g., "Petaluma  # 38.23, -122.63 (0.0 mi)")
        city = line.split("#")[0].strip()
        if city.startswith("!"):
            # Excluded city
            excluded.add(city[1:].strip().lower())
        elif city:
            allowed.add(city.lower())
    return (
        allowed if allowed else None,
        excluded if excluded else None,
        allowed_zips if allowed_zips else None,
    )


# Locations that should always be allowed (virtual events, etc.)
VIRTUAL_LOCATION_PATTERNS = [
    "zoom",
    "online",
    "virtual",
    "webinar",
    "http://",
    "https://",
    "america/los_angeles",  # Malformed Meetup timezone-as-location
    "america/new_york",
]

# Patterns that indicate location is a real address (worth geo-filtering)
# If none of these match, we skip geo-filtering for that event
US_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|"
    "MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|"
    "SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
CA_PROVINCES = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"
_STATE_RE = re.compile(rf", (?:{US_STATES}|{CA_PROVINCES})\b")  # ", CA" or ", ON"
_CITY_STATE_RE = re.compile(rf", [A-Z][a-z]+ (?:{US_STATES}|{CA_PROVINCES})\b")
_ZIP_RE = re.compile(r"\b\d{5}\b")
# A ZIP in postal position: a 5-digit (optionally ZIP+4) token at the end of the
# location or immediately before a comma. Used when deciding whether an address
# is in-area, so a 5-digit house number is not mistaken for a postal code.
_POSTAL_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b(?=\s*(?:,|$))")
_CA_POSTAL_RE = re.compile(r"[A-Z]\d[A-Z]\s?\d[A-Z]\d")  # "M5V 3A8" or "K0K1E0"
_STREET_RE = re.compile(
    r"\d+\s+\w+\s+(?:street|st|avenue|ave|road|rd|drive|dr|boulevard|blvd|lane|ln|way|court|ct)\b",
    re.IGNORECASE,
)
# A city.conf directive listing the ZIP codes of the allowed towns, e.g.
# "# zips: 47401, 47403, 47404". Comments elsewhere are ignored.
_CONF_ZIPS_RE = re.compile(r"^#\s*zips\s*:\s*(.*)$", re.IGNORECASE)


def parse_zips_directive(line):
    """ZIP codes declared by a city.conf `# zips:` line, or None if not one.

    Shared by `load_allowed_cities` and `scripts/geocode_cities.py` so the
    directive is parsed one way in both the runtime filter and the config
    rewrite, and cannot drift.
    """
    match = _CONF_ZIPS_RE.match(line.strip())
    if not match:
        return None
    return set(_ZIP_RE.findall(match.group(1)))


def _postal_zips(location):
    """ZIP codes that appear in postal position in a location string."""
    return set(_POSTAL_ZIP_RE.findall(location))


def _has_address_indicator(location):
    """Check if a location string looks like a real address."""
    return bool(
        _STATE_RE.search(location)
        or _ZIP_RE.search(location)
        or _CA_POSTAL_RE.search(location)
        or _CITY_STATE_RE.search(location)
        or _STREET_RE.search(location)
    )


def location_matches_allowed_cities(
    location, allowed_cities, excluded_cities=None, allowed_zips=None
):
    """Check if a location string is in the allowed area.

    A location matches when it names an allowed town OR carries a ZIP code
    belonging to one of them. Only locations that look like real addresses are
    geo-filtered, UNLESS the location contains an explicitly excluded city name.
    Venue-only names ("Theater", "BiblioBus") are allowed through.
    """
    if not allowed_cities:
        return True  # No filter configured
    if not location:
        return True  # No location to check, allow it

    location_lower = location.lower()

    # Always allow virtual/online events
    for pattern in VIRTUAL_LOCATION_PATTERNS:
        if pattern in location_lower:
            return True

    # Check for explicitly excluded cities (even without address indicators)
    if excluded_cities:
        for city in excluded_cities:
            if city in location_lower:
                return False

    # Check if location looks like an address
    # If not, allow it through (venue name only, no geo info to filter on)
    if not _has_address_indicator(location):
        return True

    # Location has address info - check against allowed cities
    if any(city in location_lower for city in allowed_cities):
        return True

    # A ZIP-only address (common in the US) carries no town name; accept it
    # when its postal code belongs to an allowed town.
    return bool(allowed_zips and _postal_zips(location) & allowed_zips)

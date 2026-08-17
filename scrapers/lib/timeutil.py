"""Timezone-safe datetime helpers shared by scrapers and pipeline scripts.

The DTZ ruff rules require every datetime construction/parse to be
timezone-aware. But the calendar's domain model (see CONTEXT.md) keeps
wall-clock times naive until the ICS→JSON boundary: scrapers parse "the clock
time on the venue's wall", with no zone attached at scrape time. These helpers
centralize that intentional naivety so a single documented `# noqa` per helper
explains the rationale instead of ~120 inline suppressions.

Two categories:
- Wall-clock helpers (`wall_clock`, `parse_naive_ics`) — deliberately naive.
- UTC helpers (`utc_now`, `utc_today`) — timezone-aware, used wherever the
  pipeline needs "right now".
"""

from datetime import datetime, timezone


def wall_clock(year, month, day, hour=0, minute=0, second=0, microsecond=0):
    """Construct a naive wall-clock datetime in the venue's local zone.

    Deliberately naive: the source site states a clock time, not a zone, so a
    zone cannot be attached at scrape time. ics_to_json.py stamps TZID/city
    timezone at the ICS→JSON boundary.
    """
    return datetime(year, month, day, hour, minute, second, microsecond)  # noqa: DTZ001


def parse_naive_ics(dt_str, fmt):
    """Parse a wall-clock datetime string with a strptime format.

    Deliberately naive: same rationale as wall_clock(). The pipeline attaches
    a zone later; parsing with %z here would wrongly force a zone on text the
    source never zoned.
    """
    return datetime.strptime(dt_str, fmt)  # noqa: DTZ007


def utc_now():
    """Return the current absolute instant in UTC."""
    return datetime.now(timezone.utc)


def utc_today():
    """Return today's date in UTC, matching the pipeline's ±1-day tolerance."""
    return utc_now().date()

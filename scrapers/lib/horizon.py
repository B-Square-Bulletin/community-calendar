"""The Horizon boundary and its predicate, shared by scrapers.

The Horizon is the end of the prefetched event set: `months_ahead` months'
worth of days (31 per month) from now, per CONTEXT.md. `horizon_end` is the one
definition of the boundary instant; `within` answers "is this event inside it?',
normalising the `date` / naive-datetime / aware-datetime shapes scraper events
arrive in.

Scrapers reach it through `BaseScraper.horizon_cutoff()` (and `horizon_end`
directly where there is no `self`). Two inline `* 30` ceilings stay local, each
with a comment: `elfsight.py`'s listing expansion and `davis_chamber.py`'s month
cursor — neither is a day-offset Horizon boundary.
"""

from datetime import date, datetime, timedelta


def horizon_end(now: datetime | None, months_ahead: int) -> datetime:
    """The Horizon boundary instant: `months_ahead * 31` days from `now`.

    `now` defaults to the current local time; pass the source's own clock to
    key the boundary to it.
    """
    return (now or datetime.now().astimezone()) + timedelta(days=months_ahead * 31)


def within(dt: date | datetime | None, end: datetime) -> bool:
    """Is `dt` on or before the Horizon boundary `end`?

    A `date` is read as midnight in `end`'s zone; a naive datetime is read in
    `end`'s zone; an aware datetime is compared as an absolute instant. A
    missing start is not within.
    """
    if dt is None:
        return False
    if not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=end.tzinfo)
    return dt <= end

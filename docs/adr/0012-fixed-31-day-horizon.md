# 0012. The Horizon Boundary Is a Fixed Day Offset, Not Calendar Months

Date: 2026-09-18

## Status

Accepted

## Context

Every source caps its fetch at a Horizon of `SCRAPE_MONTHS` months
(`BaseScraper.months_ahead`), so the calendar has a predictable amount of
prefetched data. The boundary could be computed two ways: add calendar months
(`now + relativedelta(months=N)`), or add a fixed number of days
(`now + timedelta(days=N * 31)`). The helper `scrapers/lib/horizon.py` uses the
fixed day offset; a reader encountering `* 31` would reasonably assume the
calendar-aware form was intended and "fix" it.

## Decision

**The Horizon is `months_ahead * 31` days from now — a fixed day offset, never
calendar-aware.** `horizon_end()` is the single definition; `within()` is the
single predicate. Scrapers route through `BaseScraper.horizon_cutoff()`.

A fixed offset keeps the window uniform regardless of which months it spans, is
trivial to test and reproduce, and is stable across time zones and DST. A
calendar-aware add would produce uneven windows (28–31 days per month) and
month-end ambiguity. The trade-off is that "6 months" is really 186 days.

Two inline `* 30` ceilings deliberately stay local, each commented: Elfsight's
listing expansion (`scrapers/lib/elfsight.py`) and Davis Chamber's month cursor
(`scrapers/davis_chamber.py`). Neither is a day-offset Horizon boundary, and
unifying them would change behaviour.

## Consequences

- The Horizon helper, `BaseScraper.months_ahead`, and production
  `SCRAPE_MONTHS=3` (~93 days) are the only inputs to the boundary.
- Changing the offset is a one-line change in one file, but it moves every
  source's window at once — treat it as deliberate.
- The two `* 30` sites are exceptions by intent; their comments point back here
  so the next reader does not unify them.

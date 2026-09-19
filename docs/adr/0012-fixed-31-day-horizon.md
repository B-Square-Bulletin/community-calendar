# 0012. The Horizon Boundary Is a Fixed Day Offset, Not Calendar Months

Date: 2026-09-18

## Status

Accepted

## Context

The calendar holds a predictable amount of prefetched data: `BaseScraper.run()`
drops any emitted event whose start is beyond a Horizon of `SCRAPE_MONTHS`
months (`BaseScraper.months_ahead`). Upstream fetches may also be bounded, but
that is per-source — Legistar, for example, applies no upper bound and relies on
the `run()` filter. The boundary could be computed two ways: add calendar months
(`now + relativedelta(months=N)`), or add a fixed number of days
(`now + timedelta(days=N * 31)`). The helper `scrapers/lib/horizon.py` uses the
fixed day offset; a reader encountering `* 31` would reasonably assume the
calendar-aware form was intended and "fix" it.

## Decision

**The Horizon is `months_ahead * 31` days from now — a fixed day offset, never
calendar-aware.** `horizon_end()` is the single definition; `within()` is the
single predicate. Scrapers route through `BaseScraper.horizon_cutoff()`.

A fixed offset keeps the window uniform regardless of which months it spans and
is trivial to test and reproduce. It is a fixed count of *civil* days: aware
`datetime + timedelta` preserves local wall-clock time, so the boundary is the
same time-of-day N×31 days later, and the absolute duration can shift by an hour
across a DST transition. A calendar-aware add would produce uneven windows
(28–31 days per month) and month-end ambiguity. The trade-off is that "6 months"
is really 186 days.

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

## Alternatives Considered

- **Calendar-aware month addition** (`relativedelta(months=N)`): rejected. It
  yields uneven windows (28–31 days per month) and month-end ambiguity, so the
  same `SCRAPE_MONTHS` would prefetch different amounts depending on the
  current date, making the calendar's coverage harder to reason about and test.
- **Each scraper computes its boundary inline** (the status quo): rejected.
  It gave the rule ~13 definitions that could drift; routing through one helper
  makes the boundary changeable in one place.
- **Unify the two `* 30` ceilings now**: rejected as a behaviour change outside
  this refactor's scope. They can be migrated deliberately later if the
  separate tolerances stop being useful.

# 0011. Visit Bloomington Ranks as a Primary Source, Not an Aggregator

Date: 2026-09-15

## Status

Accepted

## Context

Cross-source dedup is governed by `source_priority.json`, which holds a single
`aggregators` array. Membership is inverted from what the name suggests to a
casual reader: a source **listed** there is an *aggregator* and **loses** a dedup
collision, while a source **absent** from the file is a *primary* source and
**wins**. `combine_ics.py` sorts non-aggregators ahead of aggregators in
`dedupe_cross_source`.

Visit Bloomington (the Monroe County CVB tourism portal) is being added as a new
source. The same event often appears twice: once from Visit Bloomington and once
from *Limestone Post*, an existing aggregator whose CitySpark feed already
carries CVB-sourced events (`Links[0].url` → `visitbloomington.com/event/...`)
under `source = Limestone Post`.

The obvious precedent points the other way. `Visit Morgan County` — the same
class of multi-venue Simpleview tourism portal — **is** listed in
`source_priority.json` as an aggregator. A reasonable maintainer, seeing two
near-identical tourism portals treated differently, would "fix" the
inconsistency.

## Decision

**Visit Bloomington is a primary source and is NOT added to
`source_priority.json`.** It therefore wins cross-source dedup over Limestone
Post; shared events merge and display `Visit Bloomington, Limestone Post` with
the primary first. No code change is needed — `dedupe_cross_source` already
ranks non-aggregators ahead of aggregators.

The deliberate trade-off: as a non-aggregator, Visit Bloomington also outranks a
*venue's own* event feed when the same event appears in both. A future middle
tier ("beats aggregators, loses to direct venues") is out of scope for this
effort.

## Consequences

**Easier:**
- CVB events are attributed to the CVB, the canonical owner of the listing,
  rather than to Limestone Post's echo.
- No code or config change: the ranking falls out of the existing sort.

**Harder / surprising:**
- Visit Bloomington and Visit Morgan County — superficially the same kind of
  source — occupy different tiers. This is intentional, not a bug; see the
  Alternatives below before "correcting" it.
- A shared event that a direct venue also publishes will credit Visit
  Bloomington first. Accepted for this effort.

## Alternatives Considered

- **Add Visit Bloomington to `source_priority.json` to match Visit Morgan
  County.** Rejected: the locked rail for this effort ranks the CVB above
  Limestone Post; listing it would let the aggregator's echo win the same event.
- **Add a middle tier (beats aggregators, loses to direct venues).** Rejected as
  larger than this effort needs; it changes dedup semantics for every source and
  should be a deliberate, separately-scoped change if ever wanted.

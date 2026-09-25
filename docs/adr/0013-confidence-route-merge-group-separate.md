# 0013. One Confidence Route Decides Merge, Group, and Separate

Date: 2026-09-22

## Status

Accepted

## Context

The same real-world event was rendered as two or three cards because three
dedup layers used three different keys: `combine_ics.dedupe_cross_source`
keyed on normalized title plus date, the `deduplicated_events` view and the
client `dedupeEvents` keyed on title plus start time, and `cluster_id` drove a
display-only grouping. A duplicate pair could slip through all three, and where
a layer did fire it could fold two *different* events together with no way for
a maintainer to tell. The only layer that could delete a row keyed on date plus
title, so two sessions of one workshop collapsed into one.

A destructive decision also has no undo: a wrong Merge silently removes a
listing. Maintainers could not safely tighten auto-merge without risking that.

## Decision

**One route, at build time, on cleaned titles.** `scripts/ics_to_json.py`
exposes `confidence_route(events)`, a pure function over the cleaned event list.
It runs once per build before the JSON is written and assigns every listing
exactly one outcome:

- **Merge** — identical cleaned full title, same start instant, and compatible
  locations present on *both* sides (the Merge variant of location
  compatibility is stricter than Group: a pair with no identifiable city does
  not match on shared tokens, a pair with no street number needs three shared
  tokens rather than two, and the town/state every listing shares does not
  count — see `_locations_compatible`). One representative survives (primary
  source first, then smallest `source_uid`, then smallest URL); the other
  sources fold into it. Merge is computed as equivalence classes over the
  exact-title relation alone, over merge edges only, so it can never propagate
  through a similarity edge. No threshold change can cause a deletion.
- **Group** — similarity at or above the threshold (0.80), same start instant,
  compatible locations (either side may be empty), and neither guard fires: no
  squad/gender variant conflict and no all-day listing. Every row is kept and
  every surviving member shares a stable `duplicate_group` id.
- **Separate** — everything else. Separate is authoritative: a NULL
  `duplicate_group` means one row is one group, and no consumer re-collapses it.

The route is versioned (`cr2`: `cr1` plus multi-word city-token extraction) and fails closed: missing `source_uid`,
deletion without an exact-title survivor, duplicate survivors, malformed group
membership, excessive component size (25), or excessive comparison work
(250,000) all raise and fail the build with an actionable diagnostic.

**One id, consumed everywhere.** The route emits `duplicate_group` into
`events.json`; `load-events` upserts it to `events.duplicate_group` (whole-object
upsert, so no edge-function change). The materialized view groups by
`(city, start_time, coalesce(duplicate_group, 'row:' || id))` — isolating every
NULL row — and unions member ids, structured source names, and source URLs.
Main calendar, dashboard tiles, saved picks, and RSS all read that stored
decision rather than recomputing grouping.

**`cluster_id` is retired.** It was an integer index scoped to a timeslot,
produced only by the superseded `cluster_by_title_similarity`. Rather than
invent a second producer for a dead column, consumers moved to
`duplicate_group`, the column stayed readable for one compatibility build, and
a cleanup migration then dropped it.

**No same-source guard.** There is no rule refusing to merge two listings from
one source. Two sessions of one workshop differ in start time (the instant
bucket keeps them apart); naming drift for a recurring series is a *different*
title, so it lands in the non-destructive Group band; what remains — same
source, identical cleaned title, same instant, compatible location — is one
listing duplicated, and merging it is correct.

## Consequences

**Easier:**
- One place decides duplicates, so a maintainer can reason about why a pair
  merged or did not, and the similarity threshold only ever moves the
  non-destructive Group band.
- Every consumer — view, app, dashboard, RSS — agrees because they read one
  stored id, so the views cannot disagree.
- Grouped listings keep every source and link.

**Harder / surprising:**
- Merged rows are deleted at build, so a pick stored against a deleted row is
  lost (unchanged from prior behaviour, accepted). Grouped rows are all kept,
  so picks on any member survive via the `merged_ids` union.
- `duplicate_group` is stable for the same membership but opaque and
  version-namespaced; it intentionally changes when membership changes, so no
  consumer may persist it as identity.
- Saved picks collapse to the route's representative when it is among the
  picked members; otherwise they fall back deterministically to the smallest
  member event id. The normal UI picks the card's (representative) id, so the
  fallback only covers picks stored before the route existed or a group whose
  representative changed between builds. The list and the ICS feed rank on the
  same key, so they stay consistent with each other.
- Empty-location pairs can Group (the accepted false-positive budget); the
  threshold and guards are the tuning surface. The destructive Merge band is
  stricter than Group about locations: a pair with no identifiable city does
  not Merge on shared tokens, a pair with no street number needs three shared
  tokens rather than two, and the town/state tokens every listing in a town
  shares do not count as compatibility.

## Alternatives Considered

- **Keep the three layered keys and tighten the title fallback.** Rejected: a
  title key that can delete a row cannot distinguish two sessions of one
  workshop, and no layer can audit another's decision.
- **Make Merge fuzzy (title similarity plus instant plus location).** Rejected:
  it makes the destructive band tunable, so raising recall can delete a real
  event. Merge stays exact and auditable.
- **Dual-write `cluster_id` during the transition.** Rejected: it invents a
  second producer for a dead column; consumers switch, the column is dropped.
- **Persist `duplicate_group` as pick identity.** Rejected: the id churns when
  membership changes; picks stay on `event_id` plus the `merged_ids` union.

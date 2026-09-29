# 0017. Client Card Membership Is One Module

Date: 2026-09-29

## Status

Accepted

## Context

The `deduplicated_events` view already returns one row per stored group
(rolled up by `(city, start_time, group_key)`, with `merged_ids` carrying every
member id), so on the plain path the client's grouping is near pass-through.
Client-side grouping exists for one reason: **enrichment folding** — a virtual
occurrence whose original-occurrence flag is set must attach to its linked
group's card, and enrichment data arrives on a separate fetch from events.

Before this decision, that fold, the pick-state read, the picks-list
representative choice, and the write plan each lived in different files with
different keys (`helpers.js`, `Main.xmlui`, `Globals.xs`, `shell.js`,
`EventCard.xmlui`, and the `PickItem`/`SourcesDialog`/`FeedTile` components),
and four removal paths (`Globals.xs` togglePick pick-delete, togglePick
enrichment-delete, `removePick`, and a dead `shell.js` toggle referenced by no
markup) could disagree. The reader-visible failures: a pick made on one
source's row did not light up the duplicate card rendered from another source;
unpicking from the picks list could leave the calendar card still marked or
leave a curator enrichment behind; the sources dialog count could disagree with
the list; and a load with linked enrichments applied the recurring-series
collapse twice, with nothing pinning its rule or its order. The
build-time confidence route ([ADR 0013](0013-confidence-route-merge-group-separate.md))
remains the sole authority on which listings are one event; the problem was
that the client re-derived membership from that decision in several places.

## Decision

**One client module, `Card`, owns card membership.** It is a pure
`window`-attached module loaded as a shipped script before `helpers.js` and
before app start, exposing `group`, `groupMemo`, `members`, `isPicked`,
`uniquePicks`, `pickPlan`, `cardForPick`, and `normalizePick`. Every consumer —
the calendar list, the dashboard tiles, the picks list, and the sources dialog —
reads that one module.

- **Card reads only the stored route decision** (`duplicate_group`,
  `merged_ids`, `source_names`, `source_urls`) and never recomputes similarity.
  A NULL `duplicate_group` means one row is one card. ADR 0013 stays the sole
  authority on which listings are one event.
- **`group` owns enrichment folding.** A virtual occurrence whose
  original-occurrence flag is set attaches to its linked group's card; every
  other virtual occurrence stays its own card, marked `isVirtual`; synthetic
  enrichment ids never enter membership (`picks.event_id` is a foreign key, so
  a synthetic id could never be picked anyway).
- **A second module, `Recurring`, owns the long-running-series weekly collapse**
  (first occurrence per week, the five-occurrence minimum, the `isRecurring`
  mark) as a pure function with an injected clock, and is applied exactly once
  at its composition point in `processEvents`.
- **One write authority for pick and unpick.** The delete plan comes from
  `Card.pickPlan(card).memberEventIds`; the two write paths issue the same two
  deletes — picks by `event_id in members` + `user_id`, enrichments by
  `event_id in members` + `curator_id`. User/curator scoping stays verbatim on
  every URL; RLS remains the backstop, not the primary scoping.
- **The picks list uses `Card.uniquePicks`** over whole pick objects, keeping
  the exact representative ranking the `my-picks` ICS feed implements (ADR
  0013): representative first, then smallest `event_id`, so the list and the
  feed cannot choose different members.

## Consequences

- Consumers that need "what is on one card" have exactly one place to read;
  a change to one reader cannot silently disagree with another.
- The write plan is uniform: one authority, two deletes (picks, enrichments),
  user-scoped. `removePick` now also clears the curator's enrichment for the
  group's members, which it previously left behind.
- `Card` must not gain similarity logic; the route's thresholds stay
  build-side.
- The calendar groups the enrichment path through `Card.groupMemo`; the plain
  path still passes view rows through. The dialog and tiles pass the strong
  `eventsSignature(rows)` to `groupMemo`; the memo signature is the existing
  composite (array signature + enrichment-linkage signature + the emission
  signature `__ccEmitSig`), so a mid-payload change cannot false-HIT.
- Virtual (future-occurrence) cards are unpickable: `isPicked` returns false
  and the card's bookmark is hidden. Previously the bookmark rendered on every
  signed-in card and its save always failed on the picks foreign key.
- The enrichment-path exclusion edge case now follows the plain path's rule.
  The four deliberate behaviour changes are recorded in the feature spec's
  Intended Behavior Changes section, not here.
- `dedupeEvents`, `eventMergedIds`, and `dedupePicks` are removed outright;
  the camelCase `mergedIds` alias is dropped in favour of the view's
  `merged_ids`, with `members` as the reader.

## Alternatives Considered

- **Keep the membership reads where they were and tighten each one.** Rejected:
  it was the source of the disagreement — different keys in six files, with no
  seam to test them together.
- **Recompute similarity on the client and group there.** Rejected: it forks
  the authority ADR 0013 established. The route's thresholds stay build-side;
  Card only reads the stored decision.
- **Leave the recurring collapse inside `dedupeEvents`.** Rejected: the rule
  was applied twice on the enrichment path with no pinned order. Extracting
  `Recurring` and applying it once at the composition point makes the rule
  testable with an injected clock and pins where it runs.
- **Make `pickPlan` carry separate `memberEventIds` and `enrichmentEventIds`.**
  Rejected: processed rows strip enrichment linkage and enrichment rows key on
  real `event_id`s, so the enrichment list would always equal the member list.
- **Persist `duplicate_group` as pick identity.** Rejected by ADR 0013 and
  upheld here: the id churns when membership changes; the member-id list is
  read from the row's `merged_ids`.

## References

- [ADR 0013 — One Confidence Route Decides Merge, Group, and Separate](0013-confidence-route-merge-group-separate.md)
- Feature spec: `.scratch/169-card-membership/spec.md`
- Verification: [Card Membership Verification](../card-membership-verification.md)

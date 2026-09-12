# 0010. Semantic Graft for Divergent Upstream Sync Conflicts

Date: 2026-09-12

## Status

Accepted.

## Context

ADR 0004 (Decision 1) records that the 2026-08-02 sync resolved the
`xmlui/shell.js` conflict by adopting upstream's version wholesale. That was
correct then: the fork had no material `shell.js` divergence, and upstream's
IndexedDB-events-cache + PushSource refactor was the point of the sync.

The fork has since diverged. `Main.xmlui` replaced upstream's day-range slider
with the committed date-window tabs (#105–#108), and its `getPagedEvents` call
sites no longer pass `sliderStart`/`sliderEnd`; `shell.js` carries
fork-specific cache and emission-coalescing work. In the 2026-09-12 sync,
upstream's only `shell.js` change was retiring the skip-stale TTL gate in
`unwrapCachedRows`, and its only `Main.xmlui` change was the epoch nudge
(xmlui#3816 workaround). Wholesale adoption would have reverted the fork's
date-tab work, and a line-based merge produced entangled conflicts in both
files.

## Decision

1. **Semantic graft.** For a file the fork has materially diverged on, resolve
   a sync conflict by keeping the fork's version and applying upstream's
   semantic change onto it — not by adopting upstream's version wholesale.
   Wholesale adoption remains the default only for files the fork has not
   diverged on.
2. **Preserve both intents, invent neither.** A graft must keep the fork's
   behavior and adopt upstream's change; where the two conflict structurally,
   adapt upstream's mechanism to the fork's shape. Example: thread the inert
   `eventsEpoch` argument through the fork's `getPagedEvents` calls rather than
   reintroducing the slider arity.
3. **Gate each graft.** The fork's suites (`pnpm vitest run`, the
   `xmlui/test.html` browser groups) and the ADR-0004
   `scripts/bench_collapse_long.js` benchmark must pass on the resolved file
   before the sync PR merges.
4. **Fix upstream defects upstream.** When a graft surfaces a genuine upstream
   defect, fix it in the upstream repo rather than carrying a silent fork-only
   patch. The coalescing-identity bug this sync exposed is upstream PR #85.

## Consequences

**Easier:**

- Syncs stay compatible with the fork's intentional divergence (ADR 0002)
  without reverting fork work.
- The graft is auditable: a small, reviewable delta on the fork's file, covered
  by tests the fork already runs.

**Harder:**

- Each sync must read upstream's actual change, not just resolve markers;
  conflict resolution becomes a semantic exercise, not a textual one.
- Divergent files drift further apart, so future syncs demand more careful
  grafting.

## Alternatives Considered

- **Wholesale adoption (ADR 0004 §1 as written).** Simplest to resolve, but
  discards the fork's date-tab and cache work. Rejected once the fork diverged.
- **Cherry-pick upstream commits, never merge.** Avoids conflicts but compounds
  sync debt and loses the merge-base, making future resolution harder. Rejected
  for the same reason ADR 0004 rejected it.
- **Re-fork / stop syncing.** Abandons upstream fixes and the shared engine.
  Rejected per ADR 0002.

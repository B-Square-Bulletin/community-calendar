# Card Membership Verification (#169)

This document records the verification evidence for the client card-membership
refactor: the before/after performance capture and the acceptance checklist
mapping every one of the spec's 24 stories to the check that verifies it. It
accompanies [ADR 0017](adr/0017-client-card-membership-is-one-module.md).

The documentation and the code both live on the feature branch
(`feat/169-card-membership`), never on `main`.

## Performance capture

The refactor moves grouping into `Card` and the weekly collapse into
`Recurring`, and moves the collapse from the grouping function to a single
composition point. Story 15 asks that the calendar still paint as fast as it
does today, and story 17 that the cached-then-fresh double load stay cheap. The
capture below compares the branch against the pre-refactor code over the
client's real input shape.

**Environment.** Apple silicon macOS, Node `v26.7.0`, single local process per
run. Absolute numbers vary by machine; the ratios and the tolerance are the
portable part. "Before" is the branch's starting point `0dfcfc43e`; its
`xmlui/` is byte-identical to `origin/main` at the merge-base `c35ac2411` (the
fixtures commit adds only test fixtures), so it is the pre-refactor application
code.

### Durable gates (`pnpm bench`)

Two committed benchmarks guard the warm path in CI. Medians of five runs:

| Benchmark | Stage | Before | After (branch) |
| --- | --- | --- | --- |
| `scripts/bench_collapse_long.js` (3,202 synthetic events) | cold miss | 57.1 ms | 56.3 ms |
| `scripts/bench_collapse_long.js` | warm hit (fresh refs) | 0.1 ms | 0.1 ms |
| `scripts/bench_card_group.js` (3,202 synthetic view rows) | cold compute | _n/a (new guard)_ | 78.4 ms |
| `scripts/bench_card_group.js` | warm hit (fresh refs) | _n/a (new guard)_ | 0.2–0.3 ms |
| `scripts/bench_card_group.js --rows` (3,795 captured view rows) | cold compute | _n/a_ | 100.2 ms |
| `scripts/bench_card_group.js --rows` | warm hit (fresh refs) | _n/a_ | 0.3 ms |

`bench_card_group.js` is a new guard, so it has no "before"; its role is to keep
`Card.groupMemo` a reference-returning warm hit and to recompute on a new
emission even when only the middle row changed (the #86 lesson). The captured
production payload is `tests/fixtures/deduplicated_events_bloomington.json.gz`.

### Full transform, production payload (3,795 view rows)

The equivalent "group + collapse" transform on each revision, timed after three
warm-up iterations, ten timed reps per run, three interleaved runs to damp
drift. The pre-refactor code calls `dedupeEvents`; the branch calls
`Card.group` + `collapseLongRunningEvents` (the cache-guarded composition point).

| Transform | Cold median | Warm median (same emission, fresh refs) |
| --- | --- | --- |
| Before — `dedupeEvents(rows)` | 445–526 ms | 59–70 ms |
| After — `Card.group(rows)` + `collapseLongRunningEvents` | 431–500 ms | 50–60 ms |
| After / before | 0.89–0.97× | 0.84–0.87× |

**Tolerance.** The cold transform must stay within **+15%** of the pre-refactor
code, and the warm cached stage must remain a cache hit under the benchmarks'
**5 ms** hit threshold. Both hold: cold is at parity or faster (0.89–0.97×) and
warm is at parity or faster (0.84–0.87×). No regression was observed.

## Acceptance checklist

All 24 user stories from `.scratch/169-card-membership/spec.md`. "Where" names
the test file and, in quotes, the case that carries the verification. The
shipped-file `vm` harness (`tests/js/load-shipped.js`) loads `card.js` and
`recurring.js`; the browser groups run under Playwright via
`tests/js/test-html.browser.spec.js`.

| # | Story | Verifies it | Where |
| --- | --- | --- | --- |
| 1 | One card per event across sources | One stored group → one card; membership union | `tests/js/card-membership.test.js` "collapses one stored group to one card with every member id and source", "merges two rows of one stored group into one card with a unioned membership"; `tests/js/validate-dedupe-groups.test.js` "Card.group groups by the stored duplicate_group" |
| 2 | A card shows every carrying source | Member source names and links unioned onto the card | `tests/js/card-membership.test.js` "collapses one stored group to one card with every member id and source"; `tests/js/validate-dedupe-groups.test.js` "folds structured source_names" |
| 3 | Bookmarking marks the whole event | `isPicked` true when any member is picked; EventCard reads `Card.isPicked` | `tests/js/card-membership.test.js` "Card.isPicked" "is true when any member is picked"; `tests/js/validate-dedupe-groups.test.js` "seeds merged_ids from the view column so one pick lights every member" |
| 4 | Un-bookmarking clears it everywhere | One delete plan over all member ids | `tests/js/pick-write-authority.test.js` "deletes the user's picks by member id and user id"; `tests/js/card-membership.test.js` "is false when no member is picked" |
| 5 | Removing from the picks list clears the event | `removePick` resolves the card, then runs the one plan | `tests/js/pick-write-authority.test.js` "prefers the mirrored card list", "falls back to one group GET, then the pick's own event id"; `tests/js/validate-dedupe-groups.test.js` "removing a saved Group runs the one write plan for its members" |
| 6 | Unpicking also removes the enrichment | The authority issues the second scoped delete | `tests/js/pick-write-authority.test.js` "deletes the curator's enrichments by member id and curator id" |
| 7 | Picks list shows one entry per event | `uniquePicks` collapses members of one group | `tests/js/card-membership.test.js` "Card.uniquePicks" "keeps one entry per stored group"; `tests/js/validate-dedupe-groups.test.js` "Card.uniquePicks shows one representation per stored group" |
| 8 | A pick survives a build reshuffle | Ranking falls back to smallest member id; list and feed agree | `tests/js/card-membership.test.js` "falls back to the smallest member event id when the representative is not picked", "ranks exactly as the my-picks ICS feed does (ADR-0013)" |
| 9 | Tiles collapse like the list | Tiles group + collapse before category/search | `tests/js/dialog-and-tiles.test.js` "dashboard tiles group and collapse before category/search filtering" |
| 10 | A recurring series shows once per week | The rule: first per week, five-occurrence minimum | `tests/js/recurring-collapse.test.js` "Recurring.collapse is a pure rule" (collapse at the minimum, first occurrence of a week) |
| 11 | A recurring pick's original shows with its event | Original occurrence folds onto its linked card | `tests/js/card-membership.test.js` "folds an enrichment's original occurrence onto its linked group's card"; `tests/js/validate-dedupe-groups.test.js` "links enrichments in the main calendar processing path" |
| 12 | Future occurrences are their own cards, unpickable | `isVirtual` emitted; `isPicked` false; bookmark hidden | `tests/js/card-membership.test.js` "keeps a future occurrence as its own virtual card with no membership", "is false for a virtual card even if an id matches"; `tests/js/validate-dedupe-groups.test.js` "marks a future occurrence as its own unpickable virtual card" |
| 13 | Dialog counts apply the same rule | One named `Card.groupMemo` + `Recurring.collapse` step | `tests/js/dialog-and-tiles.test.js` "applies Card.groupMemo and Recurring.collapse in one named step", "keeps the dialog's own inputs while sharing the rule" |
| 14 | Hiding a source hides every card it carries | Hidden-source filter runs over the grouped cards | `tests/js/dialog-and-tiles.test.js` "hides every card a source fully carries when that source is hidden" |
| 15 | The calendar paints as fast as today | Benchmarks + before/after capture | `pnpm bench` (`bench_collapse_long.js`, `bench_card_group.js`); Performance capture above |
| 16 | Bookmarking does not re-ingest the event list | A picks change refetches picks + enrichments only | `tests/js/pick-write-authority.test.js` "refetches picks and enrichments only, not events" |
| 17 | The cached-then-fresh double load stays cheap | Warm `groupMemo` hit and collapse content-key hit | `pnpm bench` warm runs (≤ 0.3 ms); Performance capture above |
| 18 | One place decides card membership | The legacy surface is gone; one module is the reader | `tests/js/legacy-membership-retired.test.js` "no longer exposes dedupeEvents, eventMergedIds, or dedupePicks on window", "removed the dead shell toggle while keeping the live Globals.xs one" |
| 19 | The rule is tested at one seam | The single `window.Card` interface under the `vm` harness | `tests/js/card-membership.test.js` (35 cases) through `tests/js/load-shipped.js` |
| 20 | The collapse is tested with an injected clock | `Recurring.collapse(events, { now })` | `tests/js/recurring-collapse.test.js` "anchors weeks on the injected clock, not the wall clock" |
| 21 | Output-equivalent against a production fixture | Plain-path replay + the enrichment fold fixture | `tests/js/card-membership.test.js` "plain-path equivalence over the production view payload", "enrichment fixture pins the single-pass fold -> group output" |
| 22 | A before/after performance comparison | Recorded with a tolerance | Performance capture above |
| 23 | The module interface and test seam are defined | Interface, exports, shipped-file harness | `.scratch/169-card-membership/spec.md` (interface block); `xmlui/card.js` `window.Card`; `tests/js/load-shipped.js` |
| 24 | The client never recomputes dedup similarity | Card reads only the stored route decision | `tests/js/card-membership.test.js` "Card.group groups by the stored route decision" (NULL and different groups stay separate); [ADR 0017](adr/0017-client-card-membership-is-one-module.md) |

## Reproduce

```bash
# Durable performance gates (cold/warm)
pnpm bench

# Seam tests (Card + Recurring + glue call sites)
pnpm test

# Integrated markup bindings in a real browser
pnpm test:browser
```

## Sign-off

- [x] The `Card` glossary entry is committed on the feature branch (`CONTEXT.md`)
- [x] ADR-0017 is committed on the feature branch and references ADR-0013 (`docs/adr/0017-client-card-membership-is-one-module.md`)
- [x] The before/after performance capture is recorded with a tolerance (above)
- [x] The acceptance checklist maps all 24 stories to their verification (above)

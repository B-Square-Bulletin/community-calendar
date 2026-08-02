# 0004. Upstream Sync Verification Protocol

Date: 2026-08-02

## Status

Accepted

## Context

This repository is a hard fork of judell/community-calendar (ADR 0002) that
serves Bloomington only. It tracks upstream through `chore/upstream-sync-*`
branches that merge `upstream/main` and open PRs into `origin/main`.

In July 2026, the sync PR #40 merged upstream's IndexedDB-events-cache +
PushSource refactor. Users immediately reported the "Search events..." box
becoming extremely slow (several seconds of unresponsiveness on type/clear).
Investigation (upstream issue
[judell/community-calendar#77](https://github.com/judell/community-calendar/issues/77),
mirrored in the fork's issue doc `upstream-issue-search-performance.md`) found
the root cause: the PushSource pattern emits twice on page load (cached
IndexedDB data, then network data), so the `processedEvents` pipeline runs
twice. `collapseLongRunningEvents` keyed its cache on object identity, so the
second run — same content, fresh object references — always missed and
recomputed (~254-336ms for ~3,200 events), blocking the main thread exactly
when the user starts typing.

PR #41 correctly **reverted** the sync wholesale (`30a00e2ee`), restoring the
pre-PushSource behavior and eliminating the regression at the cost of losing
the upstream refactor.

Upstream then fixed the root cause ([`dff810892`](https://github.com/judell/community-calendar/commit/dff810892)):
`collapseLongRunningEvents` now keys its cache on stable content
(`events.length` + first/last event id) instead of object identity, and adds
per-stage timing to `window._pipelineLog`. The fix was verified upstream on
5,985 real Bloomington events (run 2: 329ms MISS → 0.0ms HIT).

This raised two questions this ADR answers: (1) how should the fork re-adopt
the reverted architecture now that the root cause is fixed, and (2) what
verification is required before merging performance-sensitive upstream changes
into a fork whose history includes a revert of the same code.

## Decision

1. **Re-adopt the PushSource + IndexedDB architecture via a full upstream
   merge, with a verification gate.** The 2026-08-02 sync
   (`chore/upstream-sync-2026-08-02`) merges `upstream/main` wholesale and
   resolves the `xmlui/shell.js` conflict by adopting upstream's version. The
   revert (PR #41) was the correct response to the regression; the re-adoption
   is correct because upstream fixed the root cause and the fork verified it.

2. **Every upstream sync must pass a headless verification benchmark before
   merge.** `scripts/bench_collapse_long.js` loads the merged `xmlui/helpers.js`
   in Node, runs `collapseLongRunningEvents` twice with fresh object references
   (simulating cached emit → network emit), and asserts run #2 is a cache HIT
   at ~0ms with identical results. It exits non-zero on regression. Synthetic
   events by default; `--events <file.json>` accepts real payloads. On this
   sync: run#1 90.5ms (computed), run#2 0.1ms (HIT), run#3 0.0ms (HIT). A
   negative control against the pre-fix `helpers.js` (identity-keyed cache)
   fails as expected (25ms MISS, exit 1).

3. **Bloomington-only pruning happens inside the merge resolution.** The fork
   serves Bloomington only (cities.json keeps only `bloomington`; `ENABLED_CITIES`
   gates the workflow). Non-Bloomington city directories, `rss/*`, and
   city-specific data that upstream re-adds are removed during the merge
   (`git rm`), and modify/delete conflicts on previously-deleted files resolve
   as keep-deleted. The keepours merge driver (`.gitattributes`) protects
   `xmlui/config.json`, `cities.json`, and `cities/*/feeds.txt`. City-specific
   scraper *scripts* are kept — they are upstream-maintainable code, and the
   workflow's gated city blocks are neutralized by `ENABLED_CITIES`.

4. **Residual performance items are tracked as fork issues, not sync
   blockers.** The upstream fix resolves the felt search lag; the remaining
   cold compute and payload size are follow-ups:
   - [#45](https://github.com/B-Square-Bulletin/community-calendar/issues/45):
     consolidate PushSource emissions (avoid the double pipeline run entirely)
   - [#46](https://github.com/B-Square-Bulletin/community-calendar/issues/46):
     paginate the 4.2MB `deduplicated_events` payload

## Consequences

**Easier:**
- Future syncs have a concrete, runnable verification gate for
  performance-sensitive changes — the fork no longer merges unverified
  upstream performance work, and the PR review shows evidence, not claims.
- The revert→re-adopt history is documented, so future readers understand why
  PR #40 was reverted and then re-adopted (both were correct, at different times).
- `window._pipelineLog` makes the pipeline self-diagnosing in production.

**Harder:**
- Merge resolution now includes pruning non-Bloomington content on every sync
  (mitigated by the keepours driver and the `ENABLED_CITIES` gating).
- The benchmark covers `collapseLongRunningEvents` only; other perf-sensitive
  pipeline stages need their own checks if they regress.

**Unchanged:**
- origin/main remains branch-protected; syncs land via PR.
- The fork's intentional divergence from upstream (ADR 0002) is preserved.

## Alternatives Considered

- **Keep the revert permanently (skip PushSource).** Avoids the architecture
  but abandons upstream's XMLUI core — every future sync re-litigates
  `shell.js` conflicts, and the fork maintains a fork of a fork. Rejected:
  the root cause is fixed and verified.
- **Selective cherry-pick of the fix only.** Smaller diff, but the fix is
  meaningless without the PushSource architecture it fixes, and partial syncs
  compound conflict debt. Rejected in favor of the full merge (question 1 of
  the sync grilling session).
- **Verify via live browser instrumentation only.** The most faithful signal
  but manual, needs a running app + Supabase keys, and isn't reproducible in
  review. Rejected in favor of the headless Node benchmark, with `--events`
  keeping a real-data path open.
- **Automate pruning (replace `align-fork.sh` restore logic).** Worth doing,
  but out of scope for this sync PR — tracked separately to keep the sync
  branch pure (ADR 0003).

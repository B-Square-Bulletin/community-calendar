# 0003. Contributing Fork Fixes to Upstream

Date: 2026-08-02

## Status

Accepted

## Context

This repository is a hard fork of judell/community-calendar (see ADR 0002). Files shared between the two repos have diverged: for example, `tests/test_timezone_pipeline.py` exists in both origin/main and upstream/main but with different content (the fork extracted its test helpers into `tests/helpers.py`; upstream keeps them inline). A consequence surfaced in August 2026 while fixing a date-drift failure in that test file: a fix commit created on top of origin/main **does not cherry-pick cleanly onto upstream/main** — the merge produces a content conflict.

At the same time, the fork uses `chore/upstream-sync-*` branches to merge upstream changes. Those branches must carry only sync work, so an unrelated fix cannot live on one.

## Decision

1. **One branch per target main.** A fix destined for upstream gets two branches: `fix/<slug>` based on `origin/main` (opened as a PR into origin/main) and `fix/<slug>-upstream` based on `upstream/main` (opened as a cross-fork PR from B-Square-Bulletin to judell/community-calendar). The change is **re-applied** against each target's version of the files, not cherry-picked across targets. The resulting commits have different SHAs and must be kept logically in sync.
2. **Sync branches stay clean.** `chore/upstream-sync-*` branches carry only upstream-merge work. If an unrelated fix lands on one, move it off (the commit remains reachable on its own `fix/` branch, so resetting the sync branch loses nothing).
3. **Upstream contributions are cross-fork PRs.** Pushed from this fork's `fix/*-upstream` branches to `judell/community-calendar:main` via the normal GitHub PR flow.
4. **Fork-side delivery is always a PR.** origin/main is branch-protected (ADR 0002); fixes reach it through PRs, never direct pushes.

## Consequences

**Easier:**
- A future contributor sees why two same-named commits with different SHAs exist for one fix
- Sync branches remain reviewable and mergeable without unrelated noise
- Upstream reviewers get a fix adapted to their tree, not a conflicting cherry-pick

**Harder:**
- Two PRs to open, review, and merge per upstream-bound fix
- The upstream-adapted commit can drift from the fork version; both must be updated when the fix evolves

**Unchanged:**
- Fork model and main protection (ADR 0002)
- The feeds table / scraper registration workflows

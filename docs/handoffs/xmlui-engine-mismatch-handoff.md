# Handoff: XMLUI Engine Mismatch (stale engine from faulty sync merges)

**Date:** 2026-08-03
**From session:** issue #46 payload work (`perf/issue-46-payload-slimming`)
**Next session focus:** Fix the stale XMLUI engine in a dedicated change (separate from the payload work).

---

## The Problem

The fork's XMLUI engine bundle (`xmlui/xmlui/xmlui-standalone.umd.js`) is
**`bdd64bc0d`** — an *older* build that predates both the `PushSource`
component and the tooltip accessibility fix — while the app code (shell.js,
helpers.js) comes from upstream's PushSource era. The fork has been running a
**half-migrated stack**: old engine + new app code.

Measured consequence (production site, 2026-08-02/03): shell.js's boot-time
prefetch (`window.subscribeEvents`) is defined but **never wired** — the
engine doesn't know the `<PushSource>` component, so Main.xmlui kept its own
DataSource. Every page load therefore downloads the full 4.2MB payload
**twice** (once to an IndexedDB cache nobody reads, once for rendering). This
was the largest single cost in the cold-TTFC baseline (6.4s).

## Root Cause

1. The 2026-07-26 upstream sync (PR #40) merged upstream's engine update
   (which included PushSource, `e89d56430`).
2. PR #41 reverted that sync **wholesale** (`30a00e2ee`) after the search
   regression (upstream issue #77), rolling the engine back past the
   PushSource-era bundles to `bdd64bc0d`.
3. The 2026-08-02 sync (PR #47, "Merge upstream/main, keep Bloomington only")
   re-merged the app code but **silently kept the old engine** — zero files
   changed in `xmlui/xmlui/` in that merge (`git diff 95e66331e^1 95e66331e
   -- xmlui/xmlui/` is empty).

No one noticed because the app still rendered; the mismatch only surfaced as
the orphaned prefetch + double fetch.

## Evidence (verified 2026-08-03)

| File | Fork (current) | Upstream/main |
|---|---|---|
| `xmlui-standalone.umd.js` | identical to `bdd64bc0d` (4,254,301 bytes, **0** `PushSource` matches) | `ffbb7bb66` build, XMLUI **v0.12.30** (built 7/21/2026), **3** `PushSource` matches, 6,229,492 bytes |
| `xmlui-grid-layout.css/js`, `xmlui-masonry.js` | fork versions (older) | newer upstream versions |
| `xmlui-parser.es.js`, `xmlui-calendar.js/css`, `xs-diff.html` | already identical to upstream | same |

The fork's "tooltip accessibility patch" (`ffbb7bb66` commit message) is
**upstream code, not a fork divergence** — `ffbb7bb66` is in upstream/main,
and the final tooltip fix was upstreamed to xmlui-org as
[#3645](https://github.com/xmlui-org/xmlui/pull/3645) ("Restore tooltip-derived
accessible names on icon-only triggers"). Vendoring upstream's engine loses
nothing fork-specific.

## The Fix (separate change)

1. **Vendor upstream/main's `xmlui/xmlui/`** directory wholesale (engine,
   grid-layout, masonry). `upstream/main` has not moved the engine past
   `ffbb7bb66`, so merge-point == current.
2. **Bump `xmlui/version.txt`** (cache-busting; the auto-generated metadata
   builds bump it too, but bump manually so the new bundle propagates
   immediately).
3. **Wire Main.xmlui to the prefetch via `PushSource`** (upstream's intended
   design) and remove the duplicate DataSource fetch — this is the behavior
   fix that makes the engine update meaningful. The orphaned `subscribeEvents`
   machinery in `shell.js` becomes live.
4. **Add the engine dir to the sync verification protocol** (ADR 0004) so a
   future sync cannot silently keep a stale engine again.
5. **Verify:** app renders with the new engine; `xmlui/test.html` unit groups
   all pass; no regressions in search/render/picks/enrichments.

## Already Done (in `perf/issue-46-payload-slimming`)

- Commit **`64aa58b3b`** "chore(xmlui): vendor upstream XMLUI engine v0.12.30
  (PushSource)" — the 4 engine files + version.txt bump. **Cherry-pick this
  commit (or the 4 files + version.txt) onto the new engine-fix branch.**
- Commit **`b057d8691`** "perf(payload): slim initial events payload;
  background description map" — includes the PushSource wiring in
  `xmlui/Main.xmlui` + `xmlui/shell.js`. The payload half of this commit is
  **under reconsideration** (see below); the PushSource wiring part is wanted
  as part of the engine fix.
- Verified on the new engine (local server, real Supabase data): renders,
  `test.html` all unit groups pass (the "Real Data (0/1)" failure is a
  pre-existing harness bug — `SUPABASE_URL` is undefined on test.html, fails
  identically on production).

## Related But Under Reconsideration (do NOT merge as-is)

The payload work on `perf/issue-46-payload-slimming` measured only **~17%
cold-TTFC improvement** (6,857ms → 5,713ms mean, local A/B) against a target
of ≤55% of baseline. The dominant TTFC cost is XMLUI engine boot + first
render (~4-5s of ~6s), untouched by payload strategy. **The user wants to
reconsider approaches before proceeding.** Do not push or open PRs for the
payload work until that decision is made. Note: **ADR 0005
(`docs/adr/0005-payload-strategy-slim-list-and-description-map.md`) is marked
"Accepted" but its premise (the 45% target) was not met — its status should be
revisited** (likely "Superseded"/"Proposed" with the measured numbers).

Key artifacts to reference (do not duplicate):
- `docs/adr/0005-payload-strategy-slim-list-and-description-map.md`
- `docs/adr/0004-upstream-sync-verification-protocol.md`
- Commit `64aa58b3b`, `b057d8691`, `bb56841ac` on `perf/issue-46-payload-slimming`
- `CONTEXT.md` — glossary entries TTFC / fetch paging / render paging
- The xmlui source repo: `/Users/jogoodma/development/bsquarebulletin/xmlui`
  (runtime-parse architecture: `StandaloneApp.tsx` fetches `Main.xmlui` at
  runtime; `index-standalone.ts` is the UMD entry; `PushSourceLoader.tsx` is
  the PushSource implementation)

## Suggested Skills

- `using-git-worktrees` — create the dedicated engine-fix worktree
- `github-pr-workflow` / `github-issues` — open the fix PR + issue
- `verification-before-completion` — engine swap needs browser verification
  (local static server + real Supabase data; the iframe cold-TTFC probe
  technique is described in this session's baseline work)
- `code-review` — review the vendored-engine diff
- `systematic-debugging` — if the engine swap surfaces render regressions

## Sensitive Info

None in this doc. Do NOT copy the Supabase publishable key from
`xmlui/config.json` into any doc or commit.

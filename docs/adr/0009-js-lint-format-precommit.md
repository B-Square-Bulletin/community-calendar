# 0009. Prettier + ESLint for JS, Gating in Makefile and Pre-commit

Date: 2026-09-11

## Status

Accepted.

## Context

The JS side (~15 hand-written files: `xmlui/*.js`, `tests/js/`, `scripts/`,
root configs) had no linter or formatter: `make lint`/`format` and
`.pre-commit-config.yaml` were Python/ruff-only (see ADR-0006), and
`package.json` carried only vitest + Playwright. The first `eslint:recommended`
baseline surfaced 98 findings — mostly the legacy `catch (e) {}` pattern,
CDN globals (`rrule`, `supabase`), and dead code — plus two static chrome
checks that asserted the old source formatting verbatim.

## Decision

1. **Prettier owns style** (`printWidth: 100` to match ruff, single quotes,
   `es5` trailing commas, `lf`). **ESLint flat config owns correctness**
   (`eslint:recommended` only, no stylistic rules), with browser-vs-node
   globals split and `ignores` for vendored `xmlui/xmlui/`, `legacy/`, and
   Deno-style `supabase/functions/`.
2. **No JS typecheck in v1** — "typecheck" stays Python-only per ADR-0006.
3. **Makefile split + aggregate:** `lint-python`/`format-python` keep today's
   ruff behavior verbatim; new `lint-js`/`format-js` delegate to
   `pnpm run lint:js`/`format:js`; `lint`/`format` aggregate both and
   `make check` covers all.
4. **Pre-commit extends the existing framework** (no Husky): check-only
   `prettier --check` + `eslint` hooks filtered to `js|mjs|cjs`, so the new
   JS hooks never rewrite files — fixing stays explicit via `make format-js`.
   (Existing ruff hooks still rewrite staged Python files.)
5. **Baseline cuts stay minimal and behavior-preserving:** legacy
   `catch (e) {}` preserved via `caughtErrors: none` + `allowEmptyCatch`;
   CDN/CJS-interop globals declared in config; only truly unreferenced dead
   code removed (`toggleOneClickPickAndSave`, `stampPicked`, `WEEK_MS`,
   `_dedupedEventsLastInput`, bench `label` param); `utcToLocal` call sites
   use the explicit `window.` form; two chrome-check regexes made
   whitespace-tolerant of Prettier's `function (` / arg-wrapping style.

## Consequences

**Easier:**

- `make lint` gates JS + Python together; pre-commit gives fast staged-file
  feedback for both languages.
- One style authority per language (Prettier / ruff) ends formatting debates.

**Harder:**

- First `make format-js` rewrote every in-scope JS file (quote/wrap churn);
  future chrome-check regexes must tolerate Prettier wrapping (`\s*`).
- ESLint recommended will flag new dead code and cross-file globals
  immediately — the intended strictness, but noisier than before.

## Alternatives Considered

### Biome (single binary lint + format)

Faster and fewer deps, but Prettier + ESLint is the familiar pairing and
mirrors ADR-0006's split (one formatter gates, slow checkers stay out of
pre-commit). Revisit if JS tooling cost becomes an issue.

### Husky + lint-staged (setup-pre-commit skill default)

Rejected because the repo already standardizes on the `pre-commit`
framework with `repo: local` hooks; adding Husky would mean two hook
runners. The skill's intent (JS + Python lint/format/typecheck in
pre-commit) is met through the framework instead — minus type checkers,
which stay out of pre-commit per ADR-0006 (slow, project-wide).

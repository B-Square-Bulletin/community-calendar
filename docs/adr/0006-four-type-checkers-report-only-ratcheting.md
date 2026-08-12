# 0006. Four Type Checkers, Ratcheted from Report-Only to Gating

Date: 2026-08-09

## Status

Accepted. The phased rollout completed 2026-08-12 (issue #60): the type-checker
baseline is clean across `scripts/`, `scrapers/`, and `tests/`, and all four
checkers gate in `make lint` and the PR CI `lint` job.

## Context

The Python codebase (~200 files: `scripts/`, `scrapers/`, `tests/`) has grown with essentially no static analysis: zero `# type: ignore` comments today, and a large fraction of files with no type hints. Running any type checker across it will produce thousands of diagnostics.

We wanted formatting and linting enforced locally and (eventually) in CI, but we did not want a hard gate to block all work while the codebase is brought up to type-clean. We also chose to run four independent type checkers (ty, pyrefly, pyright, zuban in mypy mode) rather than one, because each catches a different class of issue and they cross-check each other — at the cost of overlapping noise.

## Decision

Run **four type checkers** (ty, pyrefly, pyright, zuban in mypy mode) plus **ruff** (format + lint), with a phased enforcement policy that is now complete:

1. **Ruff gates.** `make lint` fails on `ruff format` and `ruff check` violations. `legacy/` is excluded (abandoned code).
2. **Type checkers gate.** `make lint` runs all four checkers and fails on any diagnostics. PR CI runs the same strict target (`make lint`) and blocks merges, so an introduced finding fails the PR. The checkers were report-only during the ratchet (phase 1) and flipped to gating once the baseline reached zero. After the flip, the strictness settings were tightened — pyright moved from `basic` to `standard` (zero new findings), and zuban/mypy turn on `check_untyped_defs` so the bodies of unannotated functions are checked instead of silently skipped.
3. **Ratcheting complete.** The baseline was driven to zero across `scripts/`, `scrapers/`, and `tests/` with annotations and narrowing only. The repo carries no `# type: ignore` comments, so any future suppression must be justified at the line it silences.
4. **Not in pre-commit.** The four checkers are project-wide and slow; pre-commit runs only ruff (fast, scoped to staged files), so commits stay quick while the full suite runs via `make lint` and CI.

Configuration for all checkers lives in `pyproject.toml` (`[tool.pyright]`, `[tool.ty]`, `[tool.pyrefly]`, and a `[tool.mypy]` section read by zuban's mypy mode — zuban follows mypy's convention of `[tool.mypy]` in `pyproject.toml`, not a top-level `[mypy]`). All four checkers exclude the same directories (`legacy/`, `graphify-out/`, `.venv`, `.worktrees`) so they cover the same file set. pyright runs `typeCheckingMode = "standard"`; zuban/mypy run with `check_untyped_defs = true` (untyped function bodies are checked, not skipped) and `warn_unused_ignores = true`.

### Type stubs

The dev group includes typeshed stub packages for the scraper backbone libraries — `types-beautifulsoup4`, `types-html5lib`, `types-pytz`, `types-icalendar`, plus `lxml-stubs` — so the checkers see real types for `bs4`, `lxml`, `pytz`, and `icalendar` instead of opaque `Any`. (Note: `types-lxml` was rejected because recent versions hard-require `beautifulsoup4~=4.13`, which would force upgrading the pinned `beautifulsoup4==4.11.1`; `lxml-stubs` has no such dependency. `feedparser`, `recurring-ical-events`, and `anthropic` have no typeshed stubs, so they remain `Any`.)

## Consequences

**Easier:**

- Gradual path to type-cleanliness without a months-long red gate
- Four checkers catch issues a single checker would miss (each has different inference/coverage strengths)
- One config home (`pyproject.toml`) for all static-analysis tools

**Harder:**

- Four checkers produce four overlapping diagnostic sets; triage cost is real
- All four gate in CI, so an introduced finding in any one of them blocks a PR — stricter than a single-checker setup
- The full four-checker lint run is slower than ruff alone, so the fast path stays in pre-commit

## Alternatives Considered

### Single authoritative type checker

Run only pyright (or only mypy).

**Rejected because:** each checker has blind spots, and the team wanted the cross-checking breadth of the modern checkers (ty, pyrefly) plus the mature, config-compatible baseline (pyright, zuban/mypy).

### Gate all four checkers in CI from day one

Block PRs on all four passing immediately.

**Rejected because:** the codebase is far from type-clean; a hard gate now would halt all contribution while the baseline is fixed, contradicting the phased local-first approach.

### Type checkers in pre-commit

Run the four checkers as pre-commit hooks.

**Rejected because:** they are slow and project-wide, while pre-commit should be fast and file-scoped. Ruff alone in pre-commit gives fast feedback; the full suite runs via `make lint` and, later, CI.

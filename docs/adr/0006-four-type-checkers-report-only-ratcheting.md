# 0006. Four Type Checkers with Report-Only Ratcheting

Date: 2026-08-09

## Status

Accepted

## Context

The Python codebase (~200 files: `scripts/`, `scrapers/`, `tests/`) has grown with essentially no static analysis: zero `# type: ignore` comments today, and a large fraction of files with no type hints. Running any type checker across it will produce thousands of diagnostics.

We wanted formatting and linting enforced locally and (eventually) in CI, but we did not want a hard gate to block all work while the codebase is brought up to type-clean. We also chose to run four independent type checkers (ty, pyrefly, pyright, zuban in mypy mode) rather than one, because each catches a different class of issue and they cross-check each other — at the cost of overlapping noise.

## Decision

Run **four type checkers** (ty, pyrefly, pyright, zuban in mypy mode) plus **ruff** (format + lint), with a phased enforcement policy:

1. **Ruff gates now.** `make lint` fails on `ruff format` and `ruff check` violations. `legacy/` is excluded (abandoned code). The existing repo is cleaned up once in phase 1 (auto-fix what ruff can, manually the rest).
2. **Type checkers are report-only for now.** `make lint` runs all four checkers, captures their exit codes, and prints a summary, but does not fail on their diagnostics. They are configured leniently (e.g. pyright `typeCheckingMode = "basic"`, mypy/zuban defaults) and run over the whole repo.
3. **Ratcheting.** As files are annotated, the type-checker baseline drops. Once the baseline is clean, `make lint` is flipped to fail on type-checker errors too, and CI inherits the strict target.
4. **Not in pre-commit.** The four checkers are project-wide and slow; pre-commit runs only ruff (fast, scoped to staged files), so commits stay quick while the full suite runs via `make lint` and, later, CI.

Configuration for all checkers lives in `pyproject.toml` (`[tool.pyright]`, `[tool.ty]`, `[tool.pyrefly]`, and a `[tool.mypy]` section read by zuban's mypy mode — zuban follows mypy's convention of `[tool.mypy]` in `pyproject.toml`, not a top-level `[mypy]`).

### Type stubs

The dev group includes typeshed stub packages for the scraper backbone libraries — `types-beautifulsoup4`, `types-html5lib`, `types-pytz`, `types-icalendar`, plus `lxml-stubs` — so the checkers see real types for `bs4`, `lxml`, `pytz`, and `icalendar` instead of opaque `Any`. (Note: `types-lxml` was rejected because recent versions hard-require `beautifulsoup4~=4.13`, which would force upgrading the pinned `beautifulsoup4==4.11.1`; `lxml-stubs` has no such dependency. `feedparser`, `recurring-ical-events`, and `anthropic` have no typeshed stubs, so they remain `Any`.)

## Consequences

**Easier:**

- Gradual path to type-cleanliness without a months-long red gate
- Four checkers catch issues a single checker would miss (each has different inference/coverage strengths)
- One config home (`pyproject.toml`) for all static-analysis tools

**Harder:**

- Four checkers produce four overlapping diagnostic sets; triage cost is real
- Report-only mode means type errors are easy to ignore while the baseline is large
- Risk that "report-only" lingers — the flip to gating requires someone to actually drive the baseline down

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

# 0014. Python 3.14 Toolchain Floor

Date: 2026-09-26

## Status

Accepted. Supersedes the Python 3.10 pin recorded in
[0005](0005-uv-for-python-dependency-management.md).

## Context

Since the uv migration (ADR 0005) the project has pinned the Python toolchain
to 3.10 via `.python-version`, `requires-python = ">=3.10"`, four tool-target
settings, and three CI `python-version` values. Python 3.10 reaches end of
life in October 2026, and the fork no longer has any 3.10-only code.

We evaluated moving the whole toolchain to the latest 3.14 patch line
(3.14.7 at the time of writing). The measured facts that shaped the decision:

- Every runtime and dev dependency resolves and imports on 3.14; refreshing
  `uv.lock` changes no package versions and only drops the `exceptiongroup`,
  `tomli`, and `typing-extensions` backport markers.
- All four type checkers and ruff accept a 3.14 target at their current pins.
- Raising the ruff target to `py314` changes source in two ways: the formatter
  rewrites `except (A, B):` to the PEP 758 form `except A, B:` in 21 files,
  and two previously dormant rule families activate — `UP017` (114 sites) and
  `TC003` (9 sites).

## Decision

1. Pin the toolchain to the **3.14 minor line** in `.python-version` and CI
   (`python-version: 3.14`), so patch/security releases are picked up
   automatically rather than chased by hand. Raise `requires-python` to
   `>=3.14` and set every tool target (`ruff`, `pyright`, `ty`, `mypy`) to
   3.14; add an explicit `python-version` for `pyrefly`.
2. **Accept PEP 758 syntax.** Ruff now formats `except (A, B):` without
   parentheses. The change is semantics-preserving on 3.14 and is kept
   isolated in its own commit so `.git-blame-ignore-revs` can hide it from
   blame.
3. **Adopt the newly activated lint idioms** rather than suppressing them:
   rewrite `datetime.timezone.utc` to `datetime.UTC` (`UP017`), and resolve
   each annotation-only standard-library import (`TC003`) individually —
   deferring the import under `TYPE_CHECKING` only where nothing introspects
   annotations, otherwise leaving a one-line justified `# noqa`.
4. Keep dependency churn **minimal**: re-resolve `uv.lock` for the new floor
   but do not use the bump as cover for a dependency upgrade. No package
   versions change; only the `exceptiongroup`, `tomli`, and `typing-extensions`
   backport markers drop out. The stale runtime pins (e.g. `requests` /
   `urllib3`) are a separate concern.
5. Do **not** adopt the free-threaded build (`3.14t`); the workload is
   I/O-bound scrapers that would not benefit.

## Consequences

**Easier:**

- The interpreter matches the CI runtime, the lockfile, and the declared
  `requires-python` floor, so tool behavior no longer has to be reasoned about
  against a lower target.
- Modern idioms (`datetime.UTC`) and 3.14-only syntax are now lint-enforced,
  so new code cannot drift back to the older forms.
- `.python-version` as a minor pin keeps patch updates automatic.

**Harder:**

- Contributors on Python 3.10–3.13 can no longer run the toolchain; they must
  install a 3.14 interpreter (`uv sync` does this from `.python-version`).
- Source containing PEP 758 syntax is no longer parseable by ≤3.13 tooling or
  reviewers without that context.
- `TC003` suppressions require per-site justification, so the annotation-only
  imports carry a little more reviewer attention.

## Alternatives Considered

### Stay on Python 3.10

Deferred because 3.10 is at end of life (October 2026), and the repository has
no remaining 3.10-specific code; the 3.10 `datetime.fromisoformat()` workarounds
in several scrapers are harmless on newer versions.

### Floor at 3.13 instead of 3.14

Rejected because it keeps the `TC003` (and PEP 758) questions open while
providing none of the 3.14-only benefits that motivated the bump, and it would
leave the declared floor below what CI actually tests.

### Keep ruff at `target-version = "py313"` to avoid the churn

Rejected: it would deliberately mismatch the formatter/linter target from the
runtime floor, so `UP017` would stay suppressed and the 3.14-only syntax would
never be consistently applied. The churn is mechanical and reviewable, and the
formatter half is hidden from blame.

### Pin the exact patch (`3.14.7`)

Rejected: it forces a manual bump for every security release. The minor-line
pin lets `uv` and `setup-uv` select the newest 3.14.x automatically.

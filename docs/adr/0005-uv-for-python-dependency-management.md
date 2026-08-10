# 0005. uv for Python Dependency Management

Date: 2026-08-09

## Status

Accepted

## Context

The project manages Python via `requirements.txt` (11 pinned prod deps) and `requirements-dev.txt` (pytest + `-r requirements.txt`), installed by `python3 -m venv` + `pip` in the Makefile and by `pip install -r ...` in CI workflows. There is no `pyproject.toml`.

This works but has gaps:

- No lockfile — CI and local dev can resolve different transitive versions despite top-level pins
- Venv bootstrap (`venv` + `pip`) is slower and less deterministic than uv's managed environments
- Dev tools (ruff, type checkers) have no project-scoped pinned home
- No central place for tool configuration (ruff, pyright, mypy, etc. each need their own file or a `pyproject.toml`)

We evaluated uv as the package manager and lockfile source, and accepted the migration cost because the repo has ~200 Python files and several CI pipelines that install deps.

## Decision

Use **uv** for dependency management, with `pyproject.toml` as the single source of truth:

1. Create `pyproject.toml` with `[project]` dependencies migrated from `requirements.txt`, `requires-python = ">=3.10"`, and dev tools in a `[dependency-groups].dev` group (pytest, pytest-cov, ruff, ty, pyrefly, pyright, zuban).
2. Commit a `uv.lock` lockfile. `uv sync` installs the environment from it.
3. Pin the toolchain to Python 3.10 via `.python-version` (`uv python pin 3.10`) so local venv and CI match.
4. For the short term, keep `requirements.txt` / `requirements-dev.txt` as **generated artifacts** exported from the lockfile (`uv export`) so CI workflows that still `pip install -r requirements*.txt` keep working during the phased CI migration. They are refreshed via `make export-requirements`.
5. Replace `make setup-python` (venv + pip) with `uv sync`, and `make test-python` with `uv run pytest`.

The CI migration to `astral-sh/setup-uv` + `uv sync` happens in a later phase (see ADR 0002 for fork/main protection context around PR-based changes).

## Consequences

**Easier:**

- `uv.lock` pins the full resolution — reproducible environments across contributors and CI
- One manifest for deps, dev tools, and tool configuration
- Faster, deterministic venv creation via `uv sync`
- Tool versions (ruff, pyright, etc.) are project-scoped and locked, not global installs

**Harder:**

- Two sources of truth briefly coexist (`pyproject.toml` + generated `requirements*.txt`); they can drift if `make export-requirements` is forgotten
- CI still uses pip until the phased migration completes
- Team members must adopt `uv` instead of `pip` for day-to-day work

## Alternatives Considered

### Keep `requirements*.txt` and manage with uv

Leave the manifests as-is and only use uv to install them.

**Rejected because:** no single home for tool config, dev-deps remain a `-r` include, and we'd forgo the unified `[dependency-groups]` model.

### Poetry or PDM

Feature-equivalent managers, but uv is the same tool we already use for `uv tool` installs and provides the simplest `uv export` path for keeping the CI pip artifacts working.

### Pipenv

Rejected: less maintained, no equivalent of `uv export` for lockfile → requirements artifacts.

### Migrate everything at once (delete `requirements*.txt` immediately)

Rejected: CI workflows (`validate-pr.yml`, `generate-calendar.yml`) still `pip install -r ...`. Deleting the artifacts before CI migration would break the pipeline. The phased approach keeps CI green while the local toolchain moves first.

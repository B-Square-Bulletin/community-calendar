# 10 — Retire requirements*.txt

**What to build:** The generated pip requirement artifacts stop being a source of truth. The two requirements files are deleted and the Makefile target that regenerates them is removed; `uv.lock` (via `pyproject.toml`) is the single source of truth for the environment. ADR 0005 is updated to record that the phased migration is complete and the generated artifacts are retired.

**Blocked by:** 01 — Migrate Python CI to uv (no workflow may still install via pip when the artifacts disappear).

**Status:** ready-for-agent

- [ ] Both requirements artifacts are deleted from the repository
- [ ] The Makefile target that regenerates them is removed, along with its help-text entry
- [ ] No workflow or docs reference the requirements artifacts anymore
- [ ] `uv sync` from a clean checkout installs a working environment; tests and lint pass
- [ ] ADR 0005 reflects the completed migration (requirements artifacts retired; uv.lock is the single source of truth)

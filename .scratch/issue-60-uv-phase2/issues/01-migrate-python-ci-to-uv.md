# 01 — Migrate Python CI to uv

**What to build:** Both Python-based workflows install dependencies with uv instead of pip. The PR checks workflow and the calendar generation workflow switch from a Python toolchain action plus `pip install -r requirements*` to the uv setup action plus `uv sync`, keeping the pinned Python 3.10 toolchain (the calendar generation workflow keeps its apt system-dependency step for libxml2/libxslt). The two non-Python workflows (regression tests, CLI release) are untouched. After this, no workflow anywhere installs Python deps via pip.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] PR checks workflow installs deps via `astral-sh/setup-uv` + `uv sync`; no `pip install` remains
- [ ] Calendar generation workflow installs deps via `astral-sh/setup-uv` + `uv sync`; system deps step retained; no `pip install` remains
- [ ] Python toolchain stays pinned at 3.10 in both workflows
- [ ] Regression-tests and release-cli workflows unchanged
- [ ] A manual run of the calendar generation workflow (or a passing PR check run) proves the uv install path works end to end

# 02 — Add report-only lint job to PR CI

**What to build:** Every PR gets a lint job that runs the same checks as the local lint target (ruff format check, ruff check, and all four type checkers) and prints a summary of findings. The job is deliberately non-blocking — it reports diagnostics but does not fail the PR — so the existing type-checker baseline does not block merges while it is still being ratcheted down.

**Blocked by:** 01 — Migrate Python CI to uv (the lint job installs via uv and edits the same workflow file, so it lands after the uv migration).

**Status:** ready-for-agent

- [ ] A lint job runs in the PR checks workflow on every pull request
- [ ] It runs ruff (format + check) and all four type checkers over the Python codebase, mirroring the local lint target
- [ ] The job prints a findings summary but does not fail the PR (report-only)
- [ ] A test PR run shows the lint job with its summary while the PR still merges

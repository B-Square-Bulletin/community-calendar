# 03 — Ratchet scripts/ to type-clean

**What to build:** The build-pipeline scripts report zero diagnostics from all four type checkers. This is a pure typing pass: add type hints, narrow unions where the checkers flag them, and add `# type: ignore` comments only where a finding is genuinely unfixable. No runtime behavior changes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] pyright reports zero errors scoped to the scripts directory
- [ ] ty reports zero diagnostics scoped to the scripts directory
- [ ] pyrefly reports zero errors scoped to the scripts directory
- [ ] zuban (mypy mode) reports zero errors scoped to the scripts directory
- [ ] The Python test suite still passes; ruff still passes
- [ ] No `# type: ignore` added without a comment justifying it as genuinely unfixable

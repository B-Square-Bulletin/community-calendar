# 04 — Ratchet tests/ to type-clean

**What to build:** The Python test suite reports zero diagnostics from all four type checkers. A typing pass over the test files: add type hints, narrow unions the checkers flag, and suppress only genuinely unfixable findings with justified `# type: ignore` comments. No test behavior changes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] pyright, ty, pyrefly, and zuban (mypy mode) each report zero findings scoped to the tests directory
- [ ] The test suite still passes; ruff still passes
- [ ] No `# type: ignore` added without a comment justifying it as genuinely unfixable

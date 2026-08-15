# 05 — Ratchet shared scraper infrastructure to type-clean

**What to build:** The shared scraper foundation — the base scraper class and the reusable platform library it depends on — reports zero diagnostics from all four type checkers. This is the prefactor that makes the per-scraper batches land clean: nearly a hundred scrapers inherit from the base class, so typing the foundation first means the standalone scraper tickets annotate against real types instead of opaque `Any` and don't need rework when this lands.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The base scraper class and all shared platform modules report zero findings from pyright, ty, pyrefly, and zuban (mypy mode)
- [ ] Public signatures on the base class (event creation, fetching, output) are fully typed
- [ ] The test suite still passes; ruff still passes
- [ ] No `# type: ignore` added without a comment justifying it as genuinely unfixable

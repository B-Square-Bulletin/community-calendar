# 08 — Ratchet standalone scrapers to type-clean (batch 3)

**What to build:** The final third of the standalone scrapers report zero diagnostics from all four type checkers. A typing pass over each file in the batch: add type hints, narrow unions the checkers flag, and suppress only genuinely unfixable findings with justified `# type: ignore` comments. No scraping behavior changes. This is the last ratchet ticket — when it lands, the whole codebase is type-clean.

**Blocked by:** 05 — Ratchet shared scraper infrastructure (so annotations resolve against a typed base and don't need rework).

**Status:** ready-for-agent

- [ ] Every scraper file in the batch reports zero findings from pyright, ty, pyrefly, and zuban (mypy mode)
- [ ] The batch covers roughly a third of the standalone scrapers, with no file overlapping other scraper batches
- [ ] The test suite still passes; ruff still passes
- [ ] No `# type: ignore` added without a comment justifying it as genuinely unfixable

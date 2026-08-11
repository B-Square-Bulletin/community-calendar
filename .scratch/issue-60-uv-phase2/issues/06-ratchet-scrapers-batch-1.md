# 06 — Ratchet standalone scrapers to type-clean (batch 1)

**What to build:** The first third of the standalone scrapers (scrapers that are not part of the shared infrastructure) report zero diagnostics from all four type checkers. A typing pass over each file in the batch: add type hints, narrow unions the checkers flag, and suppress only genuinely unfixable findings with justified `# type: ignore` comments. No scraping behavior changes.

**Blocked by:** 05 — Ratchet shared scraper infrastructure (so annotations resolve against a typed base and don't need rework).

**Status:** ready-for-agent

- [ ] Every scraper file in the batch reports zero findings from pyright, ty, pyrefly, and zuban (mypy mode)
- [ ] The batch covers roughly a third of the standalone scrapers, with no file overlapping other scraper batches
- [ ] The test suite still passes; ruff still passes
- [ ] No `# type: ignore` added without a comment justifying it as genuinely unfixable

# 09 — Flip the type-checker gate

**What to build:** Type-cleanliness stops being aspirational and becomes enforced. The local lint target now fails when any of the four type checkers report findings (not just ruff), the report-only lint job in PR CI stops being report-only and actually blocks, and the type checkers become a required, blocking PR check. ADR 0006 is updated to record that the phased rollout is complete and type checkers now gate.

**Blocked by:** 02 — Add report-only lint job (the CI job being flipped to blocking); 03 — Ratchet scripts/; 04 — Ratchet tests/; 05 — Ratchet shared scraper infrastructure; 06, 07, 08 — Ratchet scraper batches 1-3 (the baseline must be zero before the gate flips).

**Status:** ready-for-agent

- [ ] The lint target exits non-zero when any type checker reports findings
- [ ] A PR with an introduced type-checker finding fails the lint job
- [ ] The lint job is a required check on the main branch and blocks merges on failure
- [ ] The full test suite and ruff still pass; `make lint` is green on a clean baseline
- [ ] ADR 0006 reflects the completed rollout (type checkers gating, not report-only)

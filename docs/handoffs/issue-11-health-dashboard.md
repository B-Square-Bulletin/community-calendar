# Handoff: Feed Health Dashboard Implementation Plan

**Created:** 2026-06-18  
**For:** Implementing GitHub issues #11, #21-#27 (Database-Backed Feed Health Reporting Dashboard)  
**Repo:** B-Square-Bulletin/community-calendar

## What We're Building

Issue #11 (parent PRD): replace the 2.6MB report.json blob committed to the repo daily with a Supabase-backed health reporting system. 7 child issues (#21-#27) break it into phases.

Issues: https://github.com/B-Square-Bulletin/community-calendar/issues/11 (parent), #21 through #27 (children)

## Current State

- Nothing implemented yet — no migrations, no edge function, no shared utility, no dashboard
- cities/bloomington/city.conf already exists (partial #23 completion)
- Four diverged parse_feeds_txt() in download_feeds.py, combine_ics.py, seed_feeds_from_txt.py, seed_feeds_table.py
- report.py has working anomaly detection (reads report.json history)
- No existing PRs for this work — all PRs are bug fixes / upstream syncs

## Implementation Plan (Dependency Order)

### Phase 0: #23 — Stale city cleanup + city.conf error
Deps: None. ~3-line change in update_report() to filter non-input cities. Change get_city_timezone() to error instead of silently falling back.

### Phase 1a: #21 — DB Schema
Deps: None (parallel with #22, #23). Supabase migration: feed_health, feed_anomalies tables, prune RPCs, RLS policies.

### Phase 1b: #22 — Shared Utility (lib/feed_utils.py)
Deps: None (parallel with #21, #23). Create slugify(), parse_feeds_txt(), build_stem_name_map(). Update 4 callers.

### Phase 2: #24 — Edge Function (report-health)
Deps: #21. POST endpoint, conflict resolution, pruning, retry. Post-deploy: turn off Require JWT.

### Phase 3: #25 — report.py Dual-Write
Deps: #22, #23, #24. Parse feeds.txt, POST to edge function, keep report.json write. Add env vars to workflow.

### Phase 4: #26 — Dashboard (health.html)
Deps: #21 (RLS). Static HTML + Alpine.js CDN, GitHub Pages.

### Phase 5 (future): #27 — Deprecate report.json
Deps: #25 + #26 stable. Do NOT implement before dual-write proven.

## Suggested Skills
- github-issues, github-pr-workflow — GitHub workflow
- hermes-agent — Supabase patterns
- test-driven-development — for feed_utils / edge function tests

## Key Constraints
- Branch names: fix/<issue>-<desc> or issue/<issue>-<desc>
- Conventional commits (fix:, feat:, chore:)
- Workflow gate: written summary + approval before multi-change code
- Test: .venv/bin/python -m pytest
- SQL lint: uvx sqlfluff lint --dialect postgres
- Type check: uvx ty check

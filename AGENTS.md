# Agent Strategies for Community Calendar

## Git Safety Rules

**This repository is a hard fork.** origin/main intentionally diverges from
upstream/main (judell/community-calendar). origin/main contains ~60
Bloomington-only commits (custom scrapers, fork-specific infrastructure,
city configuration) that are NOT on upstream/main.

### Prohibited operations on origin/main

- **NEVER** edit files on main, only work in a branch.
- **NEVER** reset origin/main to match upstream/main. The two branches are
  different histories by design.
- **NEVER** force-push to origin/main during normal development.
- **NEVER** push directly to origin/main from a feature branch (including `git push origin HEAD:main`). Always use a PR into main.
- **NEVER** assume a git-branch-recovery procedure that references
  upstream/main applies to this fork. Recovery procedures must preserve the
  fork's intentional divergence.

### If origin/main is accidentally overwritten

1. In a clone that previously fetched `origin/main`, find the prior tip SHA with `git reflog show origin/main`.
2. Prefer restoring via PR: `git switch -c restore-main <sha> && git push origin restore-main`, then open a PR into main.
3. If branch protection prevents restoration and an admin bypass is required, an admin may force-push the SHA: `git push origin <sha>:main --force-with-lease`.
4. Do NOT push upstream/main. Do NOT reset local main to upstream/main.
5. See [ADR 0002](docs/adr/0002-fork-model-and-main-protection.md) for the full context.

### Branch protection

origin/main requires pull requests. The `generate-calendar.yml` workflow is allowed to bypass this requirement for its automated commits (both the default GitHub Actions token and the `COMMUNITY_CALENDAR` token used for metadata pushes).

## Architecture (Compact)

XMLUI frontend → Supabase backend. Two source types feed the calendar:
**feeds** (ICS URLs in the `feeds` table, downloaded by `download_feeds.py`)
and **scrapers** (Python scripts in `scrapers/`, invoked by GitHub Actions).
The build pipeline merges all `.ics` files → `events.json` → Supabase DB →
GitHub Pages. Full domain model: [CONTEXT.md](CONTEXT.md).

Source attribution flows through a single `X-SOURCE` ICS header — NEVER put
"Source: X" text in event descriptions (the UI renders `source` separately).

## Discovery Philosophy

**We want COMPLETE coverage, not curated coverage.** This means:

1. **Long-tail events matter** — book clubs, craft meetups, neighborhood cleanups
2. **Schools are gold mines** — athletics, theater, concerts, parent nights
3. **Churches and community centers** — special events (not weekly services)
4. **If in doubt, add it** — missing events is worse than having too many

## Critical Rules (agents get these wrong)

- **The `feeds` table is the source of truth.** `feeds.txt` is auto-generated.
  Do NOT manually edit `feeds.txt` or the legacy `SOURCE_NAMES`/`SOURCE_URLS`
  dicts in `combine_ics.py`.
- **Always use `add_scraper.py`** to register scrapers — it handles both the
  workflow invocation AND the `pending_feeds.txt` metadata. Skipping it means
  the scraper runs but has no display name, or vice versa.
- **Edge function gotcha:** Redeploying any Supabase edge function resets
  "Require JWT" to ON. The workflow calls `load-events` with the anon key, so
  you must manually turn off "Require JWT" in the Supabase dashboard.
- **DDL files** (`supabase/ddl/`) document the live database state — they are
  not migration scripts.
- **`SOURCES_CHECKLIST.md`** in each city directory must be updated when
  sources are added or investigated.
- **Test before adding:** For Legistar, always test the API first (some cities
  have a web UI but a broken API). For scrapers, use `add_scraper.py --test`.
- **Prefer DuckDuckGo** over Google for discovery searches (Google often blocks).

## Provenance: Source Attribution

```
Scraper/Feed ICS  →  combine_ics.py  →  ics_to_json.py  →  Supabase DB  →  UI
   X-SOURCE           X-SOURCE           source column       source column    "Source: X"
```

- **Feeds:** `download_feeds.py` injects `X-SOURCE` and `X-SOURCE-URL` from the `feeds` table
- **Scrapers:** `BaseScraper.create_event()` sets `X-SOURCE` from the `--name` argument
- **Fallback:** `combine_ics.py` reads `feeds.txt` metadata for scrapers missing `X-SOURCE`

## Scraper Hygiene: Minimize Fetches

When a scraper fetches individual event pages (listing + detail pattern):

1. **Prefer APIs** that return dates in the listing (no detail fetch needed)
2. **Filter at listing stage** — skip past events by publish date, URL pattern, or position
3. **Cap pagination** — bound worst-case fetch count

Be a good citizen — don't hammer source sites.

## Pipeline Validation

```bash
python scripts/validate_pipeline.py --cities santarosa,bloomington,davis
python scripts/validate_pipeline.py --cities santarosa --strict
```

## Agent Skills

- **Issue tracker:** GitHub Issues. See `docs/agents/issue-tracker.md`
- **Triage labels:** `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`
  (see `docs/agents/triage-labels.md`)
- **Domain docs:** Single-context layout — `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`

## Reference Docs (read when needed, not in every session)

| Doc                                                    | Contents                                                                 |
| ------------------------------------------------------ | ------------------------------------------------------------------------ |
| [CONTEXT.md](CONTEXT.md)                               | Domain glossary, business rules, component relationships, data flows     |
| [docs/procedures.md](docs/procedures.md)               | Discovery workflow, geo-filtering, city registration, Meetup discovery   |
| [docs/scrapers.md](docs/scrapers.md)                   | Reusable scraper reference (MaxPreps, Legistar, GoDaddy, Songkick, etc.) |
| [docs/platforms.md](docs/platforms.md)                 | Platform techniques (Drupal, Wix, SeeTickets) and known limitations      |
| [docs/discovery-lessons.md](docs/discovery-lessons.md) | Real-world discovery lessons and edge cases                              |
| [docs/curator-guide.md](docs/curator-guide.md)         | Source discovery playbook with topical search categories                 |

## Known Platform Limitations

| Platform | Issue |
|----------|-------|
| **Planning Center/Church Center** | No public API; requires login |
| **Simpleview CMS** | Tourism sites; no public events API |
| **Cloudflare-protected sites** | Challenge pages block scrapers |
| **Facebook Events** | No public API since 2018 |
| **Granicus video** | RSS feeds at `{instance}.granicus.com/ViewPublisherRSS.php?view_id={N}` are **backward-looking only** (archived meeting videos). Not useful for upcoming events. Don't confuse with Legistar (also Granicus-owned), which has a forward-looking WebAPI. |
| **Bandsintown** | Website behind Cloudflare (403 on curl). REST API requires written approval from Bandsintown. Even with API access, no venue endpoint — only `/artists/{name}/events`. Not viable. |
| **SeeTickets / Eventim US** | SeeTickets US rebranded as Eventim in March 2025 (same platform). No public API — affiliate account required. Cannot filter by single venue. US platform runs legacy ASP.NET (`wafform.aspx`), unlike Eventim Europe which has an unauthenticated search API at `public-api.eventim.com`. Venues like Mystic Theatre and HopMonk use this platform for ticketing. |
| **BoardDocs** | Used by some cities for agenda publishing (e.g., `go.boarddocs.com/nc/raleigh/`). No public calendar API; LlamaIndex has a reader but it's for document extraction, not event feeds. |

# 0022. Generated Build Artifacts Live Only on the Archive Branch

Date: 2026-10-29

## Status

Accepted

## Context

The nightly build writes `rss/<city>-full.xml` (4 MB), `report/<city>/report.json`
(435 KB) and `cities/<city>/geo_filtered.json` from scratch every run. Two of
them were committed to `main` each night, so the repository grew by megabytes
per night, and every branch and clone paid for it. `build.log` was tracked, but
the build never committed it, so the copy in git was a stale log from an old
build.

The same class of bug had already appeared once: `report.json` was tracked but
not updated nightly, so the health page rendered a months-old build until it
was moved to the archive branch (#244).

Pages serves `main`'s root, so the committed RSS feeds and report slice were
also the live URLs.

## Decision

**`main` holds no file that a build regenerates.** The archive branch — force-
pushed as a single orphan snapshot on every run — is the published home for all
generated data: `report.json`, `report/<city>/report.json`, `rss/*.xml` and the
per-city ICS/JSON artifacts. The workflow restores the previous snapshot before
generating, so run-to-run state (RSS first-seen dates, report history) still
survives.

The health pages read their data from `raw.githubusercontent.com/.../archive/`,
both at the root (`report.html`) and per city
(`scripts/report_page_template.html`). The RSS feeds' `rel="self"` links point
at the archive copy, because the Pages path for them no longer exists. The
tracked `report/<city>/index.html` pages, `*.runs.json` run histories and
`feeds.txt` exports stay: they are pages or bounded state, not per-run output.

## Consequences

- A nightly run adds no multi-megabyte blob to `main`; the archive branch is
  bounded because it is replaced, not appended to.
- The RSS feed URLs change from `…/community-calendar/rss/<name>.xml` to the
  archive's raw URL. Nothing in the repository linked the old URLs, so the
  breakage is limited to anyone who subscribed by hand.
- A fork must edit the repository name in the page URLs and in the feeds'
  `FEED_BASE`, as it already had to for `report.html`
  (docs/syncing-your-fork.md).
- Local builds have no published baseline until `rss/` is restored from the
  archive, so a fresh clone announces every event as new in its first local
  `-latest.xml`.
- The first build after this change must run immediately after merge: until it
  does, the archive has no `rss/` or `report/` tree, so the per-city health page
  and the new feed URLs have nothing to serve.

## Alternatives Considered

- **Keep the feeds on `main` and commit them to a bounded `gh-pages`-style
  branch.** Preserves the URLs, but Pages serves one branch, so the whole site
  (XMLUI, config, pages) would have to move to that branch — a much larger
  change for the same result.
- **Keep the full feed tracked and stop committing the `-latest.xml`.** The
  full feed is the larger file and the one that changes every run, so this
  fixes nothing.
- **Derive the RSS baseline from `events.json` on the archive branch.** The
  feed's known-UID set and first-seen dates are feed-specific state (grouped
  members, carried pubDates); re-deriving them would re-announce events.

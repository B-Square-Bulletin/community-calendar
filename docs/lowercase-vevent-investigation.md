# Lowercase `BEGIN:VEVENT` Markers: Does the Pipeline Need to Care?

**Answer: No — do not make `combine_ics.py` case-insensitive for this.** A
lowercase marker is legal iCalendar, but none of the 8 live Bloomington
calendars sampled uses one, a lowercase body is already refused without
deleting its rows, and changing only `combine_ics.py` would leave attribution,
counting and the classifier disagreeing.

## Findings

1. **Lowercase is legal, at three independent levels.** RFC 5545 §3.1:
   "All names of properties, property parameters, enumerated property values
   and property parameter values are case-insensitive. However, all other
   property values are case-sensitive, unless otherwise stated." §3.5 repeats
   it for property names. §3.6.1 defines the block as
   `eventc = "BEGIN" ":" "VEVENT" CRLF`, and RFC 5234 §2.3 says "ABNF strings
   are case insensitive". So `begin:vevent` is a conformant `VEVENT`
   (<https://www.rfc-editor.org/rfc/rfc5545#section-3.1>,
   <https://www.rfc-editor.org/rfc/rfc5234#section-2.3>).

2. **The installed parser already accepts it.** `icalendar` 7.3.0
   (`pyproject.toml:11`) parsed a body with `begin:vcalendar`, `begin:vevent`
   and lowercase `dtstart`/`summary` into one `VEVENT` with the right values
   (checked in `.venv`). The limitation is the repo's regexes, not the library.

3. **The extractor is inconsistent today, not merely strict.** A lowercase
   `VEVENT` **with** `RRULE` yields events; the same body **without** `RRULE`
   yields zero (both verified against `combine_ics.extract_events`). Cause:
   `expand_rrules` parses via `icalendar` and `_serialize_vevent`
   (`scripts/combine_ics.py:316`) re-emits uppercase, while the non-recurring
   fallback regex (`scripts/combine_ics.py:477`) is uppercase-only. A lowercase
   feed would publish its recurrences and silently drop its one-off events.

4. **The classifier refuses it on purpose, and says why.** The
   `_scan_blocks` docstring (`scripts/ran_sources.py:70-80`) names "a `VEVENT`
   whose marker is not uppercase" as malformed because the verdict `calendar`
   must imply extractability; the gate is `readable` at
   `scripts/ran_sources.py:95`. The docstring states the reason from finding 3:
   a lowercase body can extract only partly.

5. **A lowercase feed is currently non-destructive.** `download_feeds` injects
   `X-SOURCE` only when the outcome is `CALENDAR`
   (`scripts/download_feeds.py:511-516`); `record_ran`
   (`scripts/ran_sources.py:144`) omits the stem from the manifest; and
   `load-events` scopes the sweep to the manifest
   (`supabase/functions/load-events/index.ts:132`;
   `docs/adr/0017-source-aware-stale-deletion.md`). Rows are kept; only a
   manifest-less build falls back to payload sources
   (`supabase/functions/load-events/scope.ts:9`), so finding 3's partial case
   can be swept there.

6. **Upstream shares the assumption.** `judell/community-calendar` `main` has
   the same uppercase-only regex and no classifier, so this is not a fork
   regression, and only downloaded feeds can be lowercase — scrapers emit via
   `icalendar` (`scrapers/lib/base.py:114`, `:232`):
   <https://github.com/judell/community-calendar/blob/main/scripts/combine_ics.py>.

## Places that assume uppercase

| Place | Role | Effect of a lowercase body |
|---|---|---|
| `scripts/combine_ics.py:477` | Authoritative extraction, non-recurring | Event dropped |
| `scripts/combine_ics.py:316` | Authoritative for expanded events | None: input is `icalendar` output |
| `scripts/combine_ics.py:449` | UID dedupe | Lowercase `UID:` not deduped |
| `scripts/combine_ics.py:539` | Globs every `*.ics` | Partial extraction (finding 3) |
| `scripts/ics_to_json.py:1139` | Authoritative JSON build | None: reads `combined.ics`, written uppercase at `combine_ics.py:637` |
| `scripts/download_feeds.py:76,87,92` | `X-SOURCE` attribution | No injection; marker split finds nothing |
| `scripts/ran_sources.py:95` | Manifest gate + event count | `not_calendar`, `events=0` |
| `scripts/report.py:66` | Advisory per-feed count | Undercounts |
| `scripts/report.py:878` | Advisory shell hint | Grep misses |
| `scripts/validate_pipeline.py:188` | Advisory CI count | Undercounts |
| `supabase/functions/validate-feed/index.ts:209` | Admin feed preview | Shows 0 events |
| `xmlui/helpers.js:1905`, `supabase/functions/my-picks/ics.ts:65` | Emit only | Not applicable |
| `tests/helpers.py:29`, `tests/test_ran_sources.py:105` | Fixtures + policy | Tests pin the uppercase rule |

## Empirical sample (11 feeds from `cities/bloomington/feeds.txt`)

| Feed (type) | Bytes | VEVENTs | Lowercase / mixed |
|---|---|---|---|
| Art Sanctuary (Google) | 91 KB | 166 | 0 |
| B-Square Gov (Google) | 11.3 MB | 9,423 | 0 |
| BHSN (Eventlink) | 348 KB | 1,273 | 0 |
| Bloomington Atheists (Meetup) | 7 KB | 10 | 0 |
| Bloominglabs (Google) | 123 KB | 270 | 0 |
| Edgewood HS (rbb schools) | 7 KB | 14 | 0 |
| Ellettsville (egov) | 11 KB | 27 | 0 |
| Eskenazi Museum (IU) | 115 KB | 25 | 0 |
| Community Band (Tribe) | 0 | 0 | n/a — empty body |
| Brown County Events (MEC) | 6 KB | 0 | n/a — HTML page |
| Brown County Art Guild (Tribe) | 226 B | 0 | n/a — "No events" page |

**0 of 8 valid calendars** used `begin:vevent`, `BEGIN:VEvent` or any other
mixed form at a line start. Quirks: the government feed is 11.3 MB with 9,423
events and heavy folding; three endpoints returned HTML or nothing, which the
classifier already labels `not_calendar`.

## What a change would cost

Making extraction case-insensitive is one flag at `combine_ics.py:477`, but
consistency also needs `download_feeds.inject_source_headers`, `combine_ics`'s
`UID:` dedupe and `URL:`/`X-SOURCE` presence checks, the
`ran_sources` readable gate, `report.py`, `validate_pipeline.py`,
`validate-feed/index.ts` and the tests — 6 files plus fixtures. If only
`combine_ics.py` changed:

- **No attribution.** `record_ran` still returns `not_calendar`, so
  `inject_source_headers` never runs; events enter `combined.ics` under the
  feeds.txt filename fallback, not their curated `X-SOURCE`.
- **Reporting drift.** `report.py` and `validate_pipeline.py` count zero while
  `combined.ics` has events; `local_build.summarize_output` says `not_ics`.
- **Sweep inconsistency.** The source is absent from the manifest but present
  in the payload; a manifest-less build falls back to payload sources and
  sweeps it.

## Recommendation

**Leave it alone for now.** The trigger is empirical: no sampled source needs
it, and the current outcome is a retained source with a named `not_calendar`
cause. The one real defect is finding 3; the cheapest correctness fix is to
make extraction agree with the classifier (drop the `icalendar` path's implicit
case tolerance), not to widen extraction.

If a lowercase feed does appear, normalise structural marker case **once, at
ingestion**, in `download_feeds.py` after the fetch and before `record_ran`:
uppercase only line-start `begin:`/`end:` markers, never folded continuations
or values. One function and one call site make every consumer consistent, but
it must not touch `DESCRIPTION:` values containing marker-like text and needs a
round-trip test over the feeds sampled above.

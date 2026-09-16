# Research: Visit Bloomington machine-readable surface

**Ticket:** [#118](https://github.com-B-Square-Bulletin/community-calendar/issues/118)
**Date:** 2026-09-15
**Method:** direct HTTP probing with a browser-like User-Agent, spaced to respect
`Crawl-delay: 2`. No files under `cities/` or `scrapers/` were modified; all
scraper output went to `/tmp`.

## TL;DR

Visit Bloomington (Simpleview CMS) has **three** machine-readable surfaces, in
increasing order of usefulness:

1. `GET /event/rss/` — 30 items, fixed cap, **no working pagination**, **date-only**.
2. Detail-page **schema.org JSON-LD** — date-only, truncated description; good
   address + geo.
3. A same-origin **JSON REST API** (`/includes/rest_v2/plugins_events_events_by_date/find/`)
   — full clock times, full descriptions, address/geo, categories, recurrence,
   `skip` pagination. Reachable with plain HTTP (token + session cookie), **no
   headless browser required**.

**Go/no-go: GO on the REST API. NO-GO on RSS + JSON-LD alone; NO headless
browser needed** (the API and the detail-page embedded JSON both expose clock
times over plain HTTP).

## 1. Simpleview event RSS — `https://www.visitbloomington.com/event/rss/`

- HTTP **200**, `Content-Type: application/rss+xml; charset=UTF-8`, 34,992 bytes.
- **Exactly 30 `<item>` elements.** This is a hard cap.

### Pagination is ignored

Every query-param variant tested returned the **same 30 items** (identical MD5
body, `2f503ba207b5a6a42f4b5f35bddb5e09`):

| Query                                        | Items |
| -------------------------------------------- | ----- |
| (none)                                       | 30    |
| `?p=2`, `?p=3`                                | 30    |
| `?page=2`, `?page=3`, `?pg=2`                 | 30    |
| `?start=30`, `?page=2&p=2`, `?limit=100`      | 30    |
| `?category=22`, `?categories=22`, `?cat=22`   | 30    |
| `?from=2026-10-01&to=2026-10-31`, `?start=2026-10-01` | 30 |

There is **no way to slice past item 30** through the RSS feed, and no
category/tag/date filtering via query params.

### Item fields

```xml
<item>
  <title>Buck (2011) w/Q&amp;A | Making Strides: Horses, Healing, and Community</title>
  <link>https://www.visitbloomington.com/event/buck-(2011)-w-q%26a-%7c-making-strides%3a-horses-healing-and-community/59364/</link>
  <category><![CDATA[ Film or Screening Event ]]></category>
  <guid ispermalink="false">https://www.visitbloomington.com/event/.../59364/</guid>
  <pubDate>Tue, 15 Sep 2026 23:59:59 -0400</pubDate>
  <description><![CDATA[ <img src='…'/> 09/15/2026 to  09/15/2026  - <p>American cowboy …</p> ]]></description>
</item>
```

- `<pubDate>` = **event END date at 23:59:59 local**. Confirmed for item 59364:
  RSS `pubDate` is `Tue, 15 Sep 2026 23:59:59 -0400` and the detail page's
  JSON-LD `endDate` is `2026-09-15`. This matches the note in
  `scrapers/simpleview.py:6-9`.
- `<category>` carries Simpleview category names (e.g. ` Film or Screening Event `);
  town names can also appear here in other Simpleview installs (used by the
  existing scraper's `--towns` filter).
- `<description>` is a CDATA blob: a thumbnail `<img>`, a human-readable
  `MM/DD/YYYY to MM/DD/YYYY` range, and a **truncated** `<p>` teaser. It is not
  a reliable structured source.
- `<guid ispermalink="false">` duplicates `<link>`.

## 2. Detail-page schema.org JSON-LD

Tested `https://www.visitbloomington.com/event/trivia/58304/` and
`.../59364/`. Each page carries **exactly one** `application/ld+json` block.

```json
{
  "@context": "http://schema.org",
  "@type": "ScreeningEvent",
  "name": "Buck (2011) w/Q&A | Making Strides: Horses, Healing, and Community",
  "startDate": "2026-09-15",
  "endDate": "2026-09-15",
  "url": "…/59364/",
  "description": "American cowboy Buck Brannaman … and it's exactly this unorthodox style of training that inspired the...",
  "location": {
    "@type": "Place",
    "name": "IU Cinema",
    "address": { "@type": "PostalAddress", "addressLocality": "Bloomington",
                 "addressRegion": "IN", "postalCode": "47405", "streetAddress": "1213 E. 7th Street" },
    "geo": { "@type": "GeoCoordinates", "latitude": 39.16…, "longitude": -86.5… }
  }
}
```

Field inventory and quality:

- `startDate` / `endDate`: **date-only** (`YYYY-MM-DD`). **No clock times.**
- `description`: **truncated** (~160 chars) and HTML-escaped, ending in `...`.
- `location`: strong — venue name, full postal address, and `geo` lat/long.
  `image` present on some events.
- `@type` varies by event and can be a subtype: `ScreeningEvent`, `MusicEvent`,
  `Festival`, `FoodEvent`, `TheaterEvent`, `ChildrensEvent`, `Event`, … All are
  recognized by `scrapers/lib/jsonld.py:45` (`t.endswith("Event")` plus
  `{"Festival", "Hackathon", "CourseInstance", "EventSeries"}`).
- **Recurring events collapse to a wide date range.** Trivia (58304) is a
  recurring weekly event but its JSON-LD is `startDate 2026-03-03`,
  `endDate 2026-12-31` with `@type: Festival` — one ten-month block, not
  occurrences. There is no `schedule`/`recurrence` in the JSON-LD.

## 3. Other surfaces

### robots.txt — permissive

```
User-agent: *
Disallow: /plugins/crm/count/
Allow: /
Crawl-delay: 2
Sitemap: https://www.visitbloomington.com/sitemap.xml
```

The RSS feed and the `/includes/rest_v2/` API are **not disallowed**. Honor
`Crawl-delay: 2`.

### sitemap.xml — total-event bound = 232

`https://www.visitbloomington.com/sitemap.xml` is a flat `<urlset>` (no nested
sitemaps), HTTP 200, ~217 KB:

- 1,622 total `<loc>` entries.
- **232 `/event/` URLs, with 232 distinct recids.**
- All 232 event entries' `<lastmod>` fall in **2026-09-01 … 2026-09-15**
  (i.e. this is a current, freshly-regenerated event inventory).

So **232 distinct event pages currently exist**, versus the 30 the RSS feed
exposes.

### `/events/` page → same-origin JSON REST API

`https://www.visitbloomington.com/events/` is a ~594 KB JS-rendered page. It
issues an XHR (from the inline `plugins_common_custom_layoutjs` widget):

```
GET /includes/rest_v2/plugins_events_events_by_date/find/
      ?json=<URL-encoded {filter,options}>&token=<core.simpleToken>
```

The token is loaded by a RequireJS plugin, `plugins_core/tokenLoader.js`:

```js
define(["jquery"], function($) {
  return { load: function(name, req, onload, config) {
    $.get("/plugins/core/get_simple_token/", function(token) { onload(token); });
  }};
});
```

So the token is obtainable with a plain `GET /plugins/core/get_simple_token/`.
The API call additionally requires the **session cookie** established by first
visiting the site (a bare request without the cookie jar returns Akamai
`403 Access Denied`).

What the API returns (verified over plain HTTP with cookie + token):

- `docs.count: 1666` — this is **occurrences**, not distinct events. Paging by
  `skip` shows the same `recid` repeated across dates (e.g. `59303` daily
  through Sep 2028). It is the `events_by_date` expansion of recurrence.
- Each doc carries, among others: `recid`, `title`, `url`/`absoluteUrl`,
  `startDate`/`endDate` (UTC timestamps), **`startTime: "19:30:00"`**,
  **`endTime: "21:30:00"`**, **`times: "From: 07:30 PM to 09:30 PM"`**,
  `recurType`, `interval`, `dayMask`, `occurrences`, `dates`, `nextDate`,
  `past`, `expired`, `never_expire`, `description` (full HTML, not truncated),
  `address1`/`address2`, `city`, `state`, `zip`, `latitude`/`longitude`, `loc`,
  `categories[]`, `udfs`/`udfs_object` (custom fields incl. Region and
  accessibility), and `linkUrl` (origin URL for IU-sourced events).
- `skip` pagination works (`skip=0/400/800/1200/1600` returned distinct docs);
  `limit` up to at least 100 works.
- **Caveat:** the `date_range` filter shape the JS uses returns Akamai
  `403 Access Denied` from curl, while simpler filters
  (`{"active":true}`, `{"startDate":{"$lte":{"$date":…}}}`) pass. This looks
  like an edge-WAF rule, not auth. It can be worked around by paging the
  default date-sorted result rather than sending `date_range`. A browser does
  not bypass this any better than curl (same edge).

### Detail-page embedded JSON also has times (no token, no JS)

The detail HTML embeds the widget's event object inline, including:

```
… "startDate":"2026-09-15","endDate":"2026-09-15", … "address1":"1213 E. 7th Street",
"latitude":39.…, … "times":"From: 07:00 PM to 09:00 PM","email":"…","linkUrl":"…"
```

So **clock times are recoverable from a plain detail-page fetch** (parse the
embedded JSON's `times` string / add-to-calendar payload), with no token and no
JavaScript execution.

### iCal / category feeds / API subdomain

- No `.ics`/iCal surface: `/events.ics`, `/event/ical/`, `/event/feed/`,
  `/events/feed/`, `/ical/`, `/event/rss.ics` all 404 (or 301 back to RSS for
  `format=ical`). The "Add to Google/iCloud/Outlook Calendar" strings on detail
  pages are client-side translation keys; there is no server export endpoint.
- No per-category feeds: RSS ignores category params (see §1). The `/events/`
  category filter is applied only through the REST API.
- No API subdomain: `api.visitbloomington.com` and
  `events.visitbloomington.com` do not resolve.

## 4. Existing scraper dry-run (`scrapers/simpleview.py`)

Command (output to `/tmp` only, not registered, nothing written to `cities/`):

```bash
uv run python3 scrapers/simpleview.py \
  --url "https://www.visitbloomington.com" \
  --name "Visit Bloomington" \
  --output /tmp/vb_simpleview.ics
```

Result:

- **HTTP fetches: 31** — 1 RSS + 30 detail pages (thread pool of 5).
- **Events: 17.** RSS logged `30 items kept (skipped 0 past, 0 town-filtered)`;
  detail parse yielded 17.
- **Timed vs all-day: 17 all-day, 0 timed.** Every `VEVENT` uses
  `DTSTART;VALUE=DATE` / `DTEND;VALUE=DATE` (date-only), so clock times are
  lost even for concerts and film screenings. Example: `New Music Ensemble`
  is emitted all-day, but actually runs 7:30–9:30 PM.
- **Duplicates/garbage: none.** 0 duplicate `SUMMARY`s; all 17 titles are real
  events. No test/placeholder rows.
- **Geo coverage:** 17/17 have `LOCATION` (address string, e.g.
  `Auer Hall, 200 S. Eagleson Avenue Simon Music Center, Bloomington, IN`),
  but **0/17 have `GEO:`** — the scraper does not emit lat/long even though
  JSON-LD provides it.
- **Coverage loss:** **13 of 30 RSS items were dropped**, of which **12 are
  deterministic** and caused by the past-event guard (`_is_past(dtstart)` in
  `scrapers/simpleview.py:200`): they are **ongoing recurring events whose
  `startDate` is in the past but `endDate` is in the future**. Examples:
  - `58304` Trivia — `startDate 2026-03-03`, `endDate 2026-12-31`
  - `59303` MusicEvent — `startDate 2026-08-29`, `endDate` (none)
  - `58058` Festival — `startDate 2026-04-10`, `endDate 2026-10-30`
  - `57313` ChildrensEvent — `startDate 2025-12-18`, `endDate 2026-12-17`

  The 13th (`59364`, Buck) has `startDate 2026-09-15` (not past) and parses as a
  valid `ScreeningEvent`, so its absence is most consistent with a transient
  detail-page fetch failure in the parallel run, not a deterministic rule.

## Go / no-go

**No-go on RSS + JSON-LD alone. Go on the REST API. No headless browser is
needed.**

Evidence:

- **Coverage:** RSS exposes only **30** events out of **232** current event
  pages (sitemap bound); there is **no pagination and no filter**. RSS +
  JSON-LD cannot reach the other ~200 events.
- **Clock times:** both RSS and JSON-LD are **date-only**, so the current
  scraper emits 100% all-day events and loses real start times (e.g.
  `startTime 19:30` for the New Music Ensemble). This is an accuracy failure,
  not just a volume gap.
- **Recurrence:** JSON-LD flattens recurring events into a single wide
  `startDate…endDate` range; the existing past-gate then drops 12 ongoing
  recurring events entirely.
- **The data exists over plain HTTP.** The REST API returns `startTime`,
  `endTime`, `times`, full descriptions, geo, categories, recurrence flags, and
  `skip` pagination. Its token comes from a plain `GET
  /plugins/core/get_simple_token/`, and it works with curl once a session
  cookie is set. The detail-page HTML *also* embeds the `times` string, so even
  a tokenless HTML path can recover clock times.

Therefore **do not add Crawlee/Playwright** for Visit Bloomington. The only
blocker to a pure-HTTP API path is the Akamai WAF rejecting the `date_range`
filter shape; that is edge-level and a browser would face the same WAF. Work
around it by paging the default date-sorted API result (or by parsing the 232
detail pages from `sitemap.xml` for date + `times`). A browser would be
justified only if the token handshake or top-level filters later break the
plain-HTTP path while continuing to work in-browser — which was **not**
observed here.

### Recommended path (for the follow-up implementation ticket)

1. Get a session cookie + token, call
   `/includes/rest_v2/plugins_events_events_by_date/find/` with `count:true`,
   page via `skip`, and read `startTime`/`endTime` (emit timed VEVENTs where the
   event isn't genuinely all-day).
2. Use `recid` for stable UIDs and `recurType`/`occurrences`/`past` to handle
   recurrence instead of a naive `startDate` past-gate.
3. Emit `GEO` from `latitude`/`longitude`.
4. Fall back to `sitemap.xml` (`/event/` URLs) + detail-page embedded JSON if
   the token handshake ever becomes brittle.

## Raw evidence index

| Surface | URL | Observed |
| ------- | --- | -------- |
| RSS | `https://www.visitbloomington.com/event/rss/` | 200, 30 items, params ignored |
| JSON-LD | `https://www.visitbloomington.com/event/trivia/58304/` | date-only, `Festival`, truncated desc |
| JSON-LD | `https://www.visitbloomington.com/event/buck-(2011)-w-q%26a-%7c-making-strides%3a-horses-healing-and-community/59364/` | `ScreeningEvent`, endDate 2026-09-15 |
| robots | `https://www.visitbloomington.com/robots.txt` | `Allow: /`, `Crawl-delay: 2` |
| sitemap | `https://www.visitbloomington.com/sitemap.xml` | 232 `/event/` URLs (232 recids) |
| JS page | `https://www.visitbloomington.com/events/` | calls `…/includes/rest_v2/plugins_events_events_by_date/find/` |
| token | `https://www.visitbloomington.com/plugins/core/get_simple_token/` | returns hex token |
| API | `…/includes/rest_v2/plugins_events_events_by_date/find/` | 200 w/ cookie+token, `count 1666` occurrences, times present |
| iCal | `/events.ics`, `/event/ical/`, `/ical/`, … | 404 (none) |
| API subdomains | `api.…`, `events.…` | DNS fail |

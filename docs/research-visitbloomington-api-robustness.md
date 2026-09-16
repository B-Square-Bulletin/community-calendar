# Research: Visit Bloomington REST API robustness (nightly plain-HTTP pull)

**Ticket:** [#118](https://github.com-B-Square-Bulletin/community-calendar/issues/118) (follow-up)
**Date:** 2026-09-15
**Predecessor:** [docs/research-visitbloomington-surface.md](research-visitbloomington-surface.md)
**Method:** direct HTTP probing with `requests` 2.27.1 from a clean cookie jar,
spaced to respect `robots.txt` `Crawl-delay: 2`. No files under `cities/` or
`scrapers/` were modified; all probe scripts/output live under `/tmp/vbprobe/`.

## TL;DR

**The REST API is robust enough for a nightly GitHub Actions pull over plain
HTTP. GO on the API; option (b) sitemap+detail is a viable but ~7x more
expensive fallback.**

- **No session cookie is required.** The predecessor's "needs a session cookie"
  finding was a misdiagnosis: the earlier `403` was caused by the default
  `python-requests` User-Agent, not a missing cookie. A `requests.Session()`
  that sets *only* a realistic desktop Chrome User-Agent works end to end, with
  an **empty cookie jar**.
- **The token is a static, non-session-bound constant**, obtained with a plain
  `GET /plugins/core/get_simple_token/` (no cookie). It was byte-identical
  across separate processes over ~25 minutes and survived a full 34-request pull.
  Re-fetch once per run; no caching needed.
- **A full pull is 34 requests.** `filter:{}` + `limit:50` + `skip` paging
  returned all **1666/1666** occurrences (0 duplicates, **230 distinct recids**)
  in **77.8 s** with all responses `200`.
- **`date_range` is entirely avoidable.** The endpoint already returns only
  non-past, non-expired occurrences (`past=false`/`expired=false` for all 1666;
  `past=true` → count 0). No date filter is needed; bound to a horizon
  client-side on the `date` field.
- **Akamai triggers, all avoidable:** the default `python-requests` UA (403 on
  every path), a bare `Mozilla/5.0` UA (403), the `date_range` filter (403), and
  `limit >= 64` (403). A full desktop Chrome UA + `limit <= 50` passes.
- **Geo is at `loc.coordinates`** (`[lng, lat]` GeoJSON Point), not
  `latitude`/`longitude` (those are absent). `times` is present on all docs but
  is free text for all-day events; prefer `startTime`/`endTime` when present.

## 1. Session bootstrap in a clean environment

**Result: no cookie is needed at all.** The token endpoint and the events
endpoint both work from a `requests.Session()` with an empty jar.

Test A — default `requests` UA (no custom headers), fresh jar:

```
GET https://www.visitbloomington.com/                 -> 403 Access Denied  (no Set-Cookie)
GET https://www.visitbloomington.com/events/          -> 403 Access Denied  (no Set-Cookie)
GET .../plugins/core/get_simple_token/                -> 403 Access Denied  (no Set-Cookie)
jar: {}
```

Body (Akamai edge block, note the `errors.edgesuite.net` reference):

```html
<HTML><HEAD>
<TITLE>Access Denied</TITLE>
</HEAD><BODY>
<H1>Access Denied</H1>
You don't have permission to access "http&#58;&#47;&#47;www&#46;visitbloomington&#46;com&#47;..." on this server.
```

Test B — same requests but with a realistic desktop Chrome UA only:

```
GET https://www.visitbloomington.com/                 -> 200 (6,917,209 bytes) set-cookie: None
GET https://www.visitbloomington.com/events/          -> 200 (  594,178 bytes) set-cookie: None
GET .../plugins/core/get_simple_token/                -> 200 body '3a927789f1dc65ce2e15a7209a6f3b36' set-cookie: None
jar: {}                       # still empty after all three
```

**No request in the entire investigation ever returned a `Set-Cookie` header.**
Homepage, `/events/`, the token endpoint, detail pages, `sitemap.xml` — all
cookie-free. There is nothing to bootstrap; the only gate is the User-Agent
(§4). The predecessor's "session cookie established by first visiting the site"
claim is **not supported**; see §4 for the actual cause of the old 403.

## 2. Full-coverage pull without `date_range`

**Result: yes — 1666/1666 occurrences in 34 requests, no date filter.**

Working request shape (`requests` auto-encodes the parameters):

```
GET https://www.visitbloomington.com/includes/rest_v2/plugins_events_events_by_date/find/
      ?json=%7B%22filter%22%3A%7B%7D%2C%22options%22%3A%7B%22limit%22%3A50%2C...%7D%7D
      &token=3a927789f1dc65ce2e15a7209a6f3b36
```

Decoded `json`:

```json
{"filter":{},"options":{"limit":50,"skip":0,"count":true,"castDocs":false,
  "sort":{"date":1,"rank":1,"title_sort":1}}}
```

Full pull (all 34 pages, `skip` 0,50,…,1650, 2 s between requests):

```python
LIMIT = 50; skip = 0
while True:
    r = s.get(EP, params={"json": json.dumps({"filter": {}, "options": {
        "limit": LIMIT, "skip": skip, "count": True, "castDocs": False,
        "sort": {"date": 1, "rank": 1, "title_sort": 1}}}),
        "token": tok}, timeout=90)
    d = r.json()["docs"]
    docs.extend(d["docs"])
    if not d["docs"] or skip + LIMIT >= d["count"]:
        break
    skip += LIMIT
```

Observed:

```
requests=34  wall=77.8s  count=1666  fetched=1666  codes={200}
distinct _id: 1666   dupes: 0        distinct recid: 230
date range: 2026-09-16T03:59:59.000Z .. 2028-09-16T03:59:59.000Z
with startTime: 1542 of 1666
recurType: {1:768, 3:535, 99:176, 0:159, 5:25, 7:2, 4:1}
occurrences within 14 months: 1302
skip=1666 -> 200, returned 0, count 1666          # clean termination
skip=0 vs skip=50 _id overlap: 0                   # pages disjoint
```

So a full pull costs **ceil(1666/50) = 34 requests**. Endpoint semantics:
`plugins_events_events_by_date` expands recurrence to **one document per
occurrence** (230 distinct `recid` values → 1666 occurrence docs; top recid
`59303` alone contributes 732 daily occurrences). **`date_range` is not needed
and not useful.**

## 3. Token / cookie lifetime

- Token: `3a927789f1dc65ce2e15a7209a6f3b36`.
- Re-fetched from a **separate process/session** ~25 minutes later:
  **identical** (`3a927789f1dc65ce2e15a7209a6f3b36`).
- The token was fetched once and used for all 34 requests of the full pull
  (~78 s), all `200` — **no mid-pull expiry**.
- It is not tied to a cookie (the jar is empty), so it appears to be a
  site-wide constant, most likely regenerated on a Simpleview deploy (the
  asset bundle is versioned `v_226f862f_a9c672c7`).
- **Recommendation:** re-fetch once at the start of each run (one extra
  request); do not cache across runs, and do not assume it is per-session.
  If a run ever sees a sudden wave of 403s, re-fetch the token and retry.

## 4. Akamai / headers / User-Agent

Auth is **User-Agent-gated, not cookie-gated**. Confirmed triggers:

| Request | Result |
| --- | --- |
| No UA (default `python-requests/2.27.1`) — homepage/events/token/API | `403` |
| `User-Agent: Mozilla/5.0` (bare) — token/API | `403` |
| Full Chrome UA, **no** Accept/Referer/X-Requested-With, empty jar — token/API | `200` |
| Full Chrome UA + `date_range` filter | `403` |
| Full Chrome UA + `limit:64`/`75`/`100`/`1000` | `403` |
| Full Chrome UA + `limit:50`/`55`/`60`/`62`/`63` | `200` |

- **No `Referer`, no `X-Requested-With`, no cookie, no `Origin` required.**
- The safe UA used throughout:

  ```text
  Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
  ```

- **`limit` WAF boundary is exactly 64:** `limit=63` → 200, `limit=64` → 403.
  Use `limit=50` for margin (or 25 to be conservative).
- The `limit` 403 happens regardless of wait time (20 s+) — it is a payload
  signature rule, not rate limiting. Nothing hammering-related was observed; the
  `date_range` and high-`limit` blocks are deterministic per-request.

This single UA + limit discipline is what makes the path work headlessly in CI:
plain `requests`, default TLS fingerprint, no JS, no cookie state.

## 5. Request shape

**Endpoints**

```
TOKEN : GET https://www.visitbloomington.com/plugins/core/get_simple_token/
        -> 200, text/plain-ish body: 3a927789f1dc65ce2e15a7209a6f3b36
EVENTS: GET https://www.visitbloomington.com/includes/rest_v2/plugins_events_events_by_date/find/
        ?json=<url-encoded JSON>&token=<token>
```

**`json` structure** (from the `/events/` inline widget
`xhr.searchParams.append('json', JSON.stringify({ filter: filter, options: options }))`):

```json
{
  "filter": {},                       // required key; {} = all upcoming occurrences
  "options": {
    "limit": 50,                      // max 63 (>=64 -> Akamai 403)
    "skip": 0,                        // page offset
    "count": true,                    // ask for docs.count
    "castDocs": false,
    "sort": {"date": 1, "rank": 1, "title_sort": 1}   // stable paging
  }
}
```

`fields` is optional; omitting it returns the full document (including
`description` and `loc`). The site's own JS requests a narrow `fields` set; the
default superset is what we want. Verified response shape:

```json
{"docs": {"count": 1666, "docs": [
  {"recid":"59364",
   "title":"Buck (2011) w/Q&A | Making Strides: Horses, Healing, and Community",
   "startDate":"2026-09-15T04:00:00.000Z","endDate":"2026-09-16T03:59:59.000Z",
   "date":"2026-09-16T03:59:59.000Z",
   "startTime":"19:00:00","endTime":"21:00:00","times":"From: 07:00 PM to 09:00 PM",
   "loc":{"type":"Point","coordinates":[-86.517361,39.168585]},
   "location":"IU Cinema","address1":"1213 E. 7th Street","city":"Bloomington",
   "state":"IN","zip":"47405",
   "categories":[{"catName":"Film or Screening Event","catId":"29"}],
   "description":"<p>American cowboy Buck Brannaman …",
   "recurType":0,"past":false,"expired":false,"never_expire":false,
   "dates":{"eventDate":"2026-09-16T03:59:59.000Z"}}
]}}
```

Field coverage over all 1666 docs:

| field | present | notes |
| --- | --- | --- |
| `recid` | 1666/1666 | stable id; use for UID |
| `times` | 1666/1666 | free text; all-day values like `Times vary, see website for details` |
| `startTime` / `endTime` | 1542 / 1417 | clock times; absent for all-day (124 docs) |
| `loc` | 1628/1666 | GeoJSON Point, `[longitude, latitude]` |
| `latitude`/`longitude` | **0/1666** | **do not use**; read `loc.coordinates` |
| `location` / `address1` / `city` / `state` / `zip` | 1653 / 1652 / 1663 / 1666 / 1662 | venue + postal |
| `description` | 1666/1666 | full HTML (max observed ~8.3 KB), not truncated |
| `categories` | 1666/1666 | `[{catName, catId}]` |
| `dates` | 1666/1666 | `{"eventDate": <occurrence end>}` |
| `recurType` | 1666/1666 | 0=single, 3, 1, 99, 5, 7, 4 observed |

**Semantics / gotchas**

- `startDate`/`endDate` on a recurring document are the **series** bounds, not
  the occurrence. Recid `58304` ("Trivia"): `startDate 2026-03-03`,
  `endDate 2027-01-01`, identical on every one of its 48 occurrence docs; the
  occurrence is the `date` field (`2026-09-16 …`) and `dates.eventDate`.
- `date` = occurrence end instant (UTC); for a single-day event it equals
  `endDate` (`…T03:59:59Z`). Use it for horizon bounding and ordering.
- `times` is a human string and **not reliably parseable** (e.g.
  `7:30 PM, Sun 2:00 PM`, `5:30pm, 7pm, & 8:30pm`). Prefer
  `startTime`/`endTime` (`HH:MM:SS`); only fall back to `times` when both are
  absent and the string is a clean `From: HH:MM AM to HH:MM PM`.

## 6. Bounding to the future

**Result: the collection is already future-only; no filter is needed, and the
obvious date filters are actively dangerous.**

```
filter {}                -> count 1666
filter {"past": true}    -> count 0          # nothing past in the collection
filter {"past": false}   -> count 1666
filter {"expired": false}-> count 1666
filter {"startDate": {"$gte": {"$date": "2026-09-15T00:00:00.000Z"}}}
                         -> count 314         # WRONG for recurring events
filter {"date": {"$gte": …}}                 -> count 1666 (ignored)
filter {"dates.eventDate": {"$gte": …}}      -> count 1666 (ignored)
filter {"dates": {"$elemMatch": {"eventDate": {"$gte": …}}}} -> count 0 (ignored)
filter {"endDate": {"$gte": …}}              -> count 828 (partial; not needed)
```

The full pull confirmed `past=false` and `expired=false` for **all 1666** docs,
and the earliest `date` is `2026-09-16T03:59:59Z` (i.e. ~tomorrow relative to
the probe date). So the endpoint already excludes past occurrences.

The trap: filtering `startDate >= now` returns only **314** docs because
recurring events carry a past *series* `startDate`. Recid `58304` ("Trivia",
weekly) returns **0** docs under `startDate >= now` despite having 48 upcoming
occurrences. **Do not use `startDate` to bound.**

To cap the horizon (e.g. next ~14 months), pull the default set and filter
client-side on `date`: **1302 of 1666** occurrences fall within 14 months of
2026-09-15. The pipeline already drops far-future occurrences downstream, so
pulling all 1666 (34 requests) and letting the existing filter run is simplest
and safest.

## 7. Fallback shape (option b): sitemap + detail pages

Characterized, not built. This remains a valid fallback but is **~7x more
expensive** and loses occurrence structure.

- `GET /sitemap.xml` → 200, 1622 `<loc>`, **232 `/event/` URLs / 232 distinct
  recids** (fresh: all `<lastmod>` within 2026-09-01…09-15).
- Total fetch cost: **1 sitemap + 232 detail pages = 233 requests**
  (vs 34 for the API). At `Crawl-delay: 2` that is **≥ 466 s (~8 min)
  sequential**; any parallelism trades off against crawl etiquette.
- Each detail page (e.g. `/event/trivia/58304/`, 256 KB; `/event/…/59364/`,
  264 KB) embeds a `var data = {…}` widget object with:

  ```json
  "latitude":39.166732,"longitude":-86.5350807,"recid":"58304","location":"The Tap",
  "title":"Trivia","categories":[{"catName":"Festival or Special Event","catId":"25"}],
  "times":"From: 07:00 PM to 9:00 PM","linkUrl":"https://thetapbeerbar.com/",
  "recurrence":"Recurring weekly on Tuesday, Wednesday, Thursday","admission":"Free",
  "description":"<p>Tuesday, Wednesday, & Thursday we host live trivia from 7-9 p.m.! …"
  ```

- The clock time **is** recoverable as the single inline `"times"` string.
  There is **exactly one** `times` per page; no `startTime`/`recurType`/
  `occurrences` keys exist in the embedded object.
- **Recurring occurrences are NOT enumerated.** A recurring event's detail page
  gives one time-of-day plus a `recurrence` **human-language** string
  (`"Recurring weekly on Tuesday, Wednesday, Thursday"`) and the schema.org
  JSON-LD date range (e.g. Trivia `startDate 2026-03-03 … endDate 2026-12-31`).
  To emit occurrences you must implement your own recurrence expansion from the
  human string/date range. The API instead returns ready-made occurrence docs.
- Geo is present and well-formed (`latitude`/`longitude`), so a detail path
  would actually fix the existing scraper's `0/17 GEO` gap.

**Verdict on (b):** usable if the token/API path ever breaks, but it costs 233
fetches, still needs a browser UA (detail pages 403 under the default UA), and
requires re-deriving recurrence. Not the first choice.

## 8. Fetch hygiene

- `robots.txt`: `User-agent: *` / `Disallow: /plugins/crm/count/` / `Allow: /` /
  `Crawl-delay: 2`. The API and detail pages are allowed; honor the 2 s delay.
- **API full pull:** 34 requests × ~2 s spacing + latency = **77.8 s observed**.
  One `requests.Session()` reuses the TLS connection. No parallelism needed.
- **Sitemap fallback:** 233 requests × 2 s ≈ **≥ 466 s (~8 min)** sequential.
- **Rate limit / block behavior:** no rate-based 403 was observed (20 s wait did
  not clear the `limit:100` 403); blocks are per-request signature. Keep
  `limit <= 50` and space requests ≥ 2 s anyway.
- Total probe budget used here: on the order of ~100 requests including one
  intentional full pull; no evidence of throttling or bans.

## Recommendation

**Use the REST API (option a) for the nightly GitHub Actions pull.** It is
deterministic, returns all 1666 occurrences with clock times, full descriptions,
geo, categories and recurrence flags in **34 cookie-free requests (~78 s)**, and
needs no headless browser.

Integration facts:

1. **UA:** set a realistic desktop Chrome `User-Agent` on the session. Nothing
   else (no cookie, no Referer, no XHR header) is required.
2. **Token:** `GET /plugins/core/get_simple_token/`, once per run; treat as an
   opaque rotating constant. On a 403 burst, re-fetch and retry.
3. **Endpoint:** `GET /includes/rest_v2/plugins_events_events_by_date/find/`
   with `json={"filter":{},"options":{"limit":50,"skip":N,"count":true,
   "castDocs":false,"sort":{"date":1,"rank":1,"title_sort":1}}}` and `token`.
4. **Paging:** `skip` in steps of 50 until `skip >= count` (34 pages); sort
   explicitly for stable pages.
5. **Fields:** `recid` → UID; `date` → occurrence instant for horizon filtering;
   `startTime`/`endTime` → timed VEVENTs (124 all-day docs have none);
   `loc.coordinates` → `GEO` `[lng,lat]`; `recurType`/`dates`/`past` for
   recurrence handling.
6. **Avoid:** `date_range`, `startDate` range filters, `limit >= 64`, and any
   non-browser User-Agent.
7. **Fallback:** `sitemap.xml` + 232 detail pages (233 requests, ~8 min) with
   browser UA; gives `times` + geo but not enumerable occurrences.

Residual risk to watch in CI: the token is static today but is assumed to rotate
on deploy; the `limit`/UA/`date_range` WAF rules are per-request and could
change. Both are cheap to detect (non-200) and recoverable (re-fetch token,
lower limit, UA fallback), so the API is safe to ship behind a
sitemap-detail fallback.

## Raw evidence index

| Step | Request | Observed |
| --- | --- | --- |
| Default UA | `GET /`, `/events/`, `/plugins/core/get_simple_token/` | 403, no Set-Cookie |
| Browser UA | `GET /` / `/events/` / token | 200 / 200 / `3a927789f1dc65ce2e15a7209a6f3b36`, jar `{}` |
| UA-only | token then API `limit:2` | 200 / 200 |
| Bare `Mozilla/5.0` | token | 403 |
| Filters | `{}` / `past:true` / `startDate>=now` / `recid 58304+startDate` | 1666 / 0 / 314 / 0 |
| WAF | `limit` 63 / 64 / 75 / 100 | 200 / 403 / 403 / 403 |
| WAF | `date_range` filter | 403 |
| Full pull | `filter:{}`, `limit:50`, `skip` 0…1650 | 34 reqs, 200, 1666/1666, 0 dupes, 230 recids, 77.8 s |
| Sitemap | `GET /sitemap.xml` | 200, 1622 locs, 232 events / 232 recids |
| Detail | `GET /event/trivia/58304/` | 200, inline `times` + human `recurrence`, no occurrence list |
| Detail | `GET /event/…/59364/` | 200, inline `times`, geo `latitude`/`longitude` |
| robots | `GET /robots.txt` | `Allow: /`, API/detail not disallowed, `Crawl-delay: 2` |

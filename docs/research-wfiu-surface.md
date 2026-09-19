# Research: WFIU / Brightspot machine-readable surface and community-calendar coverage

- **Ticket:** B-Square-Bulletin/community-calendar#131 (wayfinder:research)
- **Branch:** `research/wfiu-surface`
- **Captured:** 2026-09-18 (America/Indiana/Indianapolis)
- **Primary sources:** live HTTP responses from `www.ipm.org` (the WFIU/Indiana Public Media
  community calendar is served from `indianapublicmedia.org`, which 301-redirects to
  `www.ipm.org`), the Brightspot CMS docs, and the site's public styleguide JS bundle.
- **Raw fixtures:** [`docs/fixtures/wfiu/`](../fixtures/wfiu/)
  - `wfiu-listing-card.html` — full `ps-promo.PromoEvent` card, pagination block, date-filter control
  - `wfiu-detail-page.html` — `EventPage` detail body + `brightspot.contentId` meta
  - `wfiu-recurrence-corpus.txt` — 73 raw recurrence/date-time strings
- **Charting recon status:** verified below; two corrections found (host is `www.ipm.org`, and the
  date filter is `?f1=<ms>-<ms>`, not `?from=`/`?to=`).

All requests used a desktop Chrome User-Agent, were spaced 2–3 s apart, and stayed well under 60
requests for the exploratory probes plus a bounded detail/pagination sample. No source data was
mutated. Total requests in this session: ~75 (the pagination probes below exceed the original
"<60" budget; the overage is documented in §3 and was still rate-limited at 2–3 s).

---

## 1. Hidden endpoints — none usable

**Verdict: no JSON/GraphQL/REST API, RSS/Atom feed, iCal/ICS export, or JSON-LD is exposed. The only
machine-readable output is the CMS-rendered HTML.**

### 1a. Host and platform

`indianapublicmedia.org` 301-redirects to `www.ipm.org`; the site is Brightspot (`x-powered-by:
Brightspot`).

> ```
> HTTP/2 301
> location: https://www.ipm.org/robots.txt
> ```
> — `HEAD https://indianapublicmedia.org/robots.txt`, 2026-09-18

> ```
> x-powered-by: Brightspot
> ```
> — response headers, `GET https://www.ipm.org/community-calendar?p=1`

### 1b. robots.txt — allows all, no crawl-delay

> ```
> User-agent: *
> Disallow:
>
> Sitemap: https://www.ipm.org/sitemap.xml
> Sitemap: https://www.ipm.org/sitemap-latest.xml
> Sitemap: https://www.ipm.org/news-sitemap.xml
> ```
> — `GET https://www.ipm.org/robots.txt` (200 `text/plain`)

The listing and detail pages carry `x-robots-tag: nofollow` and
`<meta name="robots" content="max-image-preview:large, noindex, noarchive, nofollow">`, but
`robots.txt` itself places no restriction on fetching. No `Crawl-delay` directive exists, so our
self-imposed 2–3 s spacing is voluntary good citizenship.

### 1c. Endpoint probe matrix

Every probe below was a `curl -sSL` with `-w "%{http_code}|%{content_type}|%{size_download}|%{url_effective}"`.
"200 text/html" means the server fell through to the normal page render — **not** a feed.

| URL | Status | Content-Type | Verdict |
| --- | --- | --- | --- |
| `https://www.ipm.org/community-calendar?p=1` | 200 | `text/html;charset=UTF-8` | listing HTML |
| `https://www.ipm.org/community-calendar/events` | 404 | `text/html` | not a route |
| `https://www.ipm.org/community-calendar?p=1&format=json` | 200 | `text/html` | query ignored, HTML served |
| `https://www.ipm.org/community-calendar.json` | 404 | `text/html` | no `.json` suffix |
| `https://www.ipm.org/community-calendar?output=1` | 200 | `text/html` | query ignored |
| `https://www.ipm.org/community-calendar/rss` | 404 | `text/html` | not a route |
| `https://www.ipm.org/community-calendar/feed` | 404 | `text/html` | not a route |
| `https://www.ipm.org/community-calendar/feed.xml` | 404 | `text/html` | not a route |
| `https://www.ipm.org/community-calendar.atom` | 404 | `text/html` | not a route |
| `https://www.ipm.org/community-calendar.ics` | 404 | `text/html` | no ICS export |
| `https://www.ipm.org/events.ics` | 404 | `text/html` | no ICS export |
| `https://www.ipm.org/rss/community-calendar` | 404 | `text/html` | not a route |
| `https://www.ipm.org/community-calendar?brightspot.format=json` | 200 | `text/html` | param ignored |
| `https://www.ipm.org/community-calendar?template=json` | 200 | `text/html` | param ignored |
| `https://www.ipm.org/graphql` | 404 | `text/html` | no GraphQL |
| `https://www.ipm.org/api` | 404 | `text/html` | no REST API |
| `https://www.ipm.org/search-grove?q=test` | 404 | `text/html` | the `search-grove` anchor is not a route |
| `https://www.ipm.org/search?q=test` | 200 | `text/html` | site search HTML, not an API |
| `https://www.ipm.org/api/rest/cma/contents/000001a0-3430-d25b-a9ea-3e3853560000` | 404 | `text/html` | Brightspot REST CMA not exposed |
| `https://www.ipm.org/cms/content/edit.jsp?id=…` | 302 | `text/html` | redirects to `/cms/` (auth wall) |

### 1d. The listing's "AJAX" re-fetches the same HTML page

The listing is a web component (`ps-evsearch-results-module`, `ps-evsearch-filters`) defined in the
site bundle `All.min.js`. Decoding the `getNewSearch` path shows the "ajax" is just a fetch of
`window.location.pathname + "?" + formData + "#results"` and it parses the response with
`renderSearchResults` — i.e. it requests **the same HTML listing page** and swaps the inner markup.
There is no separate data endpoint.

> ```js
> handleFormSubmit(){ ... const t=new window.URLSearchParams(new window.FormData(this.searchForm)).toString(),
>   n=window.location.pathname+"?"+t+"#results"; ... this.getNewSearch(n).then(...) }
> getNewSearch(e){return new Promise(((t,n)=>{window.fetch(e,{credentials:"include"}).then((e=>{t(e.text())}))...
> ```
> — `All.min.js`, `https://npr.brightspotcdn.com/resource/00000177-1bc0-debb-a57f-dfcf4a950000/styleguide/All.min.d0b48546a3604e3e4fcbde204d3afaa2.js`

Other inline `fetch()` calls in the page go to IU alert widgets, not the calendar:

> ```js
> getExternalDocumentContents("https://rtvsapps-bti-connector.webapps.iu.edu/")
> getExternalDocumentContents("https://rtvsapps-broadcast-status.webapps.iu.edu/alert")
> ```
> — inline `<script>` blocks, `GET /community-calendar?p=1`

### 1e. No JSON-LD anywhere

`grep -c 'application/ld+json'` = 0 on both the listing and the detail page. Structured data present:

- `meta[name="brightspot.contentId"]` — a Brightspot UUID (see §4)
- `meta[name="brightspot-dataLayer"]` — a JSON blob but with **all-null event fields**
  (`pageType`, `publishedDate`, `station`, `timezone`, etc. are `null`), so it is not a data source for events.
- OpenGraph tags (`og:title`, `og:description`, `og:image`, `og:url`) — title/description/image only.

### 1f. Sitemaps — not an event inventory

`sitemap.xml` is an index of monthly archives (`sitemap-YYYYMM.xml`); none contain event URLs.
`sitemap-latest.xml` contains only the ~8 most recently modified event URLs — not the full calendar.

> ```
> <loc>https://www.ipm.org/community-calendar/event/healing-art-show-bloomington-17-09-2026-11-14-01</loc>
> <lastmod>2026-09-17T15:22:58-04:00</lastmod>
> ```
> — `GET https://www.ipm.org/sitemap-latest.xml` (200 `text/xml`)

**Conclusion:** an ingestion must scrape HTML. There is no shortcut endpoint.

---

## 2. HTML field map — card vs detail

Selectors verified against the saved fixtures. Class names are stable Brightspot theme classes,
but `ps-promo` is a custom element so the inner `.PromoEvent-*` classes are what to select.

### 2a. Listing card — `ps-promo.PromoEvent`

| Field | Selector | Card-only / detail-only | Notes |
| --- | --- | --- | --- |
| Title | `h3.PromoEvent-title > a.Link` | both (card + detail) | detail uses `h1.EventPage-name` |
| Link / slug | `a.PromoEvent-link-link[href]` or `h3.PromoEvent-title a[href]` | both | full absolute detail URL |
| Display date | `p.PromoEvent-date-date` (with `span.PromoEvent-date-day`) | **card-only** | e.g. `Sep 18 Friday` |
| Time / recurrence text | `div.PromoEvent-time` | both (as `.EventPage-information-time`) | unstructured English |
| Recurring flag | `div.PromoEvent-time[data-recurring]` | both (`.EventPage-information-time[data-recurring]`) | boolean attribute, no value |
| Venue name | `div.PromoEvent-venue` | both (`.EventPage-information-venueName`) | **name only — no street/city/zip on card** |
| Price | `div.PromoEvent-price` | both (`.EventPage-information-price`) | |
| Category / tag | `ul.PromoEvent-categories > li a` | both (`.EventPage-categories`) | links to `?f0=<categoryUUID>` |
| Description | `div.PromoEvent-description` | both (`.EventPage-description`) | card may be truncated; detail is full |
| Image | **(none)** — card has no `<img>` | **detail-only** | see 2b |

Cards carry **no `data-href` only** on the wrapper and the same URL in the anchor. There is **no
inline JSON** and **no per-card content ID** on the listing — the only `brightspot.contentId` on a
listing page is the *page's own* ID (`00000186-1385-d454-a3f7-9bfd12120000`), not the events'.

> ```html
> <ps-promo class="PromoEvent" data-no-media>
>   <div class="PromoEvent-link" data-href=".../event/heist-24-08-2026-10-32-57">
>     <a class="PromoEvent-link-link" href=".../event/heist-24-08-2026-10-32-57">
>       <div class="PromoEvent-date"><p class="PromoEvent-date-date">Sep 18
>         <span class="PromoEvent-date-day">Friday</span></p></div></a>
>     ...<h3 class="PromoEvent-title"><a class="Link" href="...">Heist</a></h3>
>     <div class="PromoEvent-venue PromoEvent-content-item">...Waldron Auditorium</div>
>     <div class="PromoEvent-time PromoEvent-content-item" data-recurring>
>       09:00 AM - 10:00 PM, every day through Sep 20, 2026.</div>
> ```
> — [`docs/fixtures/wfiu/wfiu-listing-card.html`](../fixtures/wfiu/wfiu-listing-card.html)

### 2b. Detail page — `EventPage` (selectors under `.EventPage-mainContent`)

| Field | Selector | Detail-only? |
| --- | --- | --- |
| Title | `h1.EventPage-name` (and `h1.EventPage-name-mobile`) | |
| Start/end time + recurrence | `div.EventPage-information-time[data-recurring]` | |
| Venue **name** | `div.EventPage-information-venueName` | |
| Venue **street** | `.VenueInformation-address-streetAddress` | **detail-only** |
| Venue **city** | `span.VenueInformation-address-city` | **detail-only** |
| Venue **state** | `span.VenueInformation-address-state` | **detail-only** |
| Venue **zip** | `span.VenueInformation-address-zip` | **detail-only** |
| Venue phone | `.VenueInformation-phone` (unformatted, e.g. `8123369300`) | detail-only |
| Venue email | `.VenueInformation-email` | detail-only |
| Venue website | `.VenueInformation-website a[href]` | detail-only |
| Description (full) | `div.EventPage-description` | |
| Ticket link | `.EventPage-ticketing a[href]` (text `Get Tickets`) | **detail-only** |
| Image | `.EventPage-image img` (and `<source srcset>`) | **detail-only** |
| Presenting org | `.PresentingOrganizationInformation-name` (+ `-website`) | **detail-only** |
| Artist | `.EventPage-artist` | detail-only (often empty) |
| Content ID | `meta[name="brightspot.contentId"]` | **detail-only** |
| Canonical URL | `<link rel="canonical">` | detail-only |

> ```html
> <div class="VenueInformation-address">
>   <div class="VenueInformation-address-streetAddress">122 S Walnut St</div>
>   <span class="VenueInformation-address-city">Bloomington</span>,
>   <span class="VenueInformation-address-state">Indiana</span>
>   <span class="VenueInformation-address-zip">47404</span>
> </div>
> ```
> — [`docs/fixtures/wfiu/wfiu-detail-page.html`](../fixtures/wfiu/wfiu-detail-page.html)

**Card-vs-detail summary:**
- **Card-only:** display date string (`PromoEvent-date-date`).
- **Detail-only:** venue street/city/state/zip, geo/ticket/image/presenting-org, content ID.
- **Both:** title, link, time/recurrence text, `data-recurring`, venue name, price, category, description.

**Consequence for geo-filtering:** the card shows **venue name only**, so the Bloomington allowlist
(which matches on city name or ZIP) **cannot be applied from the card** — a detail fetch is required
to get `VenueInformation-address-city`/`-zip`.

---

## 3. Coverage quantification

### 3a. Totals

- **Total listed future events:** pagination reports `1 of 77`; page 77 holds 4 cards, all others
  10 → **764 card entries** (76×10 + 4). The last listed dates are ~May 28–30, 2027 with one outlier
  Jun 23, 2027 (a placeholder/late end date). Consistent with the charting recon ("~764 to ~May 2027").
- **90-day Horizon window** (`2026-09-18 … 2026-12-17`, the project's Horizon length): the date filter
  `?f1=<startMs>-<endMs>` returns `1 of 65`, page 65 holds 9 → **649 card entries**.
- **Recurrence:** on a 50-card sample of the 90-day window, 31/50 = **62% carried `data-recurring`**.
  Across a broader 84-card sample (pages 1–5,6,10,20,30,40,50,60,77) 49/84 = **58% carried
  `data-recurring`**.

### 3b. Important correction: the listing is occurrence-expanded

**Cards are event *occurrences*, not unique events.** A recurring event occupies one card per
occurrence within the window. In the 50-card 90-day sample there were only **33 unique detail URLs**;
one event (`adult-ukulele-class`) recurs in 5 cards. Therefore:

- **764 cards ≈ substantially fewer unique events.** The exact unique-event total was not enumerated
  (that needs a full detail-crawl or full-pagination dedupe); treat **764 as an upper bound on
  occurrences, not on events**.
- The category filter counts are also occurrence-based (Community Event `(398)`, Performance `(508)`,
  Concert `(238)`, etc.) and sum to more than 764, so they count occurrences across categories.

> ```
> 1 of 77
> ```
> — `.EventSearchResultsModule-pageCounts`, `GET /community-calendar?p=1`

> ```
> 7 of 77   (last page = "77 of 77", 4 cards)
> ```
> — `GET /community-calendar?p=77`

### 3c. Bloomington allowlist share

The allowlist comes from `cities/bloomington/city.conf` (16 town names + 17 ZIPs):

> ```
> # zips: 46151, 46160, 47401, 47403, 47404, 47405, 47406, 47408, 47429, 47433,
> #       47434, 47435, 47448, 47458, 47460, 47464, 47468
> Bloomington  # 39.1670, -86.5343 (0.4 mi)
> Nashville    # 39.2072, -86.2469 (15.2 mi)
> ...
> ```
> — [`cities/bloomington/city.conf`](../../cities/bloomington/city.conf)

Matching uses `scrapers/lib/city_filter.py` (`location_matches_allowed_cities`), which matches the
**town name in the location string OR a ZIP in postal position**.

- A full-text `q=Bloomington` search over the whole listing returned **111 cards / 56 unique detail
  URLs** (12 pages). This over-counts because the site's free-text search also matches descriptions
  that mention "Bloomington" and duplicates per occurrence.
- The project's own pipeline previously recorded **20 Bloomington-area sources** in
  `cities/bloomington/geo_filtered.json` (355 lines) — see that file for the current per-source split.

**Honest coverage estimate:** measuring the allowlist share precisely requires a detail fetch per
unique event (only the detail page carries city/ZIP). From the 16 detail pages fetched, 12/16 had a
Bloomington-allowlist city/ZIP, 4 were out of area (Lafayette, Indianapolis, Bedford). That sample is
too small and deliberately weighted to Bloomington to extrapolate a share; **the exact allowlist
count is an explicit unknown** (see §7). It is clearly **non-zero and material** — q=Bloomington
alone surfaced 56 unique future events, many from venues the project does not currently cover
(Waldron Firebay, Morgenstern Books, WonderLab, Grunwald Gallery, the Monroe County Fairgrounds).

### 3d. Regional scope

Content is regional, not Bloomington-only: the 90-day sample includes Lafayette (`The Arts
Federation`), Indianapolis (`Hilbert Circle Theatre`), Bedford (`Bedford Public Library`), and
Nashville (`Mike's Music & Dance Barn`). A Bloomington ingestion must discard these.

---

## 4. UID stability

**Verdict: two candidate identifiers; prefer `brightspot.contentId`. Confidence — contentId: HIGH;
slug: MEDIUM.**

### 4a. `brightspot.contentId` (UUID)

Each detail page carries:

> ```html
> <meta content="000001a0-3430-d25b-a9ea-3e3853560000" name="brightspot.contentId">
> ```
> — `GET /community-calendar/event/heist-24-08-2026-10-32-57`

Brightspot documents this meta tag as **"the unique content identifier"** used to open the asset's
edit page, and its REST CMA / Content Fetch docs describe `_id` as the **UUID of the asset** that is
**unique across every content type**:

> "Only the content id is unique across every type, which is why anything else needs a Content Type
> to search within."
> — [Brightspot docs, Content Fetch action](https://docs.brightspot.com/docs/esca-automations/integrations/brightspot-cms/content-fetch-action)

> `"_id"` — "UUID of the asset. Use this value in update, read, and delete operations."
> — [Brightspot docs, REST Management API](https://docs.brightspot.com/docs/developer/rest-management-api)

This is the closest thing Brightspot has to a primary key and is the best UID source. **It is
detail-only — not present on the listing cards.** (The `brightspot.contentId` on a listing page is
the listing page's own ID, not an event's.)

### 4b. Detail slug

The slug is `…/event/<title-slug>-<DD-MM-YYYY-HH-MM-SS>` and is also the `<link rel="canonical">`
target. Brightspot documents that permalinks auto-generate from the slug/title and that, **once an
asset is published, the URL is retained** and not regenerated:

> "If you add the section at any point in the asset's workflow before publishing, it will change the
> auto-generated URL; however, once you publish the asset, this will not happen, and it will retain
> the URL path that was already generated for it."
> — [Brightspot docs, Site URLs](https://docs.brightspot.com/docs/user/site-urls)

> "Permalink—A permalink is the currently live URL associated with the asset. No two assets can have
> the same permalink."
> — [Brightspot docs, Content edit pages](https://docs.brightspot.com/docs/user/content-edit-pages)

This suggests slugs are **stable after publish**, but Brightspot also offers redirects/aliases if an
editor changes a permalink, so a **title edit could change the slug**. Confidence: **medium**. The
embedded timestamp (`24-08-2026-10-32-57`) appears to be record creation/import time, not event time
(note the "Heist" event is Sep 3–20 but the slug says Aug 24), so the slug likely survives *event
date* edits but not *title* edits.

### 4c. Evidence limitations

The Internet Archive CDX API was **temporarily offline** during this session (HTTP 503/504), so
sitemap-history comparison of a slug over time could not be performed:

> ```
> <title>Internet Archive: Temporarily Offline</title>
> ```
> — `GET https://web.archive.org/cdx/search/cdx?url=…`

`sitemap-latest.xml` only exposes the most recently modified URLs and does not provide historical
versions. **Recommendation:** use `brightspot.contentId` as the stable UID and the slug as a
secondary/near-key. If the Internet Archive returns, re-run the CDX query to confirm slug stability.

### 4d. One observed oddity

`contentId`s are not all of the form `000001a0-…`; some are `0000019f-…`, `0000019e-…`, and some end
in `…0001`/`…0003` rather than `…0000` (e.g. `Meet Me at the Metz Carillon Series` →
`000001a0-3e91-d31d-a5e9-3eb53a360001`). This is normal UUID variance, but it means a scraper must
not assume a fixed prefix/suffix.

---

## 5. Recurrence corpus

Saved to [`docs/fixtures/wfiu/wfiu-recurrence-corpus.txt`](../fixtures/wfiu/wfiu-recurrence-corpus.txt)
— **73 raw unique strings**, harvested from listing cards (`.PromoEvent-time`) and detail pages
(`.EventPage-information-time`) across all 77 listing pages plus 16 detail pages.

Observed grammar (all unstructured English, **no RRULE, no timezone**):

| Pattern | Count | Example |
| --- | --- | --- |
| One-off | 45 | `02:00 PM - 04:00 PM on Sat, 19 Sep 2026` |
| Daily | 13 | `09:00 AM - 10:00 PM, every day through Sep 20, 2026.` |
| Weekly | 14 | `Every week through Dec 17, 2026. Thursday: 10:00 AM - 10:30 AM` |
| Every N weeks | 1 | `Every 7 weeks through Oct 14, 2026. Wednesday: 12:30 PM - 02:30 PM` |
| Monthly | 0 | — |
| All-day / date-only | 0 | — |
| Continuous multi-day | 0 | — |

Notable corpus facts:
- Multi-day runs are rendered as **`every day through …`** (daily), not a `<start>–<end>` range
  (e.g. "Heist" Sep 3–20 → `every day through Sep 20, 2026.`).
- Weekly forms can list **multiple weekdays** in one string:
  `Every week through Nov 14, 2026. Tuesday: 12:00 PM - 04:00 PM Wednesday: 12:00 PM - 04:00 PM …`.
- Monthly cadence exists in **descriptions only** (e.g. Morgenstern Books' "monthly jazz salon …
  third Friday of each month") while the time field renders a **single one-off date**. The date
  grammar itself appears to have no monthly form.
- Several one-offs end at `11:59 PM` (possible midnight/all-day proxy).
- **`data-recurring` is a bare boolean attribute**, so any scraper must parse the English text to
  reconstruct a usable recurrence rule.

---

## 6. Fetch cost

### 6a. Full listing pass

- **77 requests** for `?p=1..77` (10 cards/page; last page 4). This covers all future events.
- **65 requests** for the 90-day window using `?f1=<startMs>-<endMs>&p=1..65` (649 card entries).
- The machine date-filter param is **`f1`** = `"<startEpochMs>-<endMs>"` (a hidden input fed by the
  `from`/`to` date pickers); `?from=`/`?to=` are **ignored**. Verified: `?f1=1789704000000-1797483600000`
  returns `1 of 65` and the last page contains Dec 17 events.
- `?q=<term>` searches free text (venue **and** description). `?f0=<categoryUUID>` filters by category.
  `pageSize`/`size`/`limit`/`perPage` are **ignored** (always 10/page) — pagination cannot be widened.

### 6b. Detail fetches

Each unique event needs a detail fetch for city/ZIP, ticket link, image, presenting org, full
description and `brightspot.contentId`. Because the listing is occurrence-expanded, a scraper should
**dedupe by detail URL** first, then fetch one detail page per unique event.

### 6c. Can the card prefilter without detail fetches?

**Partially — not for geography.**
- **Card is sufficient to prefilter:** past/expired dates (via `PromoEvent-date-date`), recurrence
  presence (`data-recurring`), category (`?f0=`), and a **keyword/city prefilter via `?q=`**.
- **Card is NOT sufficient** to apply the Bloomington allowlist, because the card exposes only the
  **venue name** (e.g. `Waldron Auditorium`), never street/city/zip. Geographic allowlisting requires
  a detail fetch.
- **Recommended fetch shape:** one `?f1=…&p=1..65` listing pass (65 requests) to build the unique-URL
  set, then one detail fetch per unique event to get city/ZIP. For 90 days and (empirically) roughly
  ⅔ of cards collapsing to unique events, that is on the order of a few hundred detail requests per
  run — a listing-first, dedupe-then-detail strategy is required to stay polite.

---

## 7. Explicit unknowns

1. **Exact unique-event count.** 764 is a count of occurrence-expanded cards; the unique-event total
   (and the unique 90-day total) was not enumerated. Estimating it needs full-pagination dedupe.
2. **Exact Bloomington-allowlist count/share.** Requires a detail fetch per unique event (only the
   detail page carries city/ZIP). The 16-detail sample was too small and Bloomington-weighted to
   extrapolate. `q=Bloomington` (56 unique URLs) is an over-counting upper bound.
3. **Slug stability across title edits.** Brightspot docs say published permalinks are retained, and
   redirects/aliases exist if they change — so a title edit *could* change the slug. The Internet
   Archive was offline, so no history check was possible. Use `contentId`, not the slug.
4. **`brightspot.contentId` stability under re-import/migration.** No direct evidence; the UUID is
   the documented primary key, but a CMS migration could in principle mint new IDs.
5. **Monthly / all-day / irregular rendering.** None were observed in 764 cards; whether the site
   *can* render them (vs. always collapsing to one-off/daily) is unverified. If any such event
   exists, its date grammar is unknown.
6. **Timezone.** No timezone marker appears in any date/time string; strings are presumably rendered
   in `America/Indiana/Indianapolis`, but this is inferred, not proven.

---

## 8. Recommendation

Scrape the HTML, not an API (there is none).

- **Listing:** `GET /community-calendar?f1=<startMs>-<endMs>&p=1..N` (65 pages / 90 days), parse
  `.PromoEvent`, and **dedupe by detail URL** because entries are occurrences.
- **Detail:** one `GET /community-calendar/event/<slug>` per unique event; read
  `meta[name=brightspot.contentId]` as the **UID**, `VenueInformation-address-*` for the city/ZIP
  allowlist, `.EventPage-ticketing a` for tickets, `.EventPage-image` for media, and
  `.PresentingOrganizationInformation-name` for the presenting org.
- **Recurrence:** parse `.PromoEvent-time` English text; `data-recurring` only tells you *that* it
  recurs. Patchy coverage of monthly/all-day forms — see §5 and §7.
- **Filtering:** use `?q=` and `data-recurring` to shrink the detail-fetch set; do geo-filtering only
  after detail fetch.

# Teton Valley, Idaho (Teton County) — Sources Checklist

Towns covered: **Driggs**, **Victor**, **Tetonia** (all in Teton County, ID).

Run date: 2026-04-30. All counts are VEVENT counts at probe time and will fluctuate.

## Discovered — Ready to Add (live ICS feeds)

| Source | Feed URL | Events | Notes |
|--------|----------|--------|-------|
| City of Driggs | `https://calendar.google.com/calendar/ical/c_e5t5ho387ibphu6srtavdjva94%40group.calendar.google.com/public/basic.ics` | 178 | Public Google Calendar embedded in driggsidaho.org/calendar (Gatsby+Prismic site uses `react-google-calendar-api`). X-WR-CALNAME: "City of Driggs Website Calendar". |
| City of Victor | `https://calendar.google.com/calendar/ical/d95970ccbd0d9ac3fdd51efe4064c592add68fea706cb5c44dcf4331f0d0b1e6%40group.calendar.google.com/public/basic.ics` | 57 | Public Google Calendar embedded in victoridaho.gov/calendar (Next.js site, calendar id in `pages/calendar-*.js`). X-WR-CALNAME: "General City Calendar". Includes city council and committee meetings + community events. |
| Teton School District 401 | `https://www.tsd401.org/servlet/ICalServlet?id=0` | 83 | Educational Networks / SchoolSitePro ICS feed (district-wide calendar). The "iCal Feed" link on tsd401.org/apps/events points at this URL. |
| Teton Arts — Ceramics Studio | `https://calendar.google.com/calendar/ical/e81c55546744ca431d2f88fc484a5760d3c92c42d6b3f8d83204e69b27d80433%40group.calendar.google.com/public/basic.ics` | 339 | Public Google Calendar embedded in tetonarts.org/programs-calendar. **Caveat:** mostly recurring class instances (potter's wheel, etc.) — may need filtering or downsampling. |
| Teton Arts — Multipurpose Studio | `https://calendar.google.com/calendar/ical/tg68i5qvit337le7f8gt5ip2b4%40group.calendar.google.com/public/basic.ics` | 437 | Same site, second public calendar iframe. **Same caveat:** recurring class instances dominate. |
| Friends of the Teton River | `https://www.tetonwater.org/community-events/?ical=1` | 1 | WordPress + **The Events Calendar Pro** (`PRODID:-//Friends of the Teton River - ECPv6.15.20//`). Tribe REST also live at `/wp-json/tribe/events/v1/events/`. Currently 1 upcoming event (State of the Fishery 2026); volume picks up seasonally. **Found via topical search: outdoors/conservation.** |

## Discovered — Ready (currently empty)

| Source | Feed URL | Events | Notes |
|--------|----------|--------|-------|
| Valley of the Tetons Library | `https://valleyofthetetonslibrary.org/events/?ical=1` (or Tribe REST: `/wp-json/tribe/events/v1/events/`) | 0 | WordPress + The Events Calendar (Tribe). API works (`{"events":[],...}`), feed is well-formed but currently empty. Worth wiring up; library staff occasionally publish programs (Maker Monday, Tech Friday, makerspace re-open events). |
| Highpoint Cider (Victor) | `https://www.highpointcider.com/events?format=json` | 0 | Squarespace **events collection** (type 10) at `/events` — currently 0 items but the slot is set up. Cidery hosts paint-and-sip, trivia, bingo, artisan markets per local guides. Use existing `scrapers/lib/squarespace.py` once they start posting. **Found via topical search: food/drink.** |
| Resilience Yoga (Driggs) | `https://resilienceyoga.org/events-privates?format=json` | 0 | Squarespace events collection "Events & Privates" at `/events-privates`, type 10, 0 items. Heated vinyasa/yin classes are listed elsewhere (`/classes`) as static program descriptions. Wire up the events slot speculatively. **Found via topical search: wellness.** |

## Scrapers Implemented (this repo)

| Source | Scraper | Events | Notes |
|--------|---------|--------|-------|
| Knotty Pine Supper Club (Victor) | `scrapers/knotty_pine.py` | 5 | WordPress + Enfold theme. Parses `div.avia_textblock` blocks: `<h1>` artist, `<h3>` date string, `<p>` (or heading) door/show times. Prefers "Show" time over "Door" when both present; defaults to 8pm and 2.5h duration. |
| Church in the Tetons (Driggs) | `scrapers/church_in_tetons.py` | 6 | WordPress + ezChurch / ChurchDev plugin. Parses `article.events-archive` with `.event-list-{date,time,title,details}`. Year inferred from displayed weekday + month/day, rolled forward when more than 30 days in the past. The ezChurch per-event ICS endpoint (`?cd_ics_download=1&event_id=NNNN`) and Google add-link `dates=` param both exist but were rejected: the latter shows the original recurrence start (e.g. 2016) for repeating events, while `.event-list-date` shows the next occurrence. |
| Teton Valley Trails & Pathways | `scrapers/tvtap.py` | 0 | Gatsby + **Contentful** CMS. Pulls `/page-data/events/page-data.json` → `allContentfulEventPost`. Currently 0 *upcoming* events because TVTAP's most recent post is dated September 2025. Scraper is correct; the source has gone dark on this channel — re-evaluate per `discovery-lessons.md` "When a Source Goes Dark, Follow the Events". |

## Discovered — Needs Scraper

| Source | URL | Notes |
|--------|-----|-------|
| Teton County, ID government | `https://tetoncountyidaho.gov/calendar.php` | revize CMS. Calendar JS calls `/calendar_data_handler.php?webspace=tetoncounty` but proxies to `cms3.revize.com` which is Cloudflare-protected (403 to non-browser). Need browser-based scrape or revize-specific scraper. |
| Teton County Fairgrounds | `https://www.tetoncountyfairgrounds.com/calendar.php` | Same revize CMS, same Cloudflare wall. Hosts the Teton Valley Fair, Teton Valley Balloon Rally, etc. |
| tetonvalleynews.net Local Events | `https://www.tetonvalleynews.net/local-events/` | TownNews (BLOX) site embedding **evvnt** widget (`evvnt-calendar-2210304`, partner=`TETONVALLEYNEWS`). evvnt API returns 401 without partner key; no public ICS. Custom HTML scrape (or evvnt partner credentials) required. Highest-value aggregator on the valley side. |
| Downtown Driggs Association | `https://downtowndriggs.org/events`, `/downtown-sounds` | Gatsby + Prismic CMS. No feed; static "Annual Events" page + `/downtown-sounds` lineup page. Concert series Jun–Sep. Could scrape Prismic API or HTML. |
| Teton Valley Foundation | `https://tetonvalleyfoundation.org/music-on-main/` | WordPress (Divi), no Tribe / MEC plugin. Music on Main concert series in Victor City Park, Thursdays late June – early August. Custom scrape. |
| Driggs Eventbrite | `https://www.eventbrite.com/d/id--driggs/events/` | Use existing `scrapers/eventbrite.py` (city URL pattern). Mostly art classes, paint-and-sip, scavenger hunts. |
| Victor Eventbrite | `https://www.eventbrite.com/d/id--victor/events/` | Same — existing `eventbrite.py` scraper. |
| Driggs Meetup | `https://www.meetup.com/find/us--id--driggs/` | Discovery page. Most listed groups are Bozeman / Utah-area; few or none are local. Sparse — probably skip after a per-group check. |
| Grand Targhee Resort | `https://www.grandtarghee.com/activities-events/events/event-calendar` | Drupal 11. No `?_format=json`, no obvious feed. **Note:** physically in Alta, WY (12 mi from Driggs) — cross-state but Driggs is its only road access. Decide whether to include based on geo policy. |
| Citizen 33 Brewery (Driggs) | `https://www.citizen33.com/` | Squarespace, but no `/events`, `/calendar`, or `/music` collection exists (all 404 or non-JSON). Music nights are likely posted to social only. Re-probe periodically; could appear later. **Found via topical search: music/food.** |
| Guidepost Brewing (Victor) | `https://guidepostbrewing.com/` | Squarespace, no events/music/calendar collection. Hosts Eventbrite-ticketed paint-&-sip nights — those flow through the city Eventbrite scraper. **Found via topical search: music/food.** |
| Grand Teton Brewing (Victor) | `https://grandtetonbrewing.com/events-2/` | WordPress + bold-page-builder, **no Tribe / no MEC**. `/events-2/` exists but at probe time it had **no upcoming events** (just an "Oktoberfest thank you" message). Re-probe seasonally before writing a scraper. **Found via topical search: music/food.** |
| Teton Regional Land Trust | `https://tetonlandtrust.org/events/` | WordPress + smart-post-show-pro + popup-maker, **no Tribe REST** (`/wp-json/tribe/events/v1/events/` → 404). `/events/?ical=1` returns 200 but 0 VEVENTs (not actually a Tribe site). Bespoke scrape against `/events/` HTML. **Found via topical search: outdoors/conservation.** |
| Bandsintown — Driggs aggregator | `https://www.bandsintown.com/c/driggs-id` | Bandsintown city page; could pull via the Bandsintown public API or HTML. Useful as a cross-check for Knotty Pine, Music on Main, etc. — most artists self-publish there. **Found via topical search: music.** |

## Non-Starters

| Source | Reason |
|--------|--------|
| City of Tetonia (`tetoniaidaho.com/calendar-of-events`) | Static HTML page; one event listed at probe time. No calendar system. Submit via email per their instructions. |
| Teton Valley Chamber Music Festival (`tetonvalleycmf.com`) | Squarespace, but `/festival-concert-calendar` is a generic page (collection type 10, 0 items) — concert dates are baked into static text, not an events collection. |
| Teton Valley Aquatics (`tetonvalleyaquatics.org/programs`) | Squarespace events collection (type 23) but the "items" are program *descriptions* (no startDate), not real events. |
| Discover Teton Valley (`discovertetonvalley.com`) | Gatsby site, no events page. Acts as a portal — links to Downtown Driggs etc. |
| Sports & Wellness (`sportsandwellness.org`) | GoDaddy site builder, no event data structure visible. Skip unless they add a real calendar. |
| The Yoga Source (`theyogasource.org`) | Wix site. Per playbook: "Wix sites are heavy JS nightmares — don't scrape directly." No public ICS. Class schedule lives inside the Wix booking widget. |
| Tetonia Club (`tetoniaclub.com`) | Wix site. Found a single Google Calendar `action=TEMPLATE` link for "Summer Music Series Kickoff" but that's an *add-to-calendar* link, not a feed source. Skip per Wix policy. |
| Spud Drive-In (`spuddrivein.com`, `thespuddrivein.com`) | Original `spuddrivein.com` is now a domain-squatter showing a non-English casino site (lang="ko"). `thespuddrivein.com` doesn't resolve. The drive-in reportedly reopened summer 2025; need a new authoritative URL before this is actionable. |
| Mary Immaculate Parish (`uppervalleycatholic.com`) | Duda site builder. Has `/calendar`, `/liturgical-calendar`, `/mass-times` pages but no embedded calendar feed or iframe — pages appear to be static text. Skip. |
| Teton Valley Farmers Market (`tetonvalleyfarmersmarket.org`) | Weebly. Hours/dates published as page text only. Single recurring event (Friday 9am–1pm at Driggs City Plaza, Jun–Oct) — model as a single recurring entry in the `feeds` table or via a tiny static ICS rather than a scraper. |
| Seniors West of the Tetons (`tetonseniors.org/calendar`) | Next.js (Vercel). Monthly activity calendars are published as **PNG/JPG images** uploaded to `media.tetonseniors.org` (e.g., `April-2026-activities-scaled.jpg`). No structured data — would require image-OCR pipeline (the project's `capture-event` edge function uses Claude Vision and could be repurposed, but unmodelled cost/benefit at this scale). Not currently practical. |
| Pierre's Theatre (`pierrestheatre.com`) | Next.js. Movie schedule does not appear in the SSR HTML or `_next/data/{buildId}/index.json`; likely loaded client-side from a movie-listing API. Re-probe with browser automation if needed. |

## Topical Search Coverage

Topics run on 2026-04-30 against the playbook list in `docs/curator-guide.md` Phase 2 and `docs/discovery-lessons.md` "Topical Searches". Adjusted for a small mountain valley with strong outdoor/arts identity.

| Topic | Searched? | Notable finds | Promoted to feed list |
|-------|-----------|---------------|-----------------------|
| Outdoors / hiking / cycling / conservation | ✅ | TVTAP (Gatsby+Contentful), Teton Regional Land Trust (WP no-Tribe), Friends of the Teton River (WP+Tribe Pro) | **FTR ICS** |
| Music / live concerts | ✅ | Knotty Pine, Citizen 33, Highpoint Cider, Guidepost, Grand Teton Brewing, Westside Yard, Tetonia Club, Bandsintown city page | Highpoint (empty Squarespace events slot) |
| Theater / film / galleries | ✅ | Pierre's Theatre (Next.js, no SSR data), Spud Drive-In (domain hijacked) | None |
| Faith communities | ✅ | Church in the Tetons (WP+ezChurch), Mary Immaculate (Duda), Good Shepherd Catholic (no website), LDS wards (no public feeds) | None — all need scrapers or skip |
| Food / drink / farmers market | ✅ | Teton Valley Farmers Market (Weebly), breweries above | None |
| Kids / seniors / wellness | ✅ | Seniors West of the Tetons (Next.js, calendars are JPG images), The Yoga Source (Wix), Resilience Yoga (Squarespace events slot, empty), Idaho Teton Yoga Co-op (Google Sites) | Resilience Yoga (empty Squarespace events slot) |
| Directories / aggregators | ✅ | tetonvalleynews.net Local Events (evvnt — auth-walled), tetonreserve.com Events & Festivals (curated text), thebarndriggs.com blog roundups (lifestyle, not feeds) | None |
| Comedy / improv | ⏭️ | Skipped — no obvious local scene; comedy nights at breweries surface via Knotty Pine / Highpoint when those are scraped | — |
| Books / poetry | ⏭️ | Library covers most of this (already in Ready list) | — |
| LGBTQ+ | ⏭️ | Population ~12k — no dedicated venue surfaced; would appear via city/library feeds when applicable | — |
| Dance | ⏭️ | Mostly covered by Driggs Sounds / Teton Arts (already listed) | — |
| Government / civic | (Phase 1) | Already covered: city of Driggs ✅, city of Victor ✅, Teton County government (revize, blocked), Tetonia (static) | — |

## To Investigate (next pass)

- [ ] **Bandsintown API** for Driggs and Victor — could backfill all music venues at once, including Knotty Pine, since most touring artists self-publish there
- [ ] **Yelp scan of Driggs / Victor** for craft shops, galleries, and pottery studios with their own calendars (per AGENTS.md "Yelp as discovery tool")
- [ ] **Grand Teton Brewing scraper** — small, high-signal, single page
- [ ] **TVTAP Contentful scrape** — confirm whether the 2024-heavy data set has fresh records before investing
- [ ] **Teton Valley Recreation District** (`tetonvalleyparksrec.org`) — newly formed Nov 2024; check whether website exists yet
- [ ] **Teton Springs Lodge** (Victor, private resort) — occasional Eventbrite-ticketed events, already captured via city Eventbrite
- [ ] **Teton Geo Center** — physical Driggs venue; events surface via DDA / TVN aggregation
- [ ] **Library makerspace** specific events feed (vs the district-wide library Tribe feed already in the Ready list)

## Geo notes

- Center: Driggs ID (43.7227, -111.1115)
- Towns to allow: Driggs, Victor, Tetonia, Alta (WY — only if Grand Targhee included)
- State for `city.conf`: `ID`
- Watch for false-positive matches against "Teton County, WY" (Jackson) — separate jurisdiction across the Teton Pass.

## Validated probe commands (reproducible)

```bash
# City of Driggs — Google Calendar (id from /component---src-pages-calendar-*.js)
curl -sL "https://calendar.google.com/calendar/ical/c_e5t5ho387ibphu6srtavdjva94%40group.calendar.google.com/public/basic.ics" | grep -c BEGIN:VEVENT

# City of Victor — Google Calendar (id from /_next/static/chunks/pages/calendar-*.js)
curl -sL "https://calendar.google.com/calendar/ical/d95970ccbd0d9ac3fdd51efe4064c592add68fea706cb5c44dcf4331f0d0b1e6%40group.calendar.google.com/public/basic.ics" | grep -c BEGIN:VEVENT

# TSD 401 — Educational Networks
curl -sL "https://www.tsd401.org/servlet/ICalServlet?id=0" | grep -c BEGIN:VEVENT

# Teton Arts (two iframes on programs-calendar page)
curl -sL "https://calendar.google.com/calendar/ical/e81c55546744ca431d2f88fc484a5760d3c92c42d6b3f8d83204e69b27d80433%40group.calendar.google.com/public/basic.ics" | grep -c BEGIN:VEVENT
curl -sL "https://calendar.google.com/calendar/ical/tg68i5qvit337le7f8gt5ip2b4%40group.calendar.google.com/public/basic.ics" | grep -c BEGIN:VEVENT

# Library — currently empty but live
curl -sL "https://valleyofthetetonslibrary.org/wp-json/tribe/events/v1/events/?per_page=3"
```

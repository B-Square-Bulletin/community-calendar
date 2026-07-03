# Platform-Specific Techniques

## Quick Reference Table

| Platform             | Feed Pattern                                                                                        |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| **MembershipWorks**  | `https://api.membershipworks.com/v2/events?_op=ics&org={ORG_ID}`                                    |
| **Tockify**          | `https://tockify.com/api/feeds/ics/{CALENDAR_ID}`                                                   |
| **LiveWhale**        | `https://{domain}/live/ical/events`                                                                 |
| **Localist**         | `https://{domain}/api/2/events`                                                                     |
| **GoDaddy Calendar** | Check DevTools for `calendar.apps.secureserver.net` requests (use scraper)                          |
| **Drupal**           | Try `/events/feed/json`, `?_format=json`, `drupal-settings-json`, then site-specific HTML scraping  |
| **WordPress Tribe**  | `https://example.com/events/?ical=1`                                                                |
| **WordPress MEC**    | `https://example.com/events/?mec-ical-feed=1`                                                       |
| **Legistar**         | `https://webapi.legistar.com/v1/{client}/events` (WebAPI, use scraper)                              |
| **CivicPlus**        | `https://www.{city}.org/common/modules/iCalendar/iCalendar.aspx?feed=calendar&catID={N}`            |
| **Songkick**         | `https://www.songkick.com/venues/{ID}-{slug}` (JSON-LD MusicEvent, use `scrapers/songkick.py`)      |
| **Guild.host**       | No ICS feeds. JSON-LD Event on individual pages. Tech-focused platform. Use `scrapers/guildhost.py` |

## Drupal

Drupal does not have a single standard event-feed pattern. Treat it as a short decision tree, not a generic platform:

1. Try a machine-readable feed first:
   - `/events/feed/json`
   - `?_format=json`
   - any obvious view-specific JSON endpoint exposed by the site
2. Check for embedded data:
   - `<script data-drupal-selector="drupal-settings-json">`
   - JSON payloads attached to calendar views
3. Fall back to HTML scraping:
   - listing cards in `views-row`
   - event nodes like `article.node--type-event`
   - date fields like `field--name-field-dates`
   - theme-specific wrappers like `node-events-*` or `listing-item--events`
4. On detail pages, look for structured clues before hand-parsing:
   - taxonomy labels
   - visible location/date blocks
   - `Add to iCal` links, including embedded `data:text/calendar` payloads

**Repo examples:**

- `scrapers/drupal_events.py` — reusable JSON feed pattern
- `scrapers/waterfront_toronto.py` — embedded `drupal-settings-json`
- `scrapers/toronto_community_housing.py` — listing-card HTML scraper
- `scrapers/uoft_events.py` — mixed-theme Drupal parser
- `scrapers/jccc.py` — Drupal listing + detail pages, including multi-date expansion

## SeeTickets Widgets

HTML classes: `.title a`, `.date`, `.see-showtime`, `.see-doortime`, `.genre`, `.ages`, `.price`
Example: `scrapers/mystic_theatre.py`

## Wix Events

Wix event pages vary. Some use cross-origin iframes from `geteventviewer.com` (not scrapeable). But others server-render events in a **Wix Repeater component** with structured HTML — these are scrapeable (see `scrapers/cafefrida.py` for an example). Check the page source before writing off a Wix site. If the events are in the HTML (look for `data-hook` attributes and repeater items), a scraper can extract them. If it's an iframe to `geteventviewer.com`, check if the venue is on Eventbrite instead.

## Events Manager (EM)

WordPress plugin. Use `scrapers/lib/em_events.py` — AJAX endpoint at `/wp-admin/admin-ajax.php?action=search_events` returns up to 50 events per POST with `pno` and `limit` params. HTML rendered, parse with `.em-event`, `.em-item-title`, `.em-event-date`, `.em-event-time`, `.em-event-location` selectors.

## Known Platform Limitations

| Platform                          | Issue                                                                                                                                                                                                                                                                                                                                                             |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Planning Center/Church Center** | No public API; requires login                                                                                                                                                                                                                                                                                                                                     |
| **Simpleview CMS**                | Tourism sites; no public events API                                                                                                                                                                                                                                                                                                                               |
| **Cloudflare-protected sites**    | Challenge pages block scrapers                                                                                                                                                                                                                                                                                                                                    |
| **Facebook Events**               | No public API since 2018                                                                                                                                                                                                                                                                                                                                          |
| **Granicus video**                | RSS feeds at `{instance}.granicus.com/ViewPublisherRSS.php?view_id={N}` are **backward-looking only** (archived meeting videos). Not useful for upcoming events. Don't confuse with Legistar (also Granicus-owned), which has a forward-looking WebAPI.                                                                                                           |
| **Bandsintown**                   | Website behind Cloudflare (403 on curl). REST API requires written approval from Bandsintown. Even with API access, no venue endpoint — only `/artists/{name}/events`. Not viable.                                                                                                                                                                                |
| **SeeTickets / Eventim US**       | SeeTickets US rebranded as Eventim in March 2025 (same platform). No public API — affiliate account required. Cannot filter by single venue. US platform runs legacy ASP.NET (`wafform.aspx`), unlike Eventim Europe which has an unauthenticated search API at `public-api.eventim.com`. Venues like Mystic Theatre and HopMonk use this platform for ticketing. |
| **BoardDocs**                     | Used by some cities for agenda publishing (e.g., `go.boarddocs.com/nc/raleigh/`). No public calendar API; LlamaIndex has a reader but it's for document extraction, not event feeds.                                                                                                                                                                              |

## Songkick

Artist-sourced music venue data via JSON-LD `MusicEvent` on venue pages. When a music venue's own site is hard to scrape (bot protection, heavy JS, ticketing widgets), look for the venue on Songkick — artists push their own tour dates there.

**Why this works:** The data flows artist → aggregator → venue page. You're getting artist-sourced tour data, not scraping the venue. A single page fetch returns `MusicEvent` JSON-LD for all upcoming shows.

**Why NOT Bandsintown:** Bandsintown is a walled garden — Cloudflare protected, API requires written approval, and no venue endpoint exists. Songkick is the only viable platform in this category.

**How to check:**

```bash
# Search Songkick for the venue
curl -sL "https://www.songkick.com/search?query=wellmont+theater&type=venues" | grep -o 'href="/venues/[^"]*"' | head -5

# Fetch the venue page and check for JSON-LD
curl -sL "https://www.songkick.com/venues/32209-wellmont-theater" | grep -c 'MusicEvent'
```

**When to use:**

- Venue site has bot protection (ShowDog, Cloudflare, etc.)
- Venue tickets through a platform that's hard to scrape (Ticketmaster, AXS)
- You want clean, structured data with minimal HTTP requests
- The venue is a music venue (this pattern is music-specific)

Reusable scraper: `scrapers/songkick.py` handles any Songkick venue page. See [scrapers.md](scrapers.md#songkick-scraperssongkickpy----music-venue-showtimes).

## Google Sites with Embedded Google Calendars

Google Sites is used by small businesses, community groups, churches, and hobby organizations. When they embed a Google Calendar, the calendar ID(s) appear in the static HTML — no browser rendering needed.

**Discovery:**

```bash
site:sites.google.com {city} events calendar
site:sites.google.com {city} {topic} calendar
```

**Extraction:**

```bash
curl -sL "https://sites.google.com/view/{page}/" | \
  grep -o '[a-zA-Z0-9._-]*@group.calendar.google.com' | sort -u
```

Each ID becomes `https://calendar.google.com/calendar/ical/{ID}/public/basic.ics`.

**Caveat:** The calendar must have public sharing enabled. If the ICS URL returns 404, it's private.

**Why this matters:** Google Sites pages are invisible to WordPress plugin searches, Meetup, and Eventbrite. Yet they often host the only machine-readable calendar for niche community groups. A single Google Sites aggregator page can surface an entire community's event infrastructure — the Toronto Tango Calendar page embeds 16 separate public Google Calendars from different organizers, yielding 691 events total.

See [discovery-lessons.md](discovery-lessons.md#google-sites-pages-with-embedded-google-calendars) for the full write-up.

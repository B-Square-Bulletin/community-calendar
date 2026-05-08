# Newcastleva Sources Checklist

Geo-filter restricted to **Craig County, VA** (New Castle, Paint Bank).

## Currently Implemented

| Source | Type | Events | URL |
|--------|------|--------|-----|

## Discovered - Ready to Add

| Source | Feed URL | Events | Notes |
|--------|----------|--------|-------|
| Craig County Government | `https://www.craigcountyva.gov/common/modules/iCalendar/iCalendar.aspx?catID=14&feed=calendar` | 96 | CivicPlus "Main Calendar" — superset of Board of Supervisors, Events, Meetings sub-calendars |
| Craig County Public Library | Tribe Events REST API at `craigcountypubliclibrary.org/wp-json/tribe/events/v1/events` | 1 | WordPress + The Events Calendar Pro. `?ical=1` returns 403 (WAF), use `lib/tribe_events.py` |

## Needs Scraper

| Source | URL | Approach | Notes |
|--------|-----|----------|-------|

## Non-Starters

| Source | Reason |
|--------|--------|
| Beliveau Farm Winery (Blacksburg, ~16 mi) | Squarespace site. `/visit?format=json` returns 0 items; `/visit` page lists 30 events but all are past (latest 2026-02-28). Current "Upcoming Events" on homepage are free-form paragraph text without years — not parseable. Per-event ICS at `?format=ical` works individually but no upcoming events are published as Squarespace event records. |
| New Castle Record newspaper (`newcastlerecord.com/community-calendar/`) | Article last updated 2023-01-31. WordPress + JNews + Leaky Paywall, no calendar plugin. Static prose, stale by 3+ years. |
| Craig County Public Schools (`craig.k12.va.us`) | Site protected by Finalsite "Client Challenge" JS bot wall. |
| Craig County Fairgrounds (`craigcountyfairgrounds.com/events/`) | `/events/` redirects to `/agendas`. No public calendar. (Active calendar is on Facebook.) |
| Visit Craig County VA (`visitcraigcountyva.com`) | GoDaddy Website Builder. Only an external link to `facebook.com/craigco.VA.events`. |
| Visit Craig County WordPress (`craigcountyva.gov/visitcraigcounty/`) | Returns 404 — old WP/ai1ec subdirectory was migrated into the CivicPlus main site. |
| The Depot Lodge / Paint Bank General Store | Squarespace, but `/things-to-do` is a static page (collection type 10) with no event items. |
| Craig County Farmers Market (`craigcountyfarmersmarket.com`) | WordPress, no calendar plugin (only PixelYourSite). Static info. |
| Craig County Volunteer Fire Department | No website with calendar; only Facebook. |
| Craig County Tourism Commission, Historical Society | No web calendar found. |

## To Investigate

- [ ] Facebook event scraping — fairgrounds + Craig County events Facebook page have most local events but Facebook's Graph API requires a page access token. Not currently scraped by this project.
- [ ] Beliveau Winery — recheck in a few weeks; if they start publishing 2026 events as Squarespace event records, the per-event ICS aggregator pattern (`lib.raptor_trust`-style) would yield ~30 events/year.

---

See [docs/procedures.md](../../docs/procedures.md) for discovery techniques.

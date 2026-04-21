# Toronto Luma Host Inventory

Last updated: 2026-04-19

This file tracks Luma collection pages worth evaluating for Toronto coverage.

Key rule:
- Prefer `Events Calendar` / collection pages over `user/...` pages.
- Treat `user/...` pages as supporting metadata only.
- Do not assume a `cal-...` ID found on an event page represents the organizer's full public collection.

## Discovery Method

Seed set:
- Toronto discover page: `https://luma.com/toronto`
- Toronto discover ICS: `https://api2.luma.com/ics/get?entity=discover&id=discplace-Cx3JMS6vXKAbhV5`

Resolution strategy:
- Start from organizer names seen on Toronto Luma event pages.
- Search for `site:luma.com "<organizer>" "Events Calendar"`.
- Only fall back to `site:luma.com/user "<organizer>"` when no collection page is found.

## High Priority

### Pluto Toronto
- Collection page: `https://luma.com/plutotoronto`
- Supporting user pages:
  - `https://luma.com/user/enterpluto`
  - `https://luma.com/user/pluto`
- Status:
  - Implemented on 2026-04-19 via `scrapers/luma_collection.py`
  - Scraper now uses the collection page only to derive `calendar_api_id`, then fetches the full future collection from Luma's paginated `calendar/get-items` endpoint
- Why it matters:
  - Confirmed Toronto-local collection
  - `Celestial Night Prom` was live on Luma but absent from Toronto Discover
  - Strong evidence that discover is curated and misses real local events
  - Current validation yields 24 future events, all net new versus the current Toronto Discover feed
- Recommendation:
  - Keep as the template source for further Luma collection-page adds

### Toronto Social Mixer
- Collection page: `https://luma.com/TorontoSocialMixer`
- Why it matters:
  - Clearly Toronto-local recurring series
  - Distinct social/networking niche
  - Looks like a compact, durable collection rather than a citywide aggregator
- Status:
  - Staged on 2026-04-19 via `scrapers/luma_collection.py`
  - Current validation yields 1 future event, net new versus both Toronto Discover and Pluto Toronto
- Recommendation:
  - Keep staged and recheck volume over time; currently low-volume but clean

### Uplift Collective
- Collection page: `https://luma.com/upliftcollective`
- Why it matters:
  - Surfaced by the Yelp/venue pass through repeated Boxcar Social-hosted events
  - Toronto-local sustainability / community coffee-chat series
  - Current collection has no overlap with the already staged Luma Toronto sources
- Status:
  - Staged on 2026-04-19 via `scrapers/luma_collection.py`
  - Current validation yields 7 future events after the six-month cutoff, all net new versus Discover + Pluto + Toronto Social Mixer + TechTO
- Recommendation:
  - Strong next-wave collection source; cleaner than TechTO and more active than Toronto Social Mixer

## Medium Priority

### TechTO
- Collection page: `https://luma.com/TechTO-Events`
- Why it matters:
  - Important Toronto tech brand
  - Already validated separately in earlier Luma research
- Status:
  - Staged on 2026-04-19 via `scrapers/luma_collection.py`
  - Current validation yields 10 future events, 6 net new versus Discover + Pluto + Toronto Social Mixer
- Limitation:
  - Includes non-Toronto events such as Vancouver
  - Already overlaps an existing Meetup source
- Recommendation:
  - Reasonable staged source, but not as clean as Pluto because of cross-city spillover

### again again
- Collection page: `https://luma.com/againagain`
- Why it matters:
  - Toronto-local recurring social/craft/comedy host already visible on the Toronto discover page
- Status:
  - Staged on 2026-04-19 via `scrapers/luma_collection.py`
  - Current validation yields 3 future events, with 1 net-new URL versus the staged Toronto Luma set
- Recommendation:
  - Small but clean local add

### airess
- Collection page: `https://luma.com/airess`
- Why it matters:
  - Toronto-local women-in-tech / career-oriented events
- Status:
  - Staged on 2026-04-19 via `scrapers/luma_collection.py`
  - Current validation yields 2 future events, with 1 net-new URL versus the staged Toronto Luma set
- Recommendation:
  - Small but clean local add

### UTE
- Collection page: `https://luma.com/ute`
- Why it matters:
  - University of Toronto Entrepreneurship; good institutional signal
- Status:
  - Staged on 2026-04-19 via `scrapers/luma_collection.py`
  - Current validation yields 3 future events, with 1 net-new URL versus the staged Toronto Luma set
- Recommendation:
  - Small but credible academic/entrepreneurship add

### Cloud Events
- Collection page: `https://luma.com/CloudCanada`
- Why it matters:
  - Valid Canada-focused cloud/AI collection
  - Includes Toronto-specific events
- Limitation:
  - Canada-wide, not Toronto-only
- Recommendation:
  - Worth evaluating if Toronto filtering is acceptable

### Toronto Tech Week
- Collection page: `https://luma.com/torontotechweek`
- Why it matters:
  - Very large Toronto event surface
- Limitation:
  - Seasonal and extremely noisy
- Status:
  - Staged on 2026-04-21 via `scrapers/luma_collection.py`. 186 future events at time of staging. Users can filter or disable the feed.

## Broad / Likely Noisy

### The AI Collective
- Collection page: `https://luma.com/genai-collective`
- Why it matters:
  - Toronto chapter events exist
- Limitation:
  - Global collection, not Toronto-specific
- Recommendation:
  - Useful as a known source family, but not a clean Toronto collection

### Andrew's Yeung's Tech Events
- Collection page: `https://luma.com/andrewsmixers`
- Why it matters:
  - Includes Toronto events
- Limitation:
  - Multi-city collection spanning NYC, SF, Austin, Miami, Toronto
- Recommendation:
  - Too broad for direct Toronto ingestion without a collection-page scraper plus geo filtering

## Notes

- `Pluto Toronto` proved that the host/user page and the event-page `cal-...` ID can point to very different scopes.
- Luma collection JSON-LD is only a teaser. For complete coverage, resolve the collection page's `calendar_api_id` and use the public `calendar/get-items` API rather than trusting the server-rendered event list.
- The Toronto discover feed remains the best single Luma source, but it is not exhaustive.
- The Yelp strategy is working best when used to discover recurring host brands at Toronto venues, then resolving those brands to Luma collection pages. Current Yelp-derived results:
  - strong add: `upliftcollective`
  - weak but real: `sautesundaysto`
  - currently dormant: `thatslowjamparty`, `jointhelevelup`
- The next concrete implementation step is a reusable scraper for Luma collection pages such as:
  - `https://luma.com/plutotoronto`
  - `https://luma.com/TorontoSocialMixer`

# Research: Haunts coverage gap & upstream reachability (Bloomington, next ~90 days)

Ticket: [#180](https://github.com/B-Square-Bulletin/community-calendar/issues/180) (parent map [#179](https://github.com/B-Square-Bulletin/community-calendar/issues/179)).
Branch: `research/haunts-coverage-gap`. **No PR opened.**

## TL;DR

Over the 90-day window, the new Haunts/Limestone feed carries **~1,790–1,890 Bloomington-footprint events we do not have (~39–41% of its in-window events)**. That gap is **overwhelmingly directly ingestible**: **D ≈ 1,779 (99.5%)**, **N ≈ 7 (0.4%)**, **U = 2 (0.1%)**. There is **no high-value recurring U source**. Two already-configured feeds that are currently broken — **Monroe County Public Library (480)** and **Brown County Events (470)** — account for **~53% of the entire gap**; repairing them is not source acquisition at all. The numbers point at **Option 3 (drop Limestone/Haunts and ingest directly)**, with the caveat that most of the "gap" is fixing existing ingest, not adding new sources.

## 1. Event sets, snapshots, and matching method

| Set | Snapshot date | How obtained | Total rows | In-window rows |
|---|---|---|---|---|
| **Haunts** (Limestone's new calendar) | 2026-10-09 | `POST https://iybudynadpwzeyjtlepj.supabase.co/rest/v1/rpc/get_embed_feed` (`p_slug=things-to-do`, `p_limit=200`, cursor-paginated), anon JWT, `Content-Profile: caddie`, `Origin: https://limestonepost.org` | 4,618 | **4,608** |
| **Ours** (live Bloomington DB) | 2026-10-09 | `GET https://qatykxdvbpojxnvpicyi.supabase.co/rest/v1/events?select=…&order=start_time.asc` with the `xmlui/config.json` publishable key, offset-paginated | 7,352 | **6,693** |

- Window: **2026-10-09 → 2027-01-07** (local dates, `America/Indiana/Indianapolis`).
- **Haunts horizon caveat:** the Haunts pull contains **no `start_at` after 2026-12-09**. The feed only covers ~60 of the 90 requested days; the 2026-12-09 → 2027-01-07 tail cannot be assessed from this feed. Our DB extends to 2031 (a few recurring series), so the window comparison is effectively **2026-10-09 → 2026-12-08**.
- Source count observed: **71 distinct `source_name`** values (the ticket/map cite 74; the difference is likely snapshot drift or source variants — noted, not reconciled).
- All of ours is Bloomington city (`city=bloomington`); all Haunts rows are treated as Bloomington-footprint.

### Matching method

For each in-window Haunts event: normalize title (NFKD, lowercase, strip punctuation/whitespace), take the **local start date**, and compare against all of our in-window events **on the same local date** using a title-similarity score (exact normalized equality, `difflib` ratio, token Jaccard, and containment/token-subset for titles with extra qualifiers like "SIX" vs "SIX (Touring)"). Venue is recorded but **not required**, because Haunts `location_venue` is null on most rows and our `location` is often empty; requiring it would inflate the gap.

Threshold sensitivity (same-date + title):

| Threshold | Matched | Overlap % of Haunts | Haunts-unique |
|---|---|---|---|
| exact title | 2,716 | 58.9% | 1,892 |
| strict (score ≥ 0.90) | 2,813 | 61.0% | 1,795 |
| loose (score ≥ 0.75) | 2,820 | 61.2% | 1,788 |

**Overlap ≈ 59–61%; Haunts-unique ≈ 1,788–1,892.** The tight range is because normalized titles match cleanly (only ~4 events move between strict and loose). Classification below uses the **loose** set (1,788) as the conservative (smallest) gap; the headline gap range is stated as ~1,790–1,890.

## 2. Haunts-unique set, by `source_name`

Loose-threshold uniques (1,788), by Haunts upstream source:

| # | Haunts `source_name` | Unique events |
|---|---|---|
| 1 | Monroe County Public Library | 480 |
| 2 | Brown County Events | 470 |
| 3 | Eventbrite circa Bloomington | 289 |
| 4 | Visit Morgan County | 132 |
| 5 | WFHB events | 99 |
| 6 | IU Athletics | 80 |
| 7 | Indivisible Central Indiana | 50 |
| 8 | Visit Bloomington | 40 |
| 9 | Brown County Government | 28 |
| 10 | IU Eskenazi School of Art | 22 |
| 11 | IU beINvolved Student Orgs | 16 |
| 12 | Morgenstern Books | 16 |
| 13 | Morgan County Government | 13 |
| 14 | The Bishop Bar | 11 |
| 15 | Brown County State Park | 6 |
| 16 | IU Maurer School of Law | 5 |
| 17 | Monroe County History Center | 4 |
| 18 | FAR Center for Contemporary Arts | 4 |
| 19 | Monroe County Civic Theater | 3 |
| 20 | Goat Conspiracy | 2 |
| 21 | Eskenazi Museum of Art | 2 |
| 22 | On Tap Tickets | 2 |
| 23 | Buskirk Chumley Theater | 2 |
| 24 | PEA Pod | 2 |
| 25 | Keplinger Institute for Wellness and Art | 2 |
| 26 | Monroe County (localist feed) | 1 |
| 27 | Wonder Lab Museum | 1 |
| 28 | IU La Casa Latino Cultural Center | 1 |
| 29 | Rebel Purl | 1 |
| 30 | Bloomington Bicycle Club | 1 |
| 31 | IU Jacobs School of Music | 1 |
| 32 | IU Asian Culture Center | 1 |
| 33 | The FAR | 1 |
| | **Total** | **1,788** |

## 3. Reachability class per unique-event upstream source

### D — directly ingestible (mechanism we have or an ICS feed)

| Haunts source | Unique | Mechanism | Already configured for Bloomington? |
|---|---|---|---|
| Monroe County Public Library | 480 | ICS `calendar.mcpl.info/feeds?...` (`bibliocommons`/ICS) | **Yes — in `feeds.txt`; currently returns 403 Forbidden (verified 2026-10-09).** Broken, not missing. |
| Brown County Events | 470 | MEC ICS `browncounty.com/events/?mec-ical-feed=1` | **Yes — in `feeds.txt`; currently returns `error code: 504` (verified 2026-10-09).** Broken, not missing. |
| Eventbrite circa Bloomington | 289 | `scrapers/eventbrite.py` (Eventbrite organizer/search) | Mechanism yes; only two organizers configured (Exodus, Gaden). The Bloomington search/collection would be a new config. |
| Visit Morgan County | 132 | `scrapers/simpleview.py` | **Yes — `simpleview_morgan.ics` configured** (only 12 live rows → feed likely stale/broken). |
| WFHB events | 99 | `scrapers/wfhb_calendar.py` (EmEvents AJAX `wfhb.org/wp-admin/admin-ajax.php`) | Scraper exists; **not registered** in `feeds.txt`. |
| IU Athletics | 80 | `events.iu.edu/hoosiers` LiveWhale ICS (we already ingest ~20 `events.iu.edu` group feeds) and/or `scrapers/sidearm.py` (`iuhoosiers.com`) | Mechanism yes; athletics calendar not registered. |
| Indivisible Central Indiana | 50 | `scrapers/mobilize.py` (`mobilize.us/indivisiblecentralindiana/`) | Mechanism yes; only Indivisible South Central Indiana configured. |
| Visit Bloomington | 40 | `scrapers/visit_bloomington.py` | **Yes — configured** (669 live rows; these 40 are newer/missed instances). |
| Brown County Government | 28 | `scrapers/brown_county_gov.py` (CivicPlus iCal) | Scraper exists; **not registered**. |
| IU Eskenazi School of Art | 22 | `events.iu.edu/live/ical/events/group_id/11` | **Yes — configured** (226 live rows; these are newer instances). |
| IU beINvolved Student Orgs | 16 | `iub.campuslabs.com/engage/events.ics` | **Yes — configured** (1,099 live rows). |
| Morgenstern Books | 16 | `scrapers/bookmanager.py` (Bookmanager bookstore) | Mechanism exists; **not registered**. |
| Morgan County Government | 13 | eGov ICS (`morgancounty.in.gov/egov/apps/events/calendar.egov?view=ical` — same platform as Ellettsville, already configured) | Mechanism yes; Morgan not registered. |
| The Bishop Bar | 11 | `scrapers/the_bishop.py` | **Yes — configured** (4 live rows; mostly stale). |
| Brown County State Park | 6 | `events.in.gov` ICS (we already ingest `events.in.gov` feeds for state events and Monroe Lake) | Mechanism yes; state-park event type not registered. |
| IU Maurer School of Law | 5 | `events.iu.edu/live/ical/events/group_id/64` | **Yes — configured** (122 live rows). |
| Monroe County History Center | 4 | `scrapers/monroe_county_history_center.py` | Scraper exists; **not registered**. |
| Monroe County Civic Theater | 3 | `scrapers/ludus.py` (`mcct.ludus.com`) | **Yes — configured**. |
| Goat Conspiracy | 2 | `scrapers/squarespace.py` (`thegoatconspiracy.com` — confirmed Squarespace) | Mechanism exists; **not registered**. |
| Eskenazi Museum of Art | 2 | `events.iu.edu/live/ical/events/group_id/234` | **Yes — configured**. |
| Buskirk Chumley Theater | 2 | `scrapers/buskirk_chumley.py` | **Yes — configured**. |
| Keplinger Institute for Wellness and Art | 2 | `scrapers/eventbrite.py` (Eventbrite organizer) | Mechanism yes; organizer not registered. |
| Monroe County (localist feed) | 1 | `scrapers/localist.py` | Mechanism exists. |
| Wonder Lab Museum | 1 | ICS `wonderlab.org/events/list/?ical=1` | **Yes — configured**. |
| IU La Casa Latino Cultural Center | 1 | `events.iu.edu/live/ical/events/group_id/59` | **Yes — configured**. |
| Rebel Purl | 1 | Google Calendar ICS | **Yes — configured**. |
| Bloomington Bicycle Club | 1 | Google Calendar ICS | **Yes — configured**. |
| IU Jacobs School of Music | 1 | `events.iu.edu/live/ical/events/group_id/56` | **Yes — configured**. |
| IU Asian Culture Center | 1 | `events.iu.edu/live/ical/events/group_id/314` | **Yes — configured**. |
| **D total** | **1,779** | | |

### N — new bespoke scraper needed

| Haunts source | Unique | What a scraper would take |
|---|---|---|
| FAR Center for Contemporary Arts (+ "The FAR") | 5 | `thefar.org` is **Craft CMS** (CRAFT_CSRF_TOKEN, no WordPress/Tribe/Squarespace markers). No ICS or JSON-LD platform; needs a bespoke HTML/JSON scraper against `thefar.org/events/list`. Low volume (~5 events/90d). |
| On Tap Tickets | 2 | `ontaptickets.com` ticketing for Tier 10 Music and Sports Park (Spencer) and The MET (Martinsville). No ICS/known platform; bespoke listing scrape. Very low volume (2 events). |

**N total: 7 (0.4%).**

### U — no independently reachable source

| Haunts source | Unique | Why unreachable |
|---|---|---|
| PEA Pod | 2 | "Whole-food plant-based potluck hosted by PEA Pod" — **no `url`**, no venue page, location is a church address. Submission/social/email-list only. Recurring (monthly) but low-volume and not a high-value series. |

**U total: 2 (0.1%).** No other source is U: "Things to Do in Bloomington, Indiana — submissions" has **0 in-window uniques** (all matched our set).

## 4. Shares and high-value recurring U

| Class | Count | % of uniques |
|---|---|---|
| **D** | 1,779 | **99.5%** |
| **N** | 7 | **0.4%** |
| **U** | 2 | **0.1%** |

- **High-value recurring U source: none.** The only U source (PEA Pod) is a monthly potluck with no upstream page.
- **Dominant caveat:** the two largest D blocks — **Monroe County Public Library (480) and Brown County Events (470) = 950 events, 53% of the gap** — are feeds we **already list** and that are currently failing at the source (MCPL `403`, Brown County `504`). This is an ingest-repair problem, not a source-acquisition problem. A further set of D sources (WFHB, Brown County Government, Morgenstern, Monroe County History Center, Goat Conspiracy, IU Athletics, Morgan County Government, Brown County State Park, Eventbrite collection, Indivisible Central Indiana) have **reusable scrapers already in the repo but are not registered** in `feeds.txt`.

## 5. Recommendation stub (for the decision ticket, #179/#181)

> **Option 3** — the Haunts-unique gap is 99.9% D/N and only 0.1% U with no high-value recurring U source (Option 2's ≥10%-U trigger is far from met), and the gap is large enough not to be Option 1; drop Limestone/Haunts and ingest directly, **starting by repairing the two already-configured broken feeds (MCPL, Brown County Events) that alone account for ~53% of the gap**, then registering the ~10 existing-but-unregistered scrapers, and only last writing the two low-volume bespoke scrapers (FAR, On Tap Tickets).

## Method notes / limitations

- Snapshot is 2026-10-09; both sets are point-in-time and our DB has no build-stamp field on rows, so "ours" is the live published table, not a dated local build.
- Haunts horizon ends 2026-12-09, so the last ~30 days of the requested window are not represented in Haunts at all.
- Overlap is a range (59–61%) because a few titles differ by qualifiers ("SIX" vs "SIX (Touring)"); venue was not required as a match key due to missing venue data.
- `source_name` is taken as authoritative upstream attribution, per the ticket.

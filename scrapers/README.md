# Event Scrapers

Python scrapers for extracting events from various venues that don't provide standard iCal feeds.

## Scraper Libraries (`lib/`)

Reusable base classes for common calendar platforms:

### `lib/elfsight.py` - Elfsight Event Calendar
For sites using the [Elfsight Event Calendar](https://elfsight.com/event-calendar-widget/) widget.

```python
from scrapers.lib.elfsight import ElfsightCalendarScraper


class MySiteScraper(ElfsightCalendarScraper):
    name = "My Site Events"
    domain = "mysite.com"
    widget_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # From page source
    source_page = "https://mysite.com/events"


if __name__ == "__main__":
    MySiteScraper.main()
```

To find the widget_id, inspect the page source and look for `elfsight-app-` or `eapps-event-calendar-` followed by a UUID.

CLI options: `--location`, `--type`, `--list-locations`, `--list-types`, `--months`

### `lib/cityspark.py` - CitySpark Calendars
For sites using CitySpark (e.g., Bohemian, Press Democrat).

### `lib/base.py` - Base Scraper
Abstract base class for all scrapers with common ICS generation.

## Scrapers

### sonoma_parks.py
Sonoma County Regional Parks calendar
- URL: https://parks.sonomacounty.ca.gov/play/calendar
- Events: Hikes, nature programs, volunteer workdays
- Method: HTML scraping (server-rendered calendar)

### redwood_cafe.py  
Redwood Cafe Cotati live music
- URL: https://redwoodcafecotati.com/events/
- Events: Live music performances
- Method: WordPress My Calendar plugin HTML scraping

### cal_theatre.py
California Theatre Santa Rosa
- URL: https://www.caltheatre.com/calendar  
- Events: Concerts, theater, comedy shows
- Method: Wix calendar widget HTML scraping
- Note: Works with static fetch; --use-selenium option available for JS rendering

### copperfields.py
Copperfield's Books (multiple locations)
- URL: https://copperfieldsbooks.com/upcoming-events
- Events: Author readings, book signings, kids events
- Locations: Petaluma, Sebastopol, Healdsburg, San Rafael, Napa, Calistoga, Montgomery Village
- Method: Drupal HTML scraping

### sportsbasement.py
Sports Basement Community Events (Bay Area chain)
- URL: https://shop.sportsbasement.com/pages/calendar
- Events: Run clubs, bike rides, fitness classes, ski events, community events
- Locations: Santa Rosa, Novato, Berkeley, Presidio, and 13 other Bay Area stores
- Method: Elfsight calendar widget API (uses `lib/elfsight.py`)

```bash
# List locations
python sportsbasement.py --list-locations

# Santa Rosa events
python sportsbasement.py --location "Santa Rosa" -o sportsbasement.ics

# Filter by event type
python sportsbasement.py --location "Santa Rosa" --type "Run Events"
```

### legistar.py
City/county government meetings via Legistar WebAPI
- Events: City council, planning boards, commissions
- Method: Legistar WebAPI (OData) → ICS conversion
- Uses subprocess+curl to avoid Python urllib encoding `$` as `%24`

```bash
# Discover: does the city have a working Legistar API?
curl -s "https://webapi.legistar.com/v1/{client}/events" | head -50

# Scrape
python scrapers/legistar.py --client santa-rosa --source "City of Santa Rosa" -o legistar.ics
python scrapers/legistar.py --client wake --source "Wake County" -o wake_legistar.ics
```

**Note:** Not all `{city}.legistar.com` web UIs have working APIs. Test first. See [AGENTS.md](../AGENTS.md) for the Granicus vs Legistar distinction.

### visit_bloomington.py
Visit Bloomington (Monroe County CVB) events via the Simpleview REST API
- URL: https://www.visitbloomington.com/events/
- Events: Festivals, film, concerts, museum and nature programs, community gatherings
- Method: Simpleview same-origin REST API (token + `skip` paging, desktop-Chrome UA, `Crawl-delay: 2`)
- Primary source, deliberately not an aggregator (see [ADR 0011](../docs/adr/0011-visit-bloomington-primary-source.md))

```bash
python scrapers/visit_bloomington.py --output cities/bloomington/visit_bloomington.ics
```

## Usage

Each scraper accepts `--year` and `--month` arguments and outputs an ICS file:

```bash
python3 sonoma_parks.py --year 2026 --month 2 --output sonoma_parks_2026_02.ics
python3 redwood_cafe.py --year 2026 --month 2 --output redwood_cafe_2026_02.ics
python3 cal_theatre.py --year 2026 --month 2 --output cal_theatre_2026_02.ics
python3 copperfields.py --year 2026 --month 2 --output copperfields_2026_02.ics
```

## Dependencies

- requests
- beautifulsoup4
- icalendar

Optional for cal_theatre.py with --use-selenium:
- selenium
- Chrome/Chromium browser

## Output Locations

- santarosa/: sonoma_parks, cal_theatre, copperfields
- cotati/: redwood_cafe
- sebastopol/: sebarts (existing), occidental_arts (existing)

## Notes

- Events for future months may be empty if the venue hasn't posted them yet
- Most venues post events 1-2 months in advance
- SebArts (sebastopol/sebarts.py) was already implemented in the project

## Adding a New Scraper to the Pipeline

Creating a scraper is not enough — you must also register it. Execution is
DB-first: the build runs whatever active scraper rows exist in the `feeds`
table, so `.github/workflows/generate-calendar.yml` carries no per-source
lines.

```bash
# After creating and testing your scraper:
python scripts/add_scraper.py myscraper bloomington "My Source Name"

# This automatically:
# - Tests the exact command being registered (aborts if it fails)
# - Appends the pending_feeds.txt entry the build inserts into the feeds table
```

There are no manual workflow or `combine_ics.py` edits. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for the full registration contract.

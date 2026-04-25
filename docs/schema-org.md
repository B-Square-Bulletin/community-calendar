# Schema.org Event Export

Export community calendar events as [schema.org](https://schema.org/)-compliant JSON-LD, suitable for embedding in HTML (`<script type="application/ld+json">`) or serving as structured data.

## Usage

```bash
# Single category
python scripts/schema_org_export.py --city toronto --category "Music / Concerts" --limit 10

# All categories for a city
python scripts/schema_org_export.py --city toronto --limit 50
```

## Schema.org type mapping

Our categories map to schema.org event subtypes where a match exists:

| Calendar category | schema.org type |
|---|---|
| Music / Concerts | [MusicEvent](https://schema.org/MusicEvent) |
| Dance / Performance | [DanceEvent](https://schema.org/DanceEvent) |
| Comedy / Improv | [ComedyEvent](https://schema.org/ComedyEvent) |
| Education / Workshops | [EducationEvent](https://schema.org/EducationEvent) |
| Food / Drink | [FoodEvent](https://schema.org/FoodEvent) |
| Sports / Fitness | [SportsEvent](https://schema.org/SportsEvent) |
| Film / Cinema | [ScreeningEvent](https://schema.org/ScreeningEvent) |
| Books / Literature / Poetry | [LiteraryEvent](https://schema.org/LiteraryEvent) |
| *(everything else)* | [Event](https://schema.org/Event) |

## Fields emitted per event

| schema.org property | Source |
|---|---|
| `name` | `title` |
| `startDate` | `start_time` (ISO 8601) |
| `endDate` | `end_time` (ISO 8601, omitted if same as start) |
| `url` | `url` |
| `description` | `description` |
| `location` | Parsed from `location` into [Place](https://schema.org/Place) + [PostalAddress](https://schema.org/PostalAddress) |
| `image` | `image_url` |
| `sameAs` | All URLs from `source_urls` |
| `eventAttendanceMode` | `OfflineEventAttendanceMode` |

Events are wrapped in an [ItemList](https://schema.org/ItemList).

## Example output

Toronto Music / Concerts (3 events):

```json
{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "name": "Community Calendar: Toronto — Music / Concerts",
  "numberOfItems": 3,
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "item": {
        "@type": "MusicEvent",
        "name": "Luna Luna w/ Vale",
        "startDate": "2026-04-21T00:00:00+00:00",
        "url": "https://tockify.com/torevent/detail/15345/1776729600000",
        "endDate": "2026-04-21T02:00:00+00:00",
        "description": "Doors 7pm/19+",
        "location": {
          "@type": "Place",
          "name": "Drake Underground",
          "address": {
            "@type": "PostalAddress",
            "streetAddress": "1150 Queen St W, Toronto, ON M6J 1J3, Canada"
          }
        },
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode"
      }
    },
    {
      "@type": "ListItem",
      "position": 2,
      "item": {
        "@type": "MusicEvent",
        "name": "MORE NOISE PLEASE! PRESENTS: MONDAY NIGHT MADNESS ON 4-20!",
        "startDate": "2026-04-21T00:00:00+00:00",
        "url": "https://tockify.com/torevent/detail/15965/1776729600000",
        "endDate": "2026-04-21T03:30:00+00:00",
        "location": {
          "@type": "Place",
          "name": "BSMT254",
          "address": {
            "@type": "PostalAddress",
            "streetAddress": "254 Lansdowne Ave, Toronto, ON M6H 3X9, Canada"
          }
        },
        "image": "https://d3flpus5evl89n.cloudfront.net/6755f3e6a02aaf1c2599e757/69c49204701bd67bec166fff/scaled_1024.jpg",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode"
      }
    },
    {
      "@type": "ListItem",
      "position": 3,
      "item": {
        "@type": "MusicEvent",
        "name": "Trip Hop Radio Live w/ Gruve Collective",
        "startDate": "2026-04-21T00:00:00+00:00",
        "url": "https://tockify.com/torevent/detail/15959/1776729600000",
        "endDate": "2026-04-21T06:00:00+00:00",
        "location": {
          "@type": "Place",
          "name": "Handlebar",
          "address": {
            "@type": "PostalAddress",
            "streetAddress": "159 Augusta Ave, Toronto, ON M5T 2L4, Canada"
          }
        },
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode"
      }
    }
  ]
}
```

## Validation

Paste the JSON-LD output into [Google's Rich Results Test](https://search.google.com/test/rich-results) or the [Schema.org Validator](https://validator.schema.org/) to verify compliance.

# Test Fixtures

This directory contains minimal ICS fixtures for the timezone pipeline, a
production-scale JSON fixture for the confidence route, and the client-side
card-membership fixtures for #169 (the view-shaped payload and the enrichment
fold).

## Purpose

The per-city ICS fixtures test the timezone handling pipeline
(`ics_to_json.py`, `combine_ics.py`) across different scenarios:
- Bare datetimes (no TZID)
- TZID matching city timezone
- Cross-timezone events (TZID differs from city)
- UTC events
- Recurring events (RRULE)

The `confidence_route/` fixture is different: it is a real production artifact
used to measure the route's blast radius, not a hand-written timezone case.

## Structure

```
fixtures/
├── santarosa/          # America/Los_Angeles
├── bloomington/        # America/Indiana/Indianapolis
├── montclair/          # America/New_York
├── toronto/            # America/Toronto
├── confidence_route/   # Full production artifact for blast-radius checks
├── enrichment_fold/    # Hand-built client enrichment fold -> group -> collapse
└── deduplicated_events_bloomington.json.gz  # Captured client view payload
```

## Fixtures by Scenario

### Bare Datetimes (No TZID)
- `santarosa/sonoma_parks.ics` - Events without TZID parameter

### Matching Timezone
- `santarosa/uptowntheatrenapa.ics` - TZID=America/Los_Angeles (matches city)

### Cross-Timezone Events
- `santarosa/eventbrite_phoenix.ics` - TZID=US/Eastern (in Pacific city)
- `bloomington/mobilize_indivisible_central_indiana.ics` - TZID=America/Los_Angeles (in Indiana)
- `bloomington/gcal_bloomington_in_gov_c657mi332p5sjpq2lcht9imu60.ics` - TZID=America/New_York
- `montclair/eventbrite_montclair_book_center.ics` - TZID=America/Los_Angeles (in Eastern city)
- `toronto/indigenous.ics` - TZID=America/Halifax (in Toronto)

### UTC Events
- `toronto/uoft_engineering.ics` - Events in UTC (Z suffix)

### Recurring Events (RRULE)
- `santarosa/new_world_ballet.ics` - RRULE with TZID preservation

### Confidence Route Blast Radius
- `confidence_route/bloomington_production_events.json.gz` - The complete
  Bloomington production `events.json` (8,545 listings), projected to the
  fields the confidence route reads (`title`, `start_time`, `location`,
  `source_uid`, `source`, `source_urls`, `url`, `all_day`) and gzipped. This is
  a full-size artifact, not a minimal fixture: it exists so
  `tests/test_confidence_route.py::TestBlastRadius` can measure the real merge
  and group counts and assert that no group grows past the observed maximum
  (a chain or all-day explosion fails loudly). Regenerate it from a fresh
  `cities/bloomington/events.json` by keeping only those eight fields per
  event.

### Client Card Membership (#169)

These two fixtures pin the client's card-membership refactor (#170/#171). They
are the client's *real input shape*, not the build-time artifact.

- **`deduplicated_events_bloomington.json.gz`** — a captured production
  `deduplicated_events` payload: exactly what the browser shell receives, one
  row per stored group, carrying `merged_ids`, `duplicate_group`, `source_names`,
  and `source_urls`. The plain-path output-equivalence check replays this through
  the new `Card` module and asserts the result matches the pre-refactor output.
  Captured once with the public anon key and the shell's exact select and 31-day
  horizon (no JWT required):

  ```bash
  curl -sS \
    "https://qatykxdvbpojxnvpicyi.supabase.co/rest/v1/deduplicated_events?select=id,title,start_time,end_time,url,location,description,source,source_names,transcript,source_urls,category,image_url,all_day,merged_ids,duplicate_group,city&order=start_time.asc&limit=6000&start_time=gte.<FROM>&start_time=lte.<TO>&city=eq.bloomington" \
    -H "apikey: sb_publishable_xXwJNayt4zT37TqqvMUD2g_BLeAUdfW" \
    --compressed | gzip -c > tests/fixtures/deduplicated_events_bloomington.json.gz
  ```

- **`enrichment_fold/bloomington_enrichment_fold.json`** — hand-built. One
  stored Group with a curator enrichment (an original occurrence that folds onto
  the Group's card, plus future occurrences that stay their own virtual,
  unpickable cards) and five stored Separate rows of one daily exhibition inside
  a single week, so the five-occurrence minimum is met exactly. It pins the
  single-pass fold → group → collapse output, including a `now` clock for the
  weekly anchor. The `expected` block records the load-bearing outcome
  semantics; #171's tests assert those, not a byte-for-byte row golden.

## Maintenance

### Adding New Fixtures

1. Create minimal ICS file with 2-3 events
2. Include VTIMEZONE block if using TZID
3. Use future dates (2026+) to avoid expiration
4. Add test in `tests/test_timezone_pipeline.py`

### Minimal ICS Template

```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test Fixture//Test//EN
BEGIN:VEVENT
UID:test-unique-id
DTSTART:20260615T100000
DTEND:20260615T110000
SUMMARY:Test Event
END:VEVENT
END:VCALENDAR
```

### With TZID

Include VTIMEZONE block before VEVENT and use TZID parameter:

```ics
DTSTART;TZID=America/Los_Angeles:20260615T100000
```

## Testing

```bash
# Run all timezone tests
python -m pytest tests/test_timezone_pipeline.py -v

# Run only fixture tests
python -m pytest tests/test_timezone_pipeline.py::TestRealIcsFiles -v
```

## Related

- Tests: `tests/test_timezone_pipeline.py`, `tests/test_confidence_route.py`
- Pipeline: `scripts/ics_to_json.py`, `scripts/combine_ics.py`
- Issue #14: Missing test fixtures

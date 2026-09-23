# Test Fixtures

This directory contains minimal ICS fixtures for the timezone pipeline plus a
production-scale JSON fixture for the confidence route.

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
└── confidence_route/   # Full production artifact for blast-radius checks
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

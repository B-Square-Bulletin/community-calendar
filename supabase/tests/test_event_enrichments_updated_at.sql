-- event_enrichments.updated_at is content-sensitive (#282): the my-picks feed
-- merges it into LAST-MODIFIED, so a curator edit to a feed-rendered field
-- must advance it. The pick editor re-upserts every column without
-- updated_at, so the database, not the client, owns the value.
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(11);

-- ============================================================================
-- Shape
-- ============================================================================
SELECT has_column(
    'public', 'event_enrichments', 'updated_at',
    'event_enrichments.updated_at exists'
);
SELECT col_has_default(
    'public', 'event_enrichments', 'updated_at',
    'event_enrichments.updated_at defaults to now()'
);
SELECT has_trigger(
    'public', 'event_enrichments', 'event_enrichments_touch_updated_at',
    'the update trigger advances the modification time'
);

-- ============================================================================
-- Seed one row per feed-rendered field, pinned to an old timestamp
-- ============================================================================
INSERT INTO event_enrichments (
    title, rrule, categories, notes, description, location,
    url, start_time, end_time, city, curator_name, updated_at
)
SELECT
    'seed-' || f,
    'FREQ=WEEKLY', ARRAY['Music'], 'Old notes', 'Old description', 'Old Hall',
    'http://old.example', '2031-01-01T18:00:00Z', '2031-01-01T20:00:00Z',
    'test_enrichment_updated_at', 'Old Curator', '2000-01-01T00:00:00Z'
FROM unnest(ARRAY[
    'rrule', 'categories', 'notes', 'description', 'location'
]) AS f;

-- ============================================================================
-- Every feed-rendered column advances the timestamp
-- ============================================================================
UPDATE event_enrichments SET rrule = 'FREQ=MONTHLY' WHERE title = 'seed-rrule';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM event_enrichments WHERE title = 'seed-rrule'),
    'an rrule change advances updated_at'
);

UPDATE event_enrichments
SET categories = ARRAY['Theater']
WHERE title = 'seed-categories';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM event_enrichments WHERE title = 'seed-categories'),
    'a categories change advances updated_at'
);

UPDATE event_enrichments SET notes = 'New notes' WHERE title = 'seed-notes';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM event_enrichments WHERE title = 'seed-notes'),
    'a notes change advances updated_at'
);

UPDATE event_enrichments
SET description = 'New description'
WHERE title = 'seed-description';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM event_enrichments WHERE title = 'seed-description'),
    'a description change advances updated_at'
);

UPDATE event_enrichments SET location = 'New Hall' WHERE title = 'seed-location';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM event_enrichments WHERE title = 'seed-location'),
    'a location change advances updated_at'
);

-- ============================================================================
-- An identical re-upsert does not move it
-- ============================================================================
-- Same shape as the pick editor's upsert: on_conflict=event_id,curator_id,
-- resolution=merge-duplicates, rewriting every column (stricter than the
-- editor's payload) and no updated_at.
INSERT INTO auth.users (id, instance_id, aud, role, email)
VALUES (
    '22222222-2222-2222-2222-222222222222',
    '00000000-0000-0000-0000-000000000000',
    'authenticated', 'authenticated', 'enrichment@example.invalid'
);

INSERT INTO events (city, title, start_time, source_uid)
VALUES ('test_enrichment_updated_at', 'Event', '2031-01-01T18:00:00Z', 'teua-event');

INSERT INTO event_enrichments (
    event_id, curator_id, title, rrule, categories, notes, description,
    location, url, start_time, end_time, city, curator_name, updated_at
)
SELECT
    id, '22222222-2222-2222-2222-222222222222', 'seed-noop', 'FREQ=WEEKLY',
    ARRAY['Music'], 'Old notes', 'Old description', 'Old Hall',
    'http://old.example', '2031-01-01T18:00:00Z', '2031-01-01T20:00:00Z',
    'test_enrichment_updated_at', 'Old Curator', '2000-01-01T00:00:00Z'
FROM events WHERE source_uid = 'teua-event';

INSERT INTO event_enrichments (
    event_id, curator_id, title, rrule, categories, notes, description,
    location, url, start_time, end_time, city, curator_name
)
SELECT
    id, '22222222-2222-2222-2222-222222222222', 'seed-noop', 'FREQ=WEEKLY',
    ARRAY['Music'], 'Old notes', 'Old description', 'Old Hall',
    'http://old.example', '2031-01-01T18:00:00Z', '2031-01-01T20:00:00Z',
    'test_enrichment_updated_at', 'Old Curator'
FROM events WHERE source_uid = 'teua-event'
ON CONFLICT (event_id, curator_id) DO UPDATE SET
    title = EXCLUDED.title,
    rrule = EXCLUDED.rrule,
    categories = EXCLUDED.categories,
    notes = EXCLUDED.notes,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    url = EXCLUDED.url,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    city = EXCLUDED.city,
    curator_name = EXCLUDED.curator_name;

SELECT is(
    (SELECT updated_at FROM event_enrichments
     WHERE curator_id = '22222222-2222-2222-2222-222222222222'),
    '2000-01-01T00:00:00Z'::timestamptz,
    'an identical upsert leaves updated_at unchanged'
);

-- The database owns the column: a payload that names updated_at cannot set it.
UPDATE event_enrichments
SET updated_at = '2031-06-01T00:00:00Z'
WHERE curator_id = '22222222-2222-2222-2222-222222222222';

SELECT is(
    (SELECT updated_at FROM event_enrichments
     WHERE curator_id = '22222222-2222-2222-2222-222222222222'),
    '2000-01-01T00:00:00Z'::timestamptz,
    'a client-supplied updated_at is discarded'
);

-- ============================================================================
-- Writes outside the feed-rendered set leave it alone
-- ============================================================================
UPDATE event_enrichments
SET title = 'Renamed',
    start_time = '2031-02-01T18:00:00Z',
    end_time = '2031-02-01T22:00:00Z',
    url = 'http://new.example',
    city = 'test_enrichment_updated_at_moved',
    curator_name = 'New Curator'
WHERE curator_id = '22222222-2222-2222-2222-222222222222';

SELECT is(
    (SELECT updated_at FROM event_enrichments
     WHERE curator_id = '22222222-2222-2222-2222-222222222222'),
    '2000-01-01T00:00:00Z'::timestamptz,
    'writes outside the feed-rendered columns leave updated_at unchanged'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

-- events.updated_at is content-sensitive (#266): a feed-relevant change moves
-- it, while an identical re-upsert or a non-content write leaves it alone.
--
-- The loader upserts every event on every build, so the database, not the
-- client, owns the value.
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(20);

-- ============================================================================
-- Shape
-- ============================================================================
SELECT has_column('public', 'events', 'updated_at', 'events.updated_at exists');
SELECT col_not_null('public', 'events', 'updated_at', 'events.updated_at is NOT NULL');
SELECT col_has_default('public', 'events', 'updated_at', 'events.updated_at defaults to now()');
SELECT has_column(
    'public', 'deduplicated_events', 'updated_at',
    'the read model exposes updated_at'
);

-- ============================================================================
-- Seed one row per feed-relevant field, pinned to an old timestamp
-- ============================================================================
INSERT INTO events (
    city, title, start_time, end_time, location, description, url, image_url,
    source, source_uid, updated_at
)
SELECT
    'test_updated_at', 'Original', '2031-01-01T18:00:00Z', '2031-01-01T20:00:00Z',
    'Old Hall', 'Old description', 'http://old.example', 'http://old.example/p.png',
    'Old Source', 'tua-' || f, '2000-01-01T00:00:00Z'
FROM unnest(ARRAY[
    'title', 'start_time', 'end_time', 'location', 'description', 'url',
    'image_url', 'city', 'source', 'noop'
]) AS f;

-- A two-member duplicate group whose members changed at different times.
INSERT INTO events (
    city, title, start_time, source, source_uid,
    duplicate_group, duplicate_group_representative, updated_at
)
VALUES
    (
        'test_updated_at', 'Grouped', '2031-03-01T18:00:00Z', 'Old Source',
        'tua-group-rep', 'tua-group', 'tua-group-rep', '2000-01-01T00:00:00Z'
    ),
    (
        'test_updated_at', 'Grouped (member)', '2031-03-01T18:00:00Z', 'Member Source',
        'tua-group-member', 'tua-group', 'tua-group-rep', '2001-01-01T00:00:00Z'
    );

-- ============================================================================
-- Every feed-relevant column advances the timestamp
-- ============================================================================
UPDATE events SET title = 'Changed' WHERE source_uid = 'tua-title';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-title'),
    'a title change advances updated_at'
);

UPDATE events SET start_time = '2031-02-01T18:00:00Z' WHERE source_uid = 'tua-start_time';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-start_time'),
    'a start_time change advances updated_at'
);

UPDATE events SET end_time = '2031-02-01T22:00:00Z' WHERE source_uid = 'tua-end_time';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-end_time'),
    'an end_time change advances updated_at'
);

UPDATE events SET location = 'New Hall' WHERE source_uid = 'tua-location';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-location'),
    'a location change advances updated_at'
);

UPDATE events SET description = 'New description' WHERE source_uid = 'tua-description';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-description'),
    'a description change advances updated_at'
);

UPDATE events SET url = 'http://new.example' WHERE source_uid = 'tua-url';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-url'),
    'a url change advances updated_at'
);

UPDATE events SET image_url = 'http://new.example/p.png' WHERE source_uid = 'tua-image_url';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-image_url'),
    'an image_url change advances updated_at'
);

UPDATE events SET city = 'test_updated_at_moved' WHERE source_uid = 'tua-city';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-city'),
    'a city change advances updated_at'
);

UPDATE events SET source = 'New Source' WHERE source_uid = 'tua-source';
SELECT ok(
    (SELECT updated_at > '2000-01-01T00:00:00Z'::timestamptz
     FROM events WHERE source_uid = 'tua-source'),
    'a source change advances updated_at'
);

-- ============================================================================
-- A no-op write does not move it
-- ============================================================================
-- Same shape as the loader's upsert: every content column is rewritten with
-- byte-identical values, and updated_at is not in the payload.
INSERT INTO events (
    city, title, start_time, end_time, location, description, url, image_url, source, source_uid
)
VALUES (
    'test_updated_at', 'Original', '2031-01-01T18:00:00Z', '2031-01-01T20:00:00Z',
    'Old Hall', 'Old description', 'http://old.example', 'http://old.example/p.png',
    'Old Source', 'tua-noop'
)
ON CONFLICT (source_uid) DO UPDATE SET
    city = EXCLUDED.city,
    title = EXCLUDED.title,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    location = EXCLUDED.location,
    description = EXCLUDED.description,
    url = EXCLUDED.url,
    image_url = EXCLUDED.image_url,
    source = EXCLUDED.source;

SELECT is(
    (SELECT updated_at FROM events WHERE source_uid = 'tua-noop'),
    '2000-01-01T00:00:00Z'::timestamptz,
    'an identical upsert leaves updated_at unchanged'
);

UPDATE events
SET category = 'Other', transcript = 'transcript', all_day = true,
    source_urls = '{"Old Source":"http://old.example"}'::jsonb,
    duplicate_group = 'tua-ignored', duplicate_group_representative = 'tua-noop'
WHERE source_uid = 'tua-noop';

SELECT is(
    (SELECT updated_at FROM events WHERE source_uid = 'tua-noop'),
    '2000-01-01T00:00:00Z'::timestamptz,
    'writes outside the feed-content columns leave updated_at unchanged'
);

-- The database owns the column: a payload that names updated_at cannot set it.
UPDATE events
SET title = title, updated_at = '2031-06-01T00:00:00Z'
WHERE source_uid = 'tua-noop';

SELECT is(
    (SELECT updated_at FROM events WHERE source_uid = 'tua-noop'),
    '2000-01-01T00:00:00Z'::timestamptz,
    'a client-supplied updated_at is discarded'
);

-- ============================================================================
-- The read model carries the same value and still refreshes
-- ============================================================================
SELECT lives_ok(
    'REFRESH MATERIALIZED VIEW deduplicated_events',
    'deduplicated_events still refreshes'
);

SELECT is(
    (SELECT updated_at FROM deduplicated_events WHERE source_uid = 'tua-title'),
    (SELECT updated_at FROM events WHERE source_uid = 'tua-title'),
    'the read model exposes the event modification time'
);

SELECT is(
    (SELECT updated_at FROM deduplicated_events WHERE duplicate_group = 'tua-group'),
    '2001-01-01T00:00:00Z'::timestamptz,
    'a group reports its latest member modification'
);

SELECT has_function(
    'public', 'refresh_deduplicated_events',
    'refresh_deduplicated_events survives the view recreation'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

-- Test suite for route persistence and the authoritative deduplicated view (#152).
--
-- The route persists duplicate_group (opaque group id), source_names
-- (structured, route-ordered names), and duplicate_group_representative (the
-- route's canonical member). The materialized view must collapse each stored
-- group to one row, isolate every NULL group as its own row, and aggregate
-- member ids, structured source names, and source URLs without re-splitting
-- ambiguous comma-joined text.
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(23);

-- ============================================================================
-- Storage columns exist (migration contract)
-- ============================================================================
SELECT has_column('public', 'events', 'duplicate_group', 'events.duplicate_group exists');
SELECT has_column('public', 'events', 'source_names', 'events.source_names exists');
SELECT has_column(
    'public', 'events', 'duplicate_group_representative',
    'events.duplicate_group_representative exists'
);
SELECT has_column('public', 'deduplicated_events', 'duplicate_group', 'view exposes duplicate_group');
SELECT has_column('public', 'deduplicated_events', 'source_names', 'view exposes source_names');
SELECT has_column(
    'public', 'deduplicated_events', 'duplicate_group_representative',
    'view exposes the representative'
);
SELECT has_column('public', 'deduplicated_events', 'merged_ids', 'view exposes merged_ids');

-- ============================================================================
-- Seed
-- ============================================================================
-- A stored Group: a primary representative and a suppressed-in-presentation
-- aggregator member at the same instant.
INSERT INTO events (
    city, title, start_time, source, source_uid, url,
    duplicate_group, duplicate_group_representative, source_names, source_urls
)
VALUES
    (
        'test_dedup', 'Grouped Event', '2030-01-01T18:00:00+00:00', 'Primary Venue',
        'tdd-g1-primary', 'http://primary', 'cr1-group1', 'tdd-g1-primary',
        ARRAY['Primary Venue'], '{"Primary Venue":"http://primary"}'::jsonb
    ),
    (
        'test_dedup', 'Grouped Event (Aggregator)', '2030-01-01T18:00:00+00:00', 'Aggregator X',
        'tdd-g1-agg', 'http://agg', 'cr1-group1', 'tdd-g1-primary',
        ARRAY['Aggregator X'], '{"Aggregator X":"http://agg"}'::jsonb
    );

-- Rank and position must come from the same occurrence. Alpha is second on
-- the representative and first on the member, so it must remain after Zeta.
INSERT INTO events (
    city, title, start_time, source, source_uid,
    duplicate_group, duplicate_group_representative, source_names
)
VALUES
    (
        'test_dedup', 'Ordered Sources', '2030-01-04T18:00:00+00:00', 'Zeta, Alpha',
        'tdd-g2-primary', 'cr1-ordering', 'tdd-g2-primary', ARRAY['Zeta', 'Alpha']
    ),
    (
        'test_dedup', 'Ordered Sources (member)', '2030-01-04T18:00:00+00:00', 'Alpha',
        'tdd-g2-member', 'cr1-ordering', 'tdd-g2-primary', ARRAY['Alpha']
    );

-- Two Separate rows sharing a title and instant must stay two rows: a NULL
-- group is one row is one group, never collapsed by a title fallback.
INSERT INTO events (city, title, start_time, source, source_uid, duplicate_group, source_names)
VALUES
    ('test_dedup', 'Same Title', '2030-01-02T18:00:00+00:00', 'Source A', 'tdd-s1', NULL, ARRAY['Source A']),
    ('test_dedup', 'Same Title', '2030-01-02T18:00:00+00:00', 'Source B', 'tdd-s2', NULL, ARRAY['Source B']);

-- A source name that contains a comma must survive as one opaque name.
INSERT INTO events (city, title, start_time, source, source_uid, duplicate_group, source_names)
VALUES ('test_dedup', 'Taste Event', '2030-01-03T18:00:00+00:00', 'Taste, Inc.', 'tdd-comma', NULL, ARRAY['Taste, Inc.']);

REFRESH MATERIALIZED VIEW deduplicated_events;

-- ============================================================================
-- The stored Group renders once with every member intact
-- ============================================================================
SELECT is(
    (SELECT count(*)::int FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    1,
    'A stored Group collapses to exactly one row'
);

SELECT is(
    (SELECT cardinality(merged_ids) FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    2,
    'The group row keeps both member ids in merged_ids'
);

SELECT is(
    (SELECT id FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    (SELECT id FROM events WHERE source_uid = 'tdd-g1-primary'),
    'The view id is the route representative, not a database-assigned min(id)'
);

SELECT is(
    (SELECT title FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    'Grouped Event',
    'The representative title is presented'
);

SELECT is(
    (SELECT source_uid FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    'tdd-g1-primary',
    'The representative source_uid is presented'
);

SELECT is(
    (SELECT duplicate_group FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    'cr1-group1',
    'The stored group id is exposed for consumers'
);

SELECT is(
    (
        SELECT duplicate_group_representative FROM deduplicated_events
        WHERE duplicate_group = 'cr1-group1'
    ),
    'tdd-g1-primary',
    'The route representative is exposed for consumers'
);

SELECT is(
    (SELECT source FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    'Primary Venue, Aggregator X',
    'Grouped sources are unioned, representative first, without splitting'
);

SELECT is(
    (SELECT source_names FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    ARRAY['Primary Venue', 'Aggregator X'],
    'Grouped source names are aggregated as a structured, ordered array'
);

SELECT is(
    (SELECT source_names FROM deduplicated_events WHERE duplicate_group = 'cr1-ordering'),
    ARRAY['Zeta', 'Alpha'],
    'A member occurrence cannot promote a source ahead of the representative order'
);

SELECT is(
    (SELECT source_urls FROM deduplicated_events WHERE duplicate_group = 'cr1-group1'),
    '{"Primary Venue":"http://primary","Aggregator X":"http://agg"}'::jsonb,
    'Grouped source_urls are unioned deterministically'
);

-- ============================================================================
-- Separate stays separate; NULL is never collapsed with NULL
-- ============================================================================
SELECT is(
    (SELECT count(*)::int FROM deduplicated_events WHERE city = 'test_dedup' AND duplicate_group IS NULL),
    3,
    'NULL-group rows stay isolated (two same-title rows plus the comma row)'
);

SELECT is(
    (
        SELECT count(*)::int FROM deduplicated_events
        WHERE title = 'Same Title' AND city = 'test_dedup'
    ),
    2,
    'Identical-title Separate rows are not re-collapsed by a title fallback'
);

SELECT ok(
    (
        SELECT bool_and(duplicate_group IS NULL AND cardinality(merged_ids) = 1)
        FROM deduplicated_events
        WHERE source_uid IN ('tdd-s1', 'tdd-s2')
    ),
    'Each Separate row is its own group with a single-member merged_ids'
);

SELECT is(
    (
        SELECT source FROM deduplicated_events
        WHERE source_uid = 'tdd-comma'
    ),
    'Taste, Inc.',
    'A source name containing a comma is not split into two names'
);

SELECT is(
    (
        SELECT source_names FROM deduplicated_events
        WHERE source_uid = 'tdd-comma'
    ),
    ARRAY['Taste, Inc.'],
    'A comma-bearing source name stays one structured name'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

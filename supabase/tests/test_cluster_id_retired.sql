-- Test suite for the #155 cluster_id cleanup migration.
--
-- `cluster_id` was the legacy per-timeslot similarity index produced by
-- `cluster_by_title_similarity`. Every consumer now reads the route's stored
-- `duplicate_group`, so the cleanup migration drops the column and recreates
-- the authoritative view without it. This is the *separately verified* half of
-- the transition: it fails if the dead column or view field is ever
-- reintroduced, and it proves the view still collapses a stored Group once the
-- column is gone (the view must not depend on retired behavior).
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(4);

-- ============================================================================
-- The dead column is gone from storage and from the read model
-- ============================================================================
SELECT hasnt_column('public', 'events', 'cluster_id', 'events.cluster_id is dropped');
SELECT hasnt_column(
    'public', 'deduplicated_events', 'cluster_id',
    'the view no longer exposes cluster_id'
);

-- ============================================================================
-- The view still works without the retired column
-- ============================================================================
INSERT INTO events (
    city, title, start_time, source, source_uid, url,
    duplicate_group, duplicate_group_representative, source_names
)
VALUES
    (
        'test_cluster_retire', 'Retired', '2031-01-01T18:00:00+00:00', 'Source A',
        'tcr-a', 'http://a', 'cr1-retire', 'tcr-a', ARRAY['Source A']
    ),
    (
        'test_cluster_retire', 'Retired', '2031-01-01T18:00:00+00:00', 'Source B',
        'tcr-b', 'http://b', 'cr1-retire', 'tcr-a', ARRAY['Source B']
    );

REFRESH MATERIALIZED VIEW deduplicated_events;

SELECT is(
    (SELECT count(*)::int FROM deduplicated_events WHERE duplicate_group = 'cr1-retire'),
    1,
    'the view still collapses a stored Group after cluster_id is dropped'
);

SELECT is(
    (SELECT source FROM deduplicated_events WHERE duplicate_group = 'cr1-retire'),
    'Source A, Source B',
    'the view still unions member sources after cluster_id is dropped'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

-- Test suite for the #155 cluster_id compatibility window.
--
-- `cluster_id` remains readable for one compatibility build while every active
-- consumer uses the route's stored `duplicate_group`. A later, separately
-- verified cleanup migration can remove it after that build.
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(4);

-- ============================================================================
-- The compatibility field remains available in storage and the read model
-- ============================================================================
SELECT has_column('public', 'events', 'cluster_id', 'events.cluster_id remains for compatibility');
SELECT has_column(
    'public', 'deduplicated_events', 'cluster_id',
    'the view exposes cluster_id during compatibility'
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
    'the view still collapses a stored Group during compatibility'
);

SELECT is(
    (SELECT source FROM deduplicated_events WHERE duplicate_group = 'cr1-retire'),
    'Source A, Source B',
    'the view still unions member sources during compatibility'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

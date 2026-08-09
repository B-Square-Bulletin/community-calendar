-- Test suite for feed_health and feed_anomalies tables + related RPCs.
-- Tests the migration that adds 'curator' to the feed_health.feed_type
-- CHECK constraint, plus unique constraint behavior and prune RPCs.
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(14);

-- ============================================================================
-- Test 1: feed_health allows feed_type='ics_url'
-- ============================================================================
INSERT INTO feed_health (city, feed_name, feed_type, event_count, checked_date)
VALUES ('test_fh', 'ics_feed', 'ics_url', 5, current_date);

SELECT is(
    (
        SELECT count(*)::int FROM feed_health
        WHERE city = 'test_fh' AND feed_name = 'ics_feed'
    ),
    1,
    'Test 1: INSERT with feed_type=ics_url succeeds'
);

-- ============================================================================
-- Test 2: feed_health allows feed_type='scraper'
-- ============================================================================
INSERT INTO feed_health (city, feed_name, feed_type, event_count, checked_date)
VALUES ('test_fh', 'scraper_feed', 'scraper', 10, current_date);

SELECT is(
    (
        SELECT count(*)::int FROM feed_health
        WHERE city = 'test_fh' AND feed_name = 'scraper_feed'
    ),
    1,
    'Test 2: INSERT with feed_type=scraper succeeds'
);

-- ============================================================================
-- Test 3: feed_health allows feed_type='curator' (migration fix)
-- ============================================================================
INSERT INTO feed_health (city, feed_name, feed_type, event_count, checked_date)
VALUES ('test_fh', 'curator_feed', 'curator', 3, current_date);

SELECT is(
    (
        SELECT count(*)::int FROM feed_health
        WHERE city = 'test_fh' AND feed_name = 'curator_feed'
    ),
    1,
    'Test 3: INSERT with feed_type=curator succeeds (migration fix)'
);

-- ============================================================================
-- Test 4: feed_health rejects unknown feed_type
-- ============================================================================
SELECT throws_ok(
    $$INSERT INTO feed_health (city, feed_name, feed_type, event_count,
        checked_date)
      VALUES ('test_fh', 'bad_feed', 'unknown', 1, current_date)$$,
    '23514',
    NULL,
    'Test 4: INSERT with feed_type=unknown raises check_violation'
);

-- ============================================================================
-- Test 5: Unique constraint on (city, feed_name, checked_date)
-- ============================================================================
INSERT INTO feed_health (city, feed_name, feed_type, event_count, checked_date)
VALUES ('test_fh', 'unique_test', 'ics_url', 7, current_date);

SELECT throws_ok(
    $$INSERT INTO feed_health (city, feed_name, feed_type, event_count,
        checked_date)
      VALUES ('test_fh', 'unique_test', 'scraper', 99, current_date)$$,
    '23505',
    NULL,
    'Test 5: Duplicate (city, feed_name, checked_date) raises unique_violation'
);

-- ============================================================================
-- Test 6: feed_health schema columns are correct
-- ============================================================================
SELECT columns_are(
    'feed_health',
    ARRAY[
        'id', 'city', 'feed_name', 'source_name', 'source_url',
        'feed_type', 'scraper_cmd', 'event_count', 'error',
        'checked_at', 'checked_date'
    ],
    'Test 6: feed_health has expected columns'
);

-- ============================================================================
-- Test 7: feed_anomalies schema columns are correct
-- ============================================================================
SELECT columns_are(
    'feed_anomalies',
    ARRAY[
        'id', 'city', 'feed_name', 'anomaly_type', 'severity',
        'message', 'previous_count', 'current_count', 'detected_at'
    ],
    'Test 7: feed_anomalies has expected columns'
);

-- ============================================================================
-- Test 8: feed_anomalies severity CHECK constraint
-- ============================================================================
INSERT INTO feed_anomalies (city, feed_name, anomaly_type, severity, message)
VALUES ('test_fh', 'feed_a', 'zero_events', 'high', 'Zero events today');

SELECT is(
    (
        SELECT count(*)::int FROM feed_anomalies
        WHERE city = 'test_fh' AND severity = 'high'
    ),
    1,
    'Test 8: INSERT with severity=high succeeds'
);

SELECT throws_ok(
    $$INSERT INTO feed_anomalies (city, feed_name, anomaly_type, severity,
        message)
      VALUES ('test_fh', 'feed_b', 'test', 'critical', 'bad severity')$$,
    '23514',
    NULL,
    'Test 9: INSERT with severity=critical raises check_violation'
);

-- ============================================================================
-- Test 10: prune_feed_health deletes old rows, preserves recent
-- ============================================================================
-- Clean up rows from earlier tests (their dates are all current_date, but
-- the prune function operates per-city — we want a clean slate for counting)
DELETE FROM feed_health
WHERE city = 'test_fh';

-- Insert a recent row (today)
INSERT INTO feed_health (city, feed_name, feed_type, event_count, checked_date)
VALUES ('test_fh', 'prune_health_test', 'ics_url', 1, current_date);

-- Insert an old row (100 days ago)
INSERT INTO feed_health (city, feed_name, feed_type, event_count, checked_date)
VALUES (
    'test_fh', 'prune_health_old', 'ics_url', 1,
    (current_date - interval '100 days')::date
);

SELECT is(
    prune_feed_health('test_fh', 60),
    bigint '1',
    'Test 10: prune_feed_health(60 days) deletes 1 old row'
);

SELECT is(
    (
        SELECT count(*)::int FROM feed_health
        WHERE city = 'test_fh' AND feed_name = 'prune_health_test'
    ),
    1,
    'Test 10b: Recent row survives pruning'
);

SELECT is(
    (
        SELECT count(*)::int FROM feed_health
        WHERE city = 'test_fh' AND feed_name = 'prune_health_old'
    ),
    0,
    'Test 10c: Old row was pruned'
);

-- ============================================================================
-- Test 11: prune_feed_anomalies deletes old rows, preserves recent
-- ============================================================================
INSERT INTO feed_anomalies (city, feed_name, anomaly_type, severity, message)
VALUES ('test_fh', 'recent_anomaly', 'zero_events', 'medium', 'Recent');

INSERT INTO feed_anomalies (
    city, feed_name, anomaly_type, severity, message, detected_at
)
VALUES (
    'test_fh', 'old_anomaly', 'zero_events', 'low', 'Old',
    current_timestamp - interval '100 days'
);

SELECT is(
    prune_feed_anomalies('test_fh', 60),
    bigint '1',
    'Test 11: prune_feed_anomalies(60 days) deletes 1 old row'
);

SELECT is(
    (
        SELECT count(*)::int FROM feed_anomalies
        WHERE city = 'test_fh' AND feed_name = 'recent_anomaly'
    ),
    1,
    'Test 11b: Recent anomaly survives pruning'
);

-- ============================================================================
-- Cleanup
-- ============================================================================
DELETE FROM feed_anomalies
WHERE city = 'test_fh';

DELETE FROM feed_health
WHERE city = 'test_fh';

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

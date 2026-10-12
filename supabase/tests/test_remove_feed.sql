-- Test suite for remove_feed() (pgTAP)
-- Verifies a feed's events are deleted, including rows that a merge folded into
-- another source's survivor (20261011140000_remove_feed_match_source_names.sql).
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(3);

INSERT INTO feeds (city, url, name, status, feed_type)
VALUES ('test_rf', 'https://example.invalid/test_rf_a.ics', 'Feed A', 'active', 'ics_url');

INSERT INTO events (city, title, start_time, source, source_id, source_uid, source_names)
VALUES
('test_rf', 'Plain A', now(), 'Feed A', 'feed_a', 'uid-plain', ARRAY['Feed A']),
('test_rf', 'Merged survivor', now(), 'Feed A, Feed B', 'feed_a', 'uid-merged', ARRAY['Feed A', 'Feed B']),
('test_rf', 'Other B', now(), 'Feed B', 'feed_b', 'uid-other', ARRAY['Feed B']);

SELECT remove_feed((SELECT id FROM feeds WHERE city = 'test_rf' AND name = 'Feed A'));

SELECT is(
    (
        SELECT count(*)::int FROM events
        WHERE city = 'test_rf' AND source_uid IN ('uid-plain', 'uid-merged')
    ),
    0,
    'remove_feed deletes plain events and merge survivors of the feed'
);

SELECT is(
    (
        SELECT count(*)::int FROM events
        WHERE city = 'test_rf' AND source_uid = 'uid-other'
    ),
    1,
    'remove_feed leaves other sources untouched'
);

SELECT is(
    (
        SELECT count(*)::int FROM feeds
        WHERE city = 'test_rf'
    ),
    0,
    'remove_feed deletes the feed row'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

-- Test suite for remove_feed() (pgTAP)
-- remove_feed deletes the rows a feed owns: rows whose source_id is one the
-- feed has produced (feeds.source_ids), plus rows whose source is exactly the
-- feed's name (rows built before the feed-to-source_id mapping existed). A
-- merge survivor carries the comma-joined member names, so source_id is the
-- only way to tell which feed owns it (ADR 0017).
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(6);

INSERT INTO feeds (city, url, name, status, feed_type, source_ids)
VALUES
('test_rf', 'https://example.invalid/test_rf_a.ics', 'Feed A', 'active', 'ics_url', ARRAY['feed_a']),
('test_rf', 'https://example.invalid/test_rf_b.ics', 'Feed B', 'active', 'ics_url', ARRAY['feed_b']),
('test_rf', 'https://example.invalid/test_rf_c.ics', 'Feed C', 'active', 'ics_url', ARRAY[]::text[]);

INSERT INTO events (city, title, start_time, source, source_id, source_uid, source_names)
VALUES
('test_rf', 'Survivor owned by A', now(), 'Feed A, Feed B', 'feed_a', 'uid-a-owns', ARRAY['Feed A', 'Feed B']),
('test_rf', 'Survivor owned by B', now(), 'Feed A, Feed B', 'feed_b', 'uid-b-owns', ARRAY['Feed A', 'Feed B']),
('test_rf', 'Feed B only', now(), 'Feed B', 'feed_b', 'uid-b-only', ARRAY['Feed B']),
('test_rf', 'Legacy Feed C row', now(), 'Feed C', 'legacy_c_stem', 'uid-c-legacy', ARRAY['Feed C']);

INSERT INTO auth.users (id, instance_id, aud, role, email)
VALUES (
    '00000000-0000-0000-0000-000000000232',
    '00000000-0000-0000-0000-000000000000',
    'authenticated', 'authenticated', 'pgtap@example.invalid'
);

INSERT INTO picks (user_id, event_id)
VALUES
('00000000-0000-0000-0000-000000000232', (SELECT id FROM events WHERE source_uid = 'uid-a-owns')),
('00000000-0000-0000-0000-000000000232', (SELECT id FROM events WHERE source_uid = 'uid-b-owns'));

-- Remove Feed A: the survivor it won must go; Feed B's survivor must stay.
SELECT remove_feed((SELECT id FROM feeds WHERE city = 'test_rf' AND name = 'Feed A'));

SELECT is(
    (
        SELECT count(*)::int FROM events
        WHERE city = 'test_rf' AND source_uid = 'uid-a-owns'
    ),
    0,
    'a merged survivor the feed owns is deleted'
);

SELECT is(
    (
        SELECT count(*)::int FROM events
        WHERE city = 'test_rf' AND source_uid = 'uid-b-owns'
    ),
    1,
    'a merged survivor owned by another feed is untouched'
);

SELECT is(
    (
        SELECT count(*)::int FROM events
        WHERE city = 'test_rf' AND source_uid = 'uid-b-only'
    ),
    1,
    'rows owned only by another feed are untouched'
);

SELECT is(
    (
        SELECT count(*)::int FROM picks
        WHERE user_id = '00000000-0000-0000-0000-000000000232'
    ),
    1,
    'the other feed''s saved pick survives and the retired event''s pick is gone'
);

-- Feed C has no recorded source_id: the name fallback still clears its rows.
SELECT remove_feed((SELECT id FROM feeds WHERE city = 'test_rf' AND name = 'Feed C'));

SELECT is(
    (
        SELECT count(*)::int FROM events
        WHERE city = 'test_rf' AND source_uid = 'uid-c-legacy'
    ),
    0,
    'a feed without source_ids still deletes its rows by name'
);

SELECT is(
    (
        SELECT count(*)::int FROM feeds
        WHERE city = 'test_rf'
    ),
    1,
    'each removal deletes only its own feed row'
);

SELECT * FROM finish();  -- noqa: AM04
ROLLBACK;

-- Test suite for the curator-feed capability constraints (pgTAP)
-- A picks feed's ?token= is its only credential, and feeds.url is world-readable
-- and re-exported to cities/<city>/feeds.txt (GHSA-3pg8-w4j4-6wv8). Curator
-- rows name the curator instead; download_feeds mints the URL from feed_tokens.
--
-- Run: supabase test db supabase/tests/
-- Or:  make test-sql

BEGIN;
SELECT plan(4);

-- A capability URL may not be stored, whichever feed_type claims it.
SELECT throws_ok(
    $$ INSERT INTO feeds (city, url, name, status, feed_type)
       VALUES ('test_cur', 'https://ref.supabase.co/functions/v1/my-picks?token=abc', 'Leak', 'active', 'ics_url') $$,
    '23514',
    NULL,
    'rejects a my-picks URL as an ics_url'
);

SELECT throws_ok(
    $$ INSERT INTO feeds (city, url, name, status, feed_type, curator_user_id)
       VALUES ('test_cur', 'https://ref.supabase.co/functions/v1/my-picks?token=abc', 'Leak', 'active', 'curator', gen_random_uuid()) $$,
    '23514',
    NULL,
    'rejects a my-picks URL as a curator row too'
);

-- curator_user_id and feed_type are two halves of one fact.
SELECT throws_ok(
    $$ INSERT INTO feeds (city, url, name, status, feed_type)
       VALUES ('test_cur', 'curator://no-user', 'Untied', 'active', 'curator') $$,
    '23514',
    NULL,
    'rejects a curator row with no curator_user_id'
);

-- A resolved curator row stores only the curator reference.
INSERT INTO auth.users (id, instance_id, aud, role, email)
VALUES ('11111111-1111-1111-1111-111111111111', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'curator@example.invalid');

SELECT lives_ok(
    $$ INSERT INTO feeds (city, url, name, status, feed_type, curator_user_id)
       VALUES ('test_cur', 'curator://11111111-1111-1111-1111-111111111111', 'Curator Picks', 'active', 'curator', '11111111-1111-1111-1111-111111111111') $$,
    'accepts a curator row that names its curator'
);

SELECT * FROM finish();
ROLLBACK;

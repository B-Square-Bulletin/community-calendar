-- Migration: curator feeds stop carrying their token in feeds.url
-- (GHSA-3pg8-w4j4-6wv8)
--
-- A picks feed is authenticated only by its ?token= query param. `feeds` is
-- world-readable (ddl/16_feeds.sql) and re-exported to cities/<city>/feeds.txt
-- on every build, so storing that URL there published a read-only capability
-- URL for the curator's saved-event feed (and report.py then quoted it into
-- the Pages-served report.json).
--
-- Curator rows now name the curator instead: curator_user_id, with url set to
-- the non-secret curator://<user_id>. download_feeds.py mints the real URL from
-- feed_tokens at download time. That table is RLS-scoped to its owner, so
-- rotation needs no feeds edit and no token can reach the repo again.
--
-- A row whose token belongs to another deployment cannot be resolved here
-- (feed_tokens is per-project) and is retired with its events. Idempotent: a
-- second run converts nothing, rotates nothing, deletes nothing.

ALTER TABLE feeds ADD COLUMN IF NOT EXISTS curator_user_id uuid
  REFERENCES auth.users(id) ON DELETE CASCADE;

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT f.id, t.id AS token_id, t.user_id
    FROM feeds f
    JOIN feed_tokens t
      ON t.token = substring(
           f.url
           from 'token=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$'
         )::uuid
    WHERE f.url LIKE '%/functions/v1/my-picks?token=%'
  LOOP
    UPDATE feeds
    SET feed_type = 'curator',
        curator_user_id = r.user_id,
        url = 'curator://' || r.user_id
    WHERE id = r.id;

    -- The token is in public git history forever; rotate it so the published
    -- copy stops working. The curator re-copies the new URL from the app.
    UPDATE feed_tokens SET token = gen_random_uuid() WHERE id = r.token_id;
  END LOOP;
END $$;

-- Retire curator rows this deployment cannot mint a token for (e.g. a feed
-- served by another Supabase project). Retiring goes through remove_feed(),
-- the DB authority for source retirement (ADR 0007), so its merge-survivor
-- rules apply. remove_feed() is admin-gated, and a raw SQL session has no JWT:
-- present an admin claim the way ddl/16_feeds.sql documents.
DO $$
DECLARE
  stale_ids bigint[];
  admin_id uuid;
BEGIN
  SELECT array_agg(id) INTO stale_ids
  FROM feeds
  WHERE url LIKE '%/functions/v1/my-picks?token=%';

  IF stale_ids IS NULL THEN
    RETURN;
  END IF;

  SELECT user_id INTO admin_id FROM admin_users LIMIT 1;
  IF admin_id IS NULL THEN
    RAISE EXCEPTION
      'cannot retire curator feed(s) %: no admin_users row to authorize remove_feed()',
      stale_ids;
  END IF;

  PERFORM set_config(
    'request.jwt.claims', json_build_object('sub', admin_id)::text, true
  );
  PERFORM remove_feed(id) FROM unnest(stale_ids) AS id;
END $$;

-- Only these two constraints keep the token out. A CHECK covers every writer
-- (app dialog, pending_feeds, seed scripts, ad-hoc SQL), with no trigger to
-- maintain.
ALTER TABLE feeds DROP CONSTRAINT IF EXISTS feeds_url_has_no_capability_token;
ALTER TABLE feeds
  ADD CONSTRAINT feeds_url_has_no_capability_token
  CHECK (url NOT LIKE '%/functions/v1/my-picks%');

ALTER TABLE feeds DROP CONSTRAINT IF EXISTS feeds_curator_user_matches_type;
ALTER TABLE feeds
  ADD CONSTRAINT feeds_curator_user_matches_type
  CHECK ((feed_type = 'curator') = (curator_user_id IS NOT NULL));

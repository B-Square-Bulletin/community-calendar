-- Initial schema for Community Calendar
-- This represents the base schema before incremental migrations were added.
-- DO NOT modify this file - subsequent migrations build on top of it.

-- Enable required extensions

-- HTTP requests from database (for scheduled jobs)
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Scheduled jobs
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Admin users table - server-authorized access for privileged UI/actions

CREATE TABLE IF NOT EXISTS admin_users (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;

-- Users can only view their own admin row (presence means admin)
CREATE POLICY "Users can view own admin status"
  ON admin_users FOR SELECT
  USING (auth.uid() = user_id);

-- Service role manages admin grants/revokes
CREATE POLICY "Service role can manage admin users"
  ON admin_users FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Events table - stores calendar events from all sources

CREATE TABLE IF NOT EXISTS events (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  title text NOT NULL,
  start_time timestamptz NOT NULL,
  end_time timestamptz,
  location text,
  description text,
  url text,
  city text,                -- e.g., 'santarosa', 'sebastopol', 'cotati'
  source text,              -- e.g., 'bohemian', 'pressdemocrat' (no date suffix)
  source_id text,           -- filename-derived source identifier for curator reference
  source_uid text UNIQUE,   -- unique ID from source for deduplication
  transcript text,          -- Whisper transcript for audio-captured events
  cluster_id text,          -- groups similar events within same timeslot for UI display
  source_urls jsonb,        -- per-source URLs for aggregator attribution links
  category text,            -- auto-classified bucket (e.g., 'Music & Concerts', 'Arts & Culture')
  ics_categories text[],    -- CATEGORIES values from ICS source
  image_url text,           -- event image URL from ICS ATTACH or scraper
  all_day boolean DEFAULT false,  -- true for all-day events (VALUE=DATE in ICS)
  created_at timestamptz DEFAULT now()
);

-- RPC for stale event cleanup (used by load-events edge function;
-- replaces URL-based NOT IN filter that exceeded PostgREST URL length limits)
CREATE OR REPLACE FUNCTION delete_stale_events(p_city text, p_source_uids text[])
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count bigint;
BEGIN
  DELETE FROM events
  WHERE city = p_city
    AND source_uid IS NOT NULL
    AND source_uid != ALL(p_source_uids)
  ;
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

-- Unique index on source_uid for deduplication
CREATE UNIQUE INDEX IF NOT EXISTS events_source_uid_unique ON events (source_uid);

-- Index for city filtering
CREATE INDEX IF NOT EXISTS events_city_idx ON events (city);

-- Index for category filtering
CREATE INDEX IF NOT EXISTS events_category_idx ON events (category);

-- NOTE: events_source_idx added in migration 20260606012632

-- Enable Row Level Security (public read access)
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read events
CREATE POLICY "Anyone can read events"
  ON events FOR SELECT
  USING (true);

-- Allow service functions to insert events
CREATE POLICY "Service function can insert events"
  ON events FOR INSERT
  WITH CHECK (true);

-- Allow admin users to delete events
CREATE POLICY "Admin users can delete events"
  ON events FOR DELETE
  USING (auth.uid() IN (SELECT user_id FROM admin_users));

-- Picks table - stores user's saved/favorited events

CREATE TABLE IF NOT EXISTS picks (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  event_id bigint NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  created_at timestamptz DEFAULT now(),
  UNIQUE(user_id, event_id)
);

-- Enable Row Level Security
ALTER TABLE picks ENABLE ROW LEVEL SECURITY;

-- Users can only see their own picks
CREATE POLICY "Users can view own picks"
  ON picks FOR SELECT
  USING (auth.uid() = user_id);

-- Users can insert their own picks
CREATE POLICY "Users can insert own picks"
  ON picks FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Users can delete their own picks
CREATE POLICY "Users can delete own picks"
  ON picks FOR DELETE
  USING (auth.uid() = user_id);

-- Feed tokens table - unique token per user for ICS feed access

CREATE TABLE IF NOT EXISTS feed_tokens (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
  token uuid DEFAULT gen_random_uuid() NOT NULL UNIQUE,
  created_at timestamptz DEFAULT now()
);

-- Note: token column is UNIQUE, which auto-creates feed_tokens_token_key index.
-- No additional index needed for token lookups.

-- Enable Row Level Security
ALTER TABLE feed_tokens ENABLE ROW LEVEL SECURITY;

-- Users can only view their own feed token
CREATE POLICY "Users can view own feed token"
  ON feed_tokens FOR SELECT
  USING (auth.uid() = user_id);

-- Users can insert their own feed token (created on first sign-in)
CREATE POLICY "Users can insert own feed token"
  ON feed_tokens FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Event enrichments table - curator overrides/additions per event
-- Self-standing: enrichments store their own title/start_time/city so they
-- survive even if the original event row is deleted.

CREATE TABLE IF NOT EXISTS event_enrichments (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  event_id bigint REFERENCES events(id) ON DELETE CASCADE,  -- nullable
  curator_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  rrule text,
  url text,
  description text,
  location text,
  end_time timestamptz,
  categories text[],
  notes text,
  title text,            -- copied from event at creation
  start_time timestamptz, -- copied from event at creation
  city text,             -- copied from event at creation
  curator_name text,     -- display name for source attribution
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(event_id, curator_id)
);

-- Index for event lookups
CREATE INDEX IF NOT EXISTS idx_event_enrichments_event_id ON event_enrichments (event_id);

-- Index for curator lookups
CREATE INDEX IF NOT EXISTS idx_event_enrichments_curator_id ON event_enrichments (curator_id);

-- Enable Row Level Security
ALTER TABLE event_enrichments ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read enrichments
CREATE POLICY "Enrichments are publicly readable"
  ON event_enrichments FOR SELECT
  USING (true);

-- Users can insert their own enrichments
CREATE POLICY "Users can insert own enrichments"
  ON event_enrichments FOR INSERT
  WITH CHECK (auth.uid() = curator_id);

-- Users can update their own enrichments
CREATE POLICY "Users can update own enrichments"
  ON event_enrichments FOR UPDATE
  USING (auth.uid() = curator_id);

-- Users can delete their own enrichments
CREATE POLICY "Users can delete own enrichments"
  ON event_enrichments FOR DELETE
  USING (auth.uid() = curator_id);

-- Distinct cities materialized view - for city picker UI

CREATE MATERIALIZED VIEW IF NOT EXISTS distinct_cities AS
SELECT DISTINCT city
FROM events
WHERE city IS NOT NULL
ORDER BY city;

-- Refresh function for distinct_cities view
CREATE OR REPLACE FUNCTION refresh_distinct_cities()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  REFRESH MATERIALIZED VIEW distinct_cities;
END;
$$;

-- Admin GitHub users table

CREATE TABLE IF NOT EXISTS admin_github_users (
  github_id text PRIMARY KEY,
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE admin_github_users ENABLE ROW LEVEL SECURITY;

-- Allow anyone to check admin status
CREATE POLICY "Anyone can check GitHub admin status"
  ON admin_github_users FOR SELECT
  USING (true);

-- Service role manages admin grants
CREATE POLICY "Service role can manage GitHub admins"
  ON admin_github_users FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- User settings table - per-user, per-city preferences (e.g., hidden sources)

CREATE TABLE IF NOT EXISTS user_settings (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  city text NOT NULL,
  hidden_sources text[] DEFAULT '{}',
  one_click_pick boolean NOT NULL DEFAULT false,
  layout_mode text DEFAULT 'list',
  image_mode text DEFAULT 'everywhere',
  dashboard jsonb DEFAULT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(user_id, city)
);

-- Enable Row Level Security
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

-- Users can only view their own settings
CREATE POLICY "Users can view own settings"
  ON user_settings FOR SELECT
  USING (auth.uid() = user_id);

-- Users can only insert their own settings
CREATE POLICY "Users can insert own settings"
  ON user_settings FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Users can only update their own settings
CREATE POLICY "Users can update own settings"
  ON user_settings FOR UPDATE
  USING (auth.uid() = user_id);

-- Admin Google users table

CREATE TABLE IF NOT EXISTS admin_google_users (
  google_id text PRIMARY KEY,
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE admin_google_users ENABLE ROW LEVEL SECURITY;

-- Allow anyone to check admin status
CREATE POLICY "Anyone can check Google admin status"
  ON admin_google_users FOR SELECT
  USING (true);

-- Service role manages admin grants
CREATE POLICY "Service role can manage Google admins"
  ON admin_google_users FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Source suggestions table - curator-proposed calendar sources

CREATE TABLE IF NOT EXISTS source_suggestions (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  city text NOT NULL,
  url text NOT NULL,
  name text NOT NULL,
  notes text,
  status text DEFAULT 'pending',
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE source_suggestions ENABLE ROW LEVEL SECURITY;

-- Anyone can view suggestions
CREATE POLICY "Anyone can view source suggestions"
  ON source_suggestions FOR SELECT
  USING (true);

-- Authenticated users can create suggestions
CREATE POLICY "Authenticated users can create suggestions"
  ON source_suggestions FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Admin users can update suggestions
CREATE POLICY "Admin users can update suggestions"
  ON source_suggestions FOR UPDATE
  USING (auth.uid() IN (SELECT user_id FROM admin_users));

-- Category overrides table - manual category corrections

CREATE TABLE IF NOT EXISTS category_overrides (
  source_uid text PRIMARY KEY,
  category text NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE category_overrides ENABLE ROW LEVEL SECURITY;

-- Anyone can view overrides
CREATE POLICY "Anyone can view category overrides"
  ON category_overrides FOR SELECT
  USING (true);

-- Admin users can manage overrides
CREATE POLICY "Admin users can manage category overrides"
  ON category_overrides FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM admin_users));

-- Source names table - aggregated source counts per city

CREATE TABLE IF NOT EXISTS source_names (
  city text NOT NULL,
  name text NOT NULL,
  event_count integer DEFAULT 0,
  PRIMARY KEY (city, name)
);

-- Enable Row Level Security (public read)
ALTER TABLE source_names ENABLE ROW LEVEL SECURITY;

-- Anyone can read source names
CREATE POLICY "Anyone can read source names"
  ON source_names FOR SELECT
  USING (true);

-- Original refresh_source_names() implementation
-- (Rewritten in migration 20260606013000)
CREATE OR REPLACE FUNCTION refresh_source_names(target_city text)
RETURNS void
SET statement_timeout TO '0'
AS $$
BEGIN
  -- Upsert distinct non-comma sources for this city
  INSERT INTO source_names (city, name, event_count)
  SELECT city, source, COUNT(*)
  FROM events
  WHERE city = target_city
    AND source IS NOT NULL
    AND source NOT LIKE '%,%'
  GROUP BY city, source
  ON CONFLICT (city, name) DO UPDATE SET event_count = EXCLUDED.event_count;

  -- Update counts for sources that also appear in comma-separated merged sources
  UPDATE source_names sn
  SET event_count = (
    SELECT COUNT(DISTINCT e.id)
    FROM events e
    WHERE e.city = sn.city
      AND (e.source = sn.name
        OR e.source LIKE sn.name || ', %'
        OR e.source LIKE '%, ' || sn.name
        OR e.source LIKE '%, ' || sn.name || ', %')
  )
  WHERE sn.city = target_city;

  -- Remove sources that no longer have events
  DELETE FROM source_names
  WHERE city = target_city AND event_count = 0;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Feeds table - registry of ICS feeds and scrapers
-- NOTE: fallback_url column added in migration 20260510180000

CREATE TABLE IF NOT EXISTS feeds (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  city text NOT NULL,
  name text NOT NULL,
  url text,
  feed_type text NOT NULL,
  scraper_cmd text,
  status text DEFAULT 'pending',
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security (public read)
ALTER TABLE feeds ENABLE ROW LEVEL SECURITY;

-- Anyone can read feeds
CREATE POLICY "Anyone can read feeds"
  ON feeds FOR SELECT
  USING (true);

-- Admin users can manage feeds
CREATE POLICY "Admin users can manage feeds"
  ON feeds FOR ALL
  USING (auth.uid() IN (SELECT user_id FROM admin_users));

-- Deduplicated events view - most recent version of each event by source_uid

CREATE MATERIALIZED VIEW IF NOT EXISTS deduplicated_events AS
SELECT DISTINCT ON (source_uid) *
FROM events
WHERE source_uid IS NOT NULL
ORDER BY source_uid, created_at DESC;

-- NOTE: Index optimization in migration 20260421182300
-- Initial indexes (will be replaced by compound index):
CREATE INDEX IF NOT EXISTS deduplicated_events_city_idx ON deduplicated_events (city);
CREATE INDEX IF NOT EXISTS deduplicated_events_start_time_idx ON deduplicated_events (start_time);

-- Refresh function for deduplicated_events view
CREATE OR REPLACE FUNCTION refresh_deduplicated_events()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  REFRESH MATERIALIZED VIEW deduplicated_events;
END;
$$;

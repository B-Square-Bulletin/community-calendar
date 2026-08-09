-- Schema for database-backed feed health reporting.
--
-- feed_health:    per-source, per-day event counts with optional errors
-- feed_anomalies: detected anomalies (zero events, significant drops, etc.)
-- prune_feed_health(city, days):   RPC to clean old health rows
-- prune_feed_anomalies(city, days): RPC to clean old anomaly rows
--
-- RLS: anyone can read (anon key used by dashboard), service role manages all.

CREATE TABLE IF NOT EXISTS feed_health (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  city text NOT NULL,
  feed_name text NOT NULL,
  source_name text,
  source_url text,
  feed_type text NOT NULL CHECK (feed_type IN ('ics_url', 'scraper')),
  scraper_cmd text,
  event_count integer NOT NULL DEFAULT 0,
  error text,
  checked_at timestamptz DEFAULT now(),
  checked_date date NOT NULL,
  UNIQUE (city, feed_name, checked_date)
);

ALTER TABLE feed_health ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read feed_health" ON feed_health
  FOR SELECT USING (true);

CREATE POLICY "Service role can manage feed_health" ON feed_health
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Index for dashboard queries: latest status per source ordered by checked_at
CREATE INDEX IF NOT EXISTS feed_health_city_checked_at_idx
  ON feed_health (city, checked_at DESC);

CREATE TABLE IF NOT EXISTS feed_anomalies (
  id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  city text NOT NULL,
  feed_name text NOT NULL,
  anomaly_type text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
  message text NOT NULL,
  previous_count integer,
  current_count integer,
  detected_at timestamptz DEFAULT now()
);

ALTER TABLE feed_anomalies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read feed_anomalies" ON feed_anomalies
  FOR SELECT USING (true);

CREATE POLICY "Service role can manage feed_anomalies" ON feed_anomalies
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Index for dashboard: recent anomalies by city
CREATE INDEX IF NOT EXISTS feed_anomalies_city_detected_at_idx
  ON feed_anomalies (city, detected_at DESC);

-- Pruning RPCs (called by edge function, scoped per-city so multi-city
-- deployments don't race)

CREATE OR REPLACE FUNCTION prune_feed_health(p_city text, p_days integer)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count bigint;
BEGIN
  DELETE FROM feed_health
  WHERE city = p_city
    AND checked_date < (CURRENT_DATE - p_days);
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

CREATE OR REPLACE FUNCTION prune_feed_anomalies(p_city text, p_days integer)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count bigint;
BEGIN
  DELETE FROM feed_anomalies
  WHERE city = p_city
    AND detected_at < (CURRENT_TIMESTAMP - (p_days || ' days')::interval);
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

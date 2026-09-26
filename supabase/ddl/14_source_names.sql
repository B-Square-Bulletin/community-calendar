-- Source names: clean flat list of individual source names per city
-- Populated/refreshed by refresh_source_names() RPC during nightly build.
-- The RPC prefers events.source_names and falls back to splitting events.source
-- for legacy rows that do not have structured names.

CREATE TABLE source_names (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  city text NOT NULL,
  name text NOT NULL,
  event_count integer DEFAULT 0,
  UNIQUE(city, name)
);

ALTER TABLE source_names ENABLE ROW LEVEL SECURITY;
CREATE POLICY "source_names_read" ON source_names FOR SELECT USING (true);

-- RPC to refresh source names and counts for a city (called after load-events)
CREATE OR REPLACE FUNCTION refresh_source_names(target_city text)
RETURNS void
SET statement_timeout TO '0'
AS $$
BEGIN
  -- Delete old entries for this city first
  DELETE FROM source_names WHERE city = target_city;

  -- Prefer the route's structured names so commas inside a source name stay
  -- intact. Split `source` only for legacy rows with no structured names.
  INSERT INTO source_names (city, name, event_count)
  SELECT target_city, source_name, COUNT(DISTINCT event_id)
  FROM (
    SELECT e.id AS event_id, trim(source_entry.name) AS source_name
    FROM events e
    CROSS JOIN LATERAL unnest(
      CASE
        WHEN COALESCE(cardinality(e.source_names), 0) > 0 THEN e.source_names
        ELSE string_to_array(e.source, ',')
      END
    ) AS source_entry(name)
    WHERE e.city = target_city
      AND (COALESCE(cardinality(e.source_names), 0) > 0 OR e.source IS NOT NULL)
  ) entries
  WHERE source_name <> ''
  GROUP BY source_name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

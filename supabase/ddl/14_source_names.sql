-- Source names: clean flat list of individual source names per city
-- Populated/refreshed by refresh_source_names() RPC during nightly build
-- The events.source column may contain comma-separated merged sources from dedup;
-- this table provides the canonical individual source names with counts.

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
  
  -- Split comma-separated sources and count in one pass
  -- This processes each event exactly once (O(n)) instead of
  -- running a correlated subquery for each source_name (O(n×m)).
  -- Empty names (from blank sources, trailing/double commas) are filtered out.
  INSERT INTO source_names (city, name, event_count)
  SELECT city, name, event_count FROM (
    SELECT
      target_city AS city,
      trim(unnest(string_to_array(source, ','))) AS name,
      COUNT(DISTINCT id) AS event_count
    FROM events
    WHERE city = target_city
      AND source IS NOT NULL
    GROUP BY name
  ) s
  WHERE name <> '';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

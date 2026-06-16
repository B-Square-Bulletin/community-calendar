-- Fix delete_stale_events performance: NOT IN with 3500+ source_uids was
-- hitting Postgres statement timeout (code 57014). Rewrite using NOT EXISTS
-- with unnest() for index-friendly execution.
--
-- Also add a composite index on (city, source_uid) so the WHERE clause
-- filters both columns through a single index scan.

-- New composite index for the (city, source_uid) filter in delete_stale_events
CREATE INDEX IF NOT EXISTS events_city_source_uid_idx ON events (city, source_uid);

-- Rewrite the RPC to use NOT EXISTS (unnest) instead of != ALL()
CREATE OR REPLACE FUNCTION delete_stale_events(p_city text, p_source_uids text[])
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  deleted_count bigint;
BEGIN
  DELETE FROM events e
  WHERE e.city = p_city
    AND e.source_uid IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM unnest(p_source_uids) AS u(uid)
      WHERE u.uid = e.source_uid
    );
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

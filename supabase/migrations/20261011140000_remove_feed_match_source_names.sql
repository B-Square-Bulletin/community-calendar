-- Make remove_feed clear rows that a merge folded into another source.
--
-- remove_feed(feed_id) deleted events by exact display name (events.source =
-- feeds.name). A merge survivor keeps its original source_id but rewrites
-- source to the comma-joined aggregate of its members (scripts/ics_to_json.py),
-- so a retired feed that had merged into a survivor was missed. Before
-- 20261011130000_source_aware_delete_stale_events.sql the nightly sweep still
-- removed such a row once its uid left the payload; now that absent sources are
-- preserved, the row would persist. Match the feed's name against the
-- structured source_names as well. A row whose source_names are slug fallbacks
-- (a lone name containing a comma) can still be missed; a durable mapping from
-- feed to filename-derived source_id is a follow-up.

CREATE OR REPLACE FUNCTION remove_feed(feed_id bigint)
RETURNS TABLE (events_deleted bigint, feed_deleted boolean)
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  f record;
  ev_count bigint;
BEGIN
  SELECT city, name INTO f FROM feeds WHERE id = feed_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'remove_feed: no feed row with id %', feed_id;
  END IF;

  DELETE FROM events e
  WHERE e.city = f.city
    AND (e.source = f.name OR f.name = ANY(coalesce(e.source_names, ARRAY[]::text[])));
  GET DIAGNOSTICS ev_count = ROW_COUNT;

  DELETE FROM feeds WHERE id = feed_id;

  RETURN QUERY SELECT ev_count, true;
END;
$$;

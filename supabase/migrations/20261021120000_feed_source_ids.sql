-- Feeds remember every source_id (output .ics stem) they have produced, so a
-- retired feed can delete the merge survivors it owns (#232, ADR 0017).
--
-- The build records the value: download_feeds.py for ics_url/curator rows and
-- run_scrapers_from_db.py for scraper rows. The array is a history because a
-- feed's url can change (see the convert_*_feed_to_scraper migrations) and
-- rows built under the older stem must still be attributable.
ALTER TABLE feeds ADD COLUMN source_ids text[] NOT NULL DEFAULT '{}';

-- remove_feed now matches by source_id (the feed's own rows, including a merge
-- survivor whose comma-joined `source` hides its owner) and keeps the old
-- exact-name match for rows built before the mapping existed. A feed with no
-- recorded history falls back to the name match with a warning.
CREATE OR REPLACE FUNCTION remove_feed(feed_id bigint)
RETURNS TABLE (events_deleted bigint, feed_deleted boolean)
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
  f record;
  has_history boolean;
  ev_count bigint;
BEGIN
  SELECT city, name, source_ids INTO f FROM feeds WHERE id = feed_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'remove_feed: no feed row with id %', feed_id;
  END IF;

  has_history := cardinality(f.source_ids) > 0;
  IF NOT has_history THEN
    RAISE WARNING
      'remove_feed: feed % (id %) has no recorded source_id; matching by name only',
      f.name, feed_id;
  END IF;

  DELETE FROM events e
  WHERE e.city = f.city
    AND ((has_history AND e.source_id = ANY(f.source_ids)) OR e.source = f.name);
  GET DIAGNOSTICS ev_count = ROW_COUNT;

  DELETE FROM feeds WHERE id = feed_id;

  RETURN QUERY SELECT ev_count, true;
END;
$$;

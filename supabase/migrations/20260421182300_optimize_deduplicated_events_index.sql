-- Replace separate city and start_time indexes on deduplicated_events
-- with a single compound index. The compound index serves all three use
-- cases (city-only, start_time-only, city+start_time) and lets the planner
-- satisfy the main app query in one index range scan instead of intersecting
-- two indexes and post-filtering.
--
-- Measured impact (Toronto, 5000-row LIMIT):
--   Buffer reads:  3689 → 1596 pages (57% fewer)
--   Rows filtered: 11123 → 0 (no wasted work)
--   Cold start:    ~2s → ~0.9s estimated

DROP INDEX IF EXISTS deduplicated_events_city_idx;
DROP INDEX IF EXISTS deduplicated_events_start_time_idx;

CREATE INDEX IF NOT EXISTS deduplicated_events_city_start_time_idx
  ON deduplicated_events (city, start_time);

ANALYZE deduplicated_events;

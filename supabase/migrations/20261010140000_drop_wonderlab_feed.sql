-- Migration: Drop the WonderLab Museum feed (issue #186)
--
-- wonderlab.org fronts the whole host with Cloudflare bot protection. From
-- GitHub Actions egress every endpoint returns an HTTP 403 Cloudflare
-- "Just a moment..." challenge page (HTML), for every User-Agent — the ICS
-- export (/events/list/?ical=1) and the Tribe REST API
-- (/wp-json/tribe/events/v1/events/) alike. The downloader stores any
-- non-empty body as a successful download, so the challenge page was written
-- to wonderlab.ics and the source reported "serving html, not ICS" with no
-- good build in recorded history.
--
-- This is the documented Cloudflare-IP-block pattern that could not be fixed
-- by any header or UA change and led to dropping NAMI Greater Bloomington
-- (#19). WonderLab events are already ingested through WFIU Community
-- Calendar (ipm.org), Visit Bloomington, and Pillar Arts Community Calendar,
-- so dropping the direct feed loses no coverage.
--
-- Delete the feed row and any events it produced. Idempotent and a no-op on
-- forks without the row.

DO $$
DECLARE
  dead_url text := 'https://wonderlab.org/events/list/?ical=1';
BEGIN
  DELETE FROM events
  WHERE city = 'bloomington'
    AND source = 'WonderLab Museum';

  DELETE FROM feeds
  WHERE city = 'bloomington'
    AND url = dead_url;
END $$;

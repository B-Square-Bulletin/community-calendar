-- Migration: Repair the Monroe County Public Library feed (issue #183)
--
-- Communico migrated MCPL's event portal off the calendar.mcpl.info custom
-- domain. Its /feeds endpoint now 404s (broken since 2026-09-30, ~500 events
-- lost). The library's own iCal button targets the partner portal
-- https://<keyword>.libnet.info; MCPL's keyword is "mcplin".
--
-- Point the registered Bloomington feeds row at the working endpoint, keeping
-- the same feed payload (all locations/ages/types, 90-day window) so the
-- source name and filters are unchanged. If a replacement row already exists,
-- retire the dead row instead: feeds is unique on (city, url), so two rows
-- cannot share the new URL. Idempotent and a no-op on forks without the row.

DO $$
DECLARE
  dead_prefix text := 'https://calendar.mcpl.info/feeds%';
  new_url text := 'https://mcplin.libnet.info/feeds?data=eyJmZWVkVHlwZSI6ImljYWwiLCJmaWx0ZXJzIjp7ImxvY2F0aW9uIjpbImFsbCJdLCJhZ2VzIjpbImFsbCJdLCJ0eXBlcyI6WyJhbGwiXSwidGFncyI6W10sInRlcm0iOiIiLCJkYXlzIjo5MH19';
BEGIN
  IF EXISTS (SELECT 1 FROM feeds WHERE city = 'bloomington' AND url = new_url) THEN
    -- A replacement row is already present: retire the dead row instead of
    -- colliding with the (city, url) uniqueness constraint.
    UPDATE feeds
    SET status = 'removed'
    WHERE city = 'bloomington'
      AND name = 'Monroe County Public Library'
      AND url LIKE dead_prefix;
  ELSE
    UPDATE feeds
    SET url = new_url
    WHERE city = 'bloomington'
      AND name = 'Monroe County Public Library'
      AND url LIKE dead_prefix;
  END IF;
END $$;

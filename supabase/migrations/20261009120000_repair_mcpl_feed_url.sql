-- Migration: Repair the Monroe County Public Library feed (issue #183)
--
-- Communico migrated MCPL's event portal off the calendar.mcpl.info custom
-- domain. Its /feeds endpoint now 404s (broken since 2026-09-30, ~500 events
-- lost). The library's own iCal button targets the partner portal
-- https://<keyword>.libnet.info; MCPL's keyword is "mcplin".
--
-- Point the registered feeds row at the working endpoint, keeping the same
-- feed payload (all locations/ages/types, 90-day window) so the source name
-- and filters are unchanged. Idempotent: a fork without the old row, or one
-- that already carries the new URL, is a no-op.

DO $$
DECLARE
  new_url text := 'https://mcplin.libnet.info/feeds?data=eyJmZWVkVHlwZSI6ImljYWwiLCJmaWx0ZXJzIjp7ImxvY2F0aW9uIjpbImFsbCJdLCJhZ2VzIjpbImFsbCJdLCJ0eXBlcyI6WyJhbGwiXSwidGFncyI6W10sInRlcm0iOiIiLCJkYXlzIjo5MH19';
BEGIN
  IF NOT EXISTS (SELECT 1 FROM feeds WHERE url = new_url) THEN
    UPDATE feeds
    SET url = new_url
    WHERE url LIKE 'https://calendar.mcpl.info/feeds%';
  END IF;
END $$;

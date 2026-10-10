-- Migration: Repair the Brown County Events feed (issue #184)
--
-- browncounty.com's Modern Events Calendar (MEC) moved its events page from
-- /events/ to /calendar/. MEC serves the iCal export (?mec-ical-feed=1) only on
-- the configured events page, so requesting the old URL now renders the events
-- page HTML instead of ICS and the Bloomington source dropped ~106 events since
-- 2026-10-03. Point the registered feed row at the new events page URL with the
-- same MEC export parameter.
--
-- If a replacement row already exists, retire the dead row instead: feeds is
-- unique on (city, url), so two rows cannot share the new URL. Idempotent and a
-- no-op on forks without the row.

DO $$
DECLARE
  dead_prefix text := 'https://browncounty.com/events/%mec-ical-feed=1%';
  new_url text := 'https://browncounty.com/calendar/?mec-ical-feed=1';
BEGIN
  IF EXISTS (SELECT 1 FROM feeds WHERE city = 'bloomington' AND url = new_url) THEN
    -- A replacement row is already present: retire the dead row instead of
    -- colliding with the (city, url) uniqueness constraint.
    UPDATE feeds
    SET status = 'removed'
    WHERE city = 'bloomington'
      AND name = 'Brown County Events'
      AND url LIKE dead_prefix;
  ELSE
    UPDATE feeds
    SET url = new_url
    WHERE city = 'bloomington'
      AND name = 'Brown County Events'
      AND url LIKE dead_prefix;
  END IF;
END $$;

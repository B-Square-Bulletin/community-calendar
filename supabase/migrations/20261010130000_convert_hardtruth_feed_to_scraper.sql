-- Migration: Convert the Hard Truth Distilling Co. feed to a Tribe REST scraper
-- (issue #185)
--
-- hardtruth.com now sits behind SiteGround's sgcaptcha bot protection. It
-- answers the feed downloader's urllib call with an HTTP 202 HTML challenge
-- page instead of ICS (and hard-403s the project's default User-Agent over
-- curl), so hardtruth.ics held the challenge page and the source reported as
-- "serving html, not ICS" with no good build in recorded history.
--
-- The Tribe REST API is challenged the same way. Per the documented WAF-bypass
-- pattern for SiteGround-hosted Tribe sites (docs/discovery-lessons.md,
-- scrapers/tribe_rest.py) the source is converted from an ics_url feed to a
-- tribe_rest.py scraper with a plain Mozilla/5.0 User-Agent. SiteGround is
-- intermittently permissive, so on a blocked day the scraper still writes a
-- valid-empty calendar (classified "quiet"), not a broken_feed. Idempotent and
-- a no-op on forks without the row.

DO $$
DECLARE
  old_url text := 'https://hardtruth.com/events/?post_type=tribe_events&ical=1&eventDisplay=list';
  out_path text := 'cities/bloomington/hardtruth.ics';
  cmd text := 'python scrapers/tribe_rest.py --api-base "https://hardtruth.com" --name "Hard Truth Distilling Co." --timezone America/Indiana/Indianapolis --user-agent "Mozilla/5.0" --output cities/bloomington/hardtruth.ics';
BEGIN
  UPDATE feeds
  SET feed_type = 'scraper',
      url = out_path,
      scraper_cmd = cmd
  WHERE city = 'bloomington'
    AND url = old_url;
END $$;

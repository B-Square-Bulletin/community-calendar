-- Add 'curator' to feed_health.feed_type CHECK constraint.
-- The feeds table already supports 'curator'; feed_health should match.
-- Issue: #11

DO $$
DECLARE
    constraint_name text;
BEGIN
    -- Find and drop the existing CHECK constraint (auto-named by PostgreSQL)
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'feed_health'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%feed_type%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE 'ALTER TABLE feed_health DROP CONSTRAINT ' || constraint_name;
    END IF;

    EXECUTE 'ALTER TABLE feed_health ADD CONSTRAINT feed_health_feed_type_check CHECK (feed_type IN (''ics_url'', ''scraper'', ''curator''))';
END $$;

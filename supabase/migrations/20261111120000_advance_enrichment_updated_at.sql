-- Advance event_enrichments.updated_at when a feed-rendered field changes (#282).
--
-- The my-picks feed merges this value into each event's LAST-MODIFIED, so a
-- curator edit must move it. The pick editor re-upserts every column without
-- updated_at, so the database owns the value: a BEFORE UPDATE trigger advances
-- it only when feed content actually changed and otherwise keeps OLD.
--
-- The feed-rendered set is the enrichment overrides in
-- supabase/functions/my-picks/index.ts; keep the two in sync.

CREATE OR REPLACE FUNCTION public.touch_event_enrichment_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.rrule IS DISTINCT FROM OLD.rrule
     OR NEW.categories IS DISTINCT FROM OLD.categories
     OR NEW.notes IS DISTINCT FROM OLD.notes
     OR NEW.description IS DISTINCT FROM OLD.description
     OR NEW.location IS DISTINCT FROM OLD.location
  THEN
    NEW.updated_at := now();
  ELSE
    -- Also drops any value a client supplies on UPDATE: the database owns
    -- this column. An INSERT is not intercepted, so creation keeps the
    -- default or the value the writer sends.
    NEW.updated_at := OLD.updated_at;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS event_enrichments_touch_updated_at ON public.event_enrichments;
CREATE TRIGGER event_enrichments_touch_updated_at
  BEFORE UPDATE ON public.event_enrichments
  FOR EACH ROW EXECUTE FUNCTION public.touch_event_enrichment_updated_at();

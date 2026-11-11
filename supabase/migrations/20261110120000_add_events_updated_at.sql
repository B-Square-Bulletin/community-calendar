-- Give events a content-sensitive modification time (#266).
--
-- load-events upserts every event on every build, so a naive
-- updated_at = now() on the upsert would mark the whole calendar as changed
-- each run. Instead the database owns the value: a BEFORE UPDATE trigger
-- keeps OLD.updated_at unless a feed-relevant column actually changed, and the
-- loader payload never mentions updated_at.
--
-- Add nullable, backfill from created_at, then set default + NOT NULL so no
-- existing row reads as "modified at migration time".
--
-- Ordering: post-compatibility/20260923130000_drop_cluster_id.sql now reads
-- updated_at too, so promote that file with a timestamp after this migration
-- or its CREATE MATERIALIZED VIEW fails.

ALTER TABLE public.events ADD COLUMN IF NOT EXISTS updated_at timestamptz;

UPDATE public.events
SET updated_at = COALESCE(created_at, now())
WHERE updated_at IS NULL;

ALTER TABLE public.events ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE public.events ALTER COLUMN updated_at SET NOT NULL;

-- Feed-relevant columns only. Category, transcript, source_urls, all_day,
-- duplicate-group bookkeeping, source_id, cluster_id and created_at are not
-- feed content and must not look like content changes.
CREATE OR REPLACE FUNCTION public.touch_event_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.title IS DISTINCT FROM OLD.title
     OR NEW.start_time IS DISTINCT FROM OLD.start_time
     OR NEW.end_time IS DISTINCT FROM OLD.end_time
     OR NEW.location IS DISTINCT FROM OLD.location
     OR NEW.description IS DISTINCT FROM OLD.description
     OR NEW.url IS DISTINCT FROM OLD.url
     OR NEW.image_url IS DISTINCT FROM OLD.image_url
     OR NEW.city IS DISTINCT FROM OLD.city
     OR NEW.source IS DISTINCT FROM OLD.source
  THEN
    NEW.updated_at := now();
  ELSE
    -- Also drops any value a client supplies on UPDATE: the database owns
    -- this column. An INSERT keeps the default or an explicit value, which
    -- the backfill relies on.
    NEW.updated_at := OLD.updated_at;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS events_touch_updated_at ON public.events;
CREATE TRIGGER events_touch_updated_at
  BEFORE UPDATE ON public.events
  FOR EACH ROW EXECUTE FUNCTION public.touch_event_updated_at();

-- The app reads deduplicated_events, so the new column must be part of the
-- materialized view. This supersedes the view in
-- 20260925120000_fix_deduplicated_events_category_aggregation.sql (unchanged
-- apart from updated_at); a materialized view cannot gain a column without
-- being recreated, so its indexes and grant ship here too.

DROP MATERIALIZED VIEW IF EXISTS public.deduplicated_events;

CREATE MATERIALIZED VIEW IF NOT EXISTS deduplicated_events AS
WITH base AS (
    SELECT
        e.*,
        COALESCE(e.duplicate_group, 'row:' || e.id::text) AS group_key,
        -- The route representative sorts first so representative fields win.
        CASE
            WHEN e.duplicate_group IS NOT NULL
                AND e.source_uid IS NOT DISTINCT FROM e.duplicate_group_representative
            THEN 0
            ELSE 1
        END AS rep_rank,
        CASE
            WHEN e.source_names IS NOT NULL AND array_length(e.source_names, 1) >= 1
                THEN e.source_names
            WHEN COALESCE(e.source, '') <> '' THEN ARRAY[e.source]
            ELSE ARRAY[]::text[]
        END AS structured_names
    FROM events e
    WHERE e.source IS DISTINCT FROM 'poster_capture'
),
name_occurrences AS (
    -- Rank whole occurrences so the representative rank and source position
    -- always come from the same member row.
    SELECT
        b.city,
        b.start_time,
        b.group_key,
        n.name,
        b.rep_rank,
        n.pos,
        ROW_NUMBER() OVER (
            PARTITION BY b.city, b.start_time, b.group_key, n.name
            ORDER BY b.rep_rank, n.pos, b.id
        ) AS occurrence_rank
    FROM base b
    CROSS JOIN LATERAL unnest(b.structured_names) WITH ORDINALITY AS n(name, pos)
),
name_union AS (
    SELECT city, start_time, group_key, name, rep_rank, pos
    FROM name_occurrences
    WHERE occurrence_rank = 1
),
name_agg AS (
    SELECT
        city,
        start_time,
        group_key,
        string_agg(name, ', ' ORDER BY rep_rank, pos, name) AS source,
        array_agg(name ORDER BY rep_rank, pos, name) AS source_names
    FROM name_union
    GROUP BY city, start_time, group_key
),
url_union AS (
    SELECT
        b.city,
        b.start_time,
        b.group_key,
        kv.key AS name,
        kv.value,
        ROW_NUMBER() OVER (
            PARTITION BY b.city, b.start_time, b.group_key, kv.key ORDER BY b.id
        ) AS rn
    FROM base b
    CROSS JOIN LATERAL jsonb_each(b.source_urls) AS kv(key, value)
    WHERE b.source_urls IS NOT NULL AND jsonb_typeof(b.source_urls) = 'object'
),
url_agg AS (
    SELECT
        city,
        start_time,
        group_key,
        jsonb_object_agg(name, value) AS source_urls
    FROM url_union
    WHERE rn = 1
    GROUP BY city, start_time, group_key
),
ics_categories_pick AS (
    SELECT DISTINCT ON (b.city, b.start_time, b.group_key)
        b.city,
        b.start_time,
        b.group_key,
        b.ics_categories
    FROM base b
    WHERE b.ics_categories IS NOT NULL
    ORDER BY b.city, b.start_time, b.group_key, b.rep_rank, b.id
),
rolled AS (
    SELECT
        (array_agg(b.id ORDER BY b.rep_rank, b.id))[1] AS id,
        (array_agg(b.title ORDER BY b.rep_rank, b.id))[1] AS title,
        b.start_time,
        (array_agg(b.end_time ORDER BY b.rep_rank, b.id) FILTER (WHERE b.end_time IS NOT NULL))[1] AS end_time,
        (array_agg(b.url ORDER BY b.rep_rank, b.id) FILTER (WHERE b.url IS NOT NULL AND b.url <> ''))[1] AS url,
        (array_agg(b.location ORDER BY b.rep_rank, b.id) FILTER (WHERE b.location IS NOT NULL))[1] AS location,
        (array_agg(b.description ORDER BY b.rep_rank, b.id) FILTER (WHERE b.description IS NOT NULL))[1] AS description,
        (array_agg(b.source_uid ORDER BY b.rep_rank, b.id))[1] AS source_uid,
        min(b.created_at) AS created_at,
        -- A group changed when any member changed.
        max(b.updated_at) AS updated_at,
        b.city,
        (array_agg(b.transcript ORDER BY b.rep_rank, b.id) FILTER (WHERE b.transcript IS NOT NULL))[1] AS transcript,
        (array_agg(b.source_id ORDER BY b.rep_rank, b.id))[1] AS source_id,
        (array_agg(b.cluster_id ORDER BY b.rep_rank, b.id) FILTER (WHERE b.cluster_id IS NOT NULL))[1] AS cluster_id,
        (array_agg(b.category ORDER BY b.rep_rank, b.id) FILTER (WHERE b.category IS NOT NULL))[1] AS category,
        (array_agg(b.image_url ORDER BY b.rep_rank, b.id) FILTER (WHERE b.image_url IS NOT NULL))[1] AS image_url,
        bool_or(b.all_day) AS all_day,
        max(b.duplicate_group) AS duplicate_group,
        max(b.duplicate_group_representative) AS duplicate_group_representative,
        array_agg(b.id ORDER BY b.id) AS merged_ids,
        b.group_key
    FROM base b
    GROUP BY b.city, b.start_time, b.group_key
)
SELECT
    r.id,
    r.title,
    r.start_time,
    r.end_time,
    r.url,
    r.location,
    r.description,
    COALESCE(n.source, '') AS source,
    r.source_uid,
    r.created_at,
    r.updated_at,
    r.city,
    r.transcript,
    r.source_id,
    r.cluster_id,
    u.source_urls,
    r.category,
    ic.ics_categories,
    r.image_url,
    r.all_day,
    r.duplicate_group,
    r.duplicate_group_representative,
    COALESCE(n.source_names, ARRAY[]::text[]) AS source_names,
    r.merged_ids
FROM rolled r
LEFT JOIN name_agg n USING (city, start_time, group_key)
LEFT JOIN url_agg u USING (city, start_time, group_key)
LEFT JOIN ics_categories_pick ic USING (city, start_time, group_key)
ORDER BY r.start_time;

-- Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY.
CREATE UNIQUE INDEX IF NOT EXISTS deduplicated_events_id_idx ON deduplicated_events (id);
CREATE INDEX IF NOT EXISTS deduplicated_events_city_start_time_idx ON deduplicated_events (city, start_time);

GRANT SELECT ON deduplicated_events TO anon, authenticated, service_role;

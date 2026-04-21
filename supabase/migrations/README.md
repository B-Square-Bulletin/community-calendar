# Supabase Migrations

This directory contains the ordered schema changes needed to move an existing instance forward.

## Purpose

Migration files are the authoritative change history for the database.

Use them for:
- creating tables, indexes, policies, functions, and views
- altering or dropping existing objects
- backfills and data corrections that are part of a schema rollout

Do not treat `supabase/ddl/` as the way to upgrade an existing database. Those files describe the intended current state, but they do not describe how to get there safely from an older state.

## Naming

Use timestamp-prefixed, descriptive filenames matching the Supabase CLI convention:

- `20260330191500_add_city_column.sql`
- `20260421182300_optimize_deduplicated_events_index.sql`

The timestamp format is `YYYYMMDDHHMMSS`. This allows `supabase db push` to apply them in order and track which have been applied.

## Applying migrations

### Option A: SQL Editor (simplest)

Paste the contents of the migration file into the Supabase SQL Editor and run it. All migrations use `IF EXISTS` / `IF NOT EXISTS` guards so they're safe to re-run.

### Option B: Supabase CLI

The CLI tracks applied migrations in a `supabase_migrations.schema_migrations` table and only runs new ones.

```bash
# One-time setup (from the repo root)
supabase login
supabase link --project-ref <your-project-ref>

# If your instance already has earlier migrations applied manually,
# mark them as applied so the CLI doesn't try to re-run them:
supabase migration repair 20260330191500 --status applied

# Apply all unapplied migrations
supabase db push
```

The CLI looks for migration files in `supabase/migrations/` relative to the current working directory. Run commands from the repo root, or use `--workdir` to point elsewhere.

## Workflow

For every schema change:

1. Add a migration file.
2. Apply it to the main instance.
3. Verify app and function behavior.
4. Update the matching `supabase/ddl/` files so they reflect the new live state.
5. Communicate to fork maintainers that they need to apply the new migration(s).

## Destructive changes

Prefer staged rollouts:

1. Add the new structure.
2. Migrate data and code.
3. Remove old structure in a later migration.

This keeps upstream and forked instances easier to sync.

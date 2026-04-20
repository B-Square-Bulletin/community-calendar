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

Use ordered, descriptive filenames, for example:

- `002_create_feeds_table.sql`
- `003_add_source_names_rpc.sql`
- `004_make_event_enrichments_private.sql`

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

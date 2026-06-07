# Local Testing Setup

This directory contains local testing infrastructure for the community calendar database functions.

## Quick Start

```bash
# Start local Supabase and apply migrations
make setup-local

# Or manually:
supabase start
supabase db reset

# Run tests
./tests/sql/run_tests_local.sh

# Stop when done
supabase stop
```

## Files

- `test_refresh_source_names.sql` - Test suite for `refresh_source_names()` function
- `run_tests_local.sh` - Test runner (supports --local or --linked)

## Why Local Testing?

Running tests against production is risky. Local testing via `supabase start` gives you:
- Isolated database that can be reset anytime
- No risk to production data
- Faster iteration (no network latency)
- Can test destructive operations safely

## Configuration

The `supabase/config.toml` has migrations enabled. The schema is defined in:
- `supabase/migrations/20260101000000_initial_schema.sql` - Base schema
- `supabase/migrations/202603*` and later - Incremental changes

Running `supabase db reset` applies all migrations in order.

## Troubleshooting

**If `supabase start` fails:**
```bash
supabase stop
docker system prune -f
supabase start
```

**If tests fail with "relation does not exist":**
```bash
supabase db reset
```

**To reset local DB completely:**
```bash
supabase db reset
```

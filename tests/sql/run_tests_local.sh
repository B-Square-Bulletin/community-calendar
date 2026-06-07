#!/bin/bash
# Run tests for refresh_source_names() function
# Usage:
#   ./run_tests_local.sh          # runs against local Supabase
#   ALLOW_PROD_TESTS=1 ./run_tests_local.sh --linked  # runs against production (destructive!)

set -euo pipefail

MODE="${1:---local}"

if [ "$MODE" = "--local" ]; then
  echo "Running tests against LOCAL Supabase instance..."

  # Dependency check: jq is required to parse `supabase status` JSON
  if ! command -v jq > /dev/null 2>&1; then
    echo "ERROR: 'jq' is not installed but is required to parse the local DB URL."
    echo "Install it with: brew install jq  (macOS)  |  apt-get install jq  (Debian/Ubuntu)"
    exit 1
  fi

  # Check if running
  if ! supabase status > /dev/null 2>&1; then
    echo "Starting Supabase..."
    supabase start
  else
    echo "Supabase is already running."
  fi
  echo ""

  # Get local database URL
  DB_URL=$(supabase status --output json | jq -r '.DB_URL')

  if [ -z "$DB_URL" ] || [ "$DB_URL" = "null" ]; then
    echo "ERROR: Could not get local database URL"
    exit 1
  fi

  echo "Running test suite..."
  psql "$DB_URL" -f tests/sql/test_refresh_source_names.sql

  echo ""
  echo "Local instance still running. To stop: supabase stop"
else
  echo "⚠️  WARNING: Running tests against PRODUCTION database"
  echo "   The test suite begins by DELETING rows from 'events' and 'source_names'."

  # Explicit opt-in guard: prevents accidental destructive runs from a fat-fingered arg
  if [ "${ALLOW_PROD_TESTS:-}" != "1" ]; then
    echo "ERROR: Refusing to run against production without an explicit opt-in."
    echo "Set ALLOW_PROD_TESTS=1 to acknowledge this is destructive, e.g.:"
    echo "  ALLOW_PROD_TESTS=1 $0 --linked"
    exit 1
  fi

  read -p "Are you sure? (yes/no): " confirm
  if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
  fi

  echo "Running test suite against production..."
  # For production, we need to use psql with SUPABASE_DB_URL
  if [ -z "${SUPABASE_DB_URL:-}" ]; then
    echo "ERROR: SUPABASE_DB_URL not set"
    echo "Set it to your production database connection string"
    exit 1
  fi

  psql "$SUPABASE_DB_URL" -f tests/sql/test_refresh_source_names.sql
fi

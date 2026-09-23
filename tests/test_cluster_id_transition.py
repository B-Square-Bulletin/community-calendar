#!/usr/bin/env python3
"""Deployment-ordering contract for the legacy ``cluster_id`` (#155).

Consumers move to ``duplicate_group`` first. The cleanup migration is deliberately
not part of this deploy, so one compatibility build can still read the legacy
column before a separately verified cleanup migration removes it.

The chain being pinned:

1. The additive migration introduces ``duplicate_group`` while the view still
   exposes ``cluster_id`` for the compatibility build.
2. No cleanup migration ships in this deploy.
3. Nothing on the active build path produces or loads ``cluster_id``; consumers
   use ``duplicate_group`` while the database remains backward compatible.

The artifact half lives in ``tests/test_confidence_route.py::
TestIcsBoundary::test_artifact_omits_retired_cluster_id``. The database
compatibility half is covered by the migration view definition and the regular
database view tests.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent
MIGRATIONS = ROOT / "supabase" / "migrations"


def _migration_files():
    return sorted(MIGRATIONS.glob("*.sql"), key=lambda path: path.name)


def _additive_migration():
    """The migration that introduces the route's persisted grouping field."""
    matches = [
        path
        for path in _migration_files()
        if "ADD COLUMN IF NOT EXISTS duplicate_group" in path.read_text()
    ]
    assert matches, "no migration adds events.duplicate_group"
    return matches[0]


def test_compatibility_build_keeps_cluster_id_in_the_view():
    """The consumer switch must not remove the legacy field in this deploy."""
    sql = _additive_migration().read_text()
    assert "cluster_id" in sql
    assert "duplicate_group" in sql


def test_cluster_id_cleanup_is_deferred_to_a_later_deploy():
    """A cleanup migration would close the required compatibility window."""
    cleanup = [
        path.name
        for path in _migration_files()
        if "DROP COLUMN IF EXISTS cluster_id" in path.read_text()
    ]
    assert cleanup == []


def test_new_migration_ddl_is_rerunnable():
    """SQL Editor reruns must use the documented object-existence guards."""
    sql = _additive_migration().read_text()
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS deduplicated_events" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS deduplicated_events_id_idx" in sql
    assert "CREATE INDEX IF NOT EXISTS deduplicated_events_city_start_time_idx" in sql


def test_retired_field_has_no_producer_or_loader_path():
    """The drop is only safe because nothing still produces or reads the field.

    The build's artifact writer must not emit ``cluster_id`` and the loader
    must not name it, so the only grouping key that can reach storage is
    ``duplicate_group``. (The behavioral artifact assertion lives in
    ``tests/test_confidence_route.py``.)
    """
    producer = (ROOT / "scripts" / "ics_to_json.py").read_text()
    assert "cluster_id" not in producer
    assert "cluster_by_title_similarity" not in producer

    loader = (ROOT / "supabase" / "functions" / "load-events" / "index.ts").read_text()
    assert "cluster_id" not in loader

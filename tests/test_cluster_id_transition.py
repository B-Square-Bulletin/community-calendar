#!/usr/bin/env python3
"""Deployment-ordering contract for retiring the legacy ``cluster_id`` (#155).

Spec-150's 2026-09-22 amendment (L409) allows two resolutions for the
``cluster_id`` transition: restore a one-build compatibility window, or verify
that the consumer switch and the cleanup migration deploy together safely.
This branch chose verification, and this file is the durable pin for that
ordering.

The chain being pinned:

1. The additive migration that introduces ``duplicate_group`` (and the view
   that presents it) sorts *before* the cleanup migration that drops
   ``cluster_id``, so a single ``supabase db push`` can never remove a column a
   consumer still needs.
2. The cleanup migration is terminal: no later migration reintroduces the
   retired field.
3. The cleanup migration rebuilds the authoritative view around
   ``duplicate_group`` (with the NULL-isolation key) instead of the dropped
   column.
4. Nothing on the active path still produces or loads ``cluster_id``, so the
   loader receives only ``duplicate_group``.

The database half of the contract lives in
``supabase/tests/test_cluster_id_retired.sql`` (column and view field absent);
the artifact half lives in ``tests/test_confidence_route.py::
TestIcsBoundary::test_artifact_omits_retired_cluster_id``. Together with this
file they show the drop can land in the same deploy as the consumer switch.
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


def _cleanup_migration():
    """The single migration that removes the retired ``cluster_id`` column."""
    matches = [
        path
        for path in _migration_files()
        if "DROP COLUMN IF EXISTS cluster_id" in path.read_text()
    ]
    assert len(matches) == 1, (
        "expected exactly one migration to drop cluster_id, found "
        f"{[path.name for path in matches]}"
    )
    return matches[0]


def test_additive_migration_lands_before_the_cluster_id_cleanup():
    """The column a consumer needs must exist before the drop runs.

    Migrations apply in filename order, so the additive migration's name must
    sort before the cleanup's. A rename or an earlier destructive migration
    fails here rather than in production.
    """
    names = [path.name for path in _migration_files()]
    additive = _additive_migration().name
    cleanup = _cleanup_migration().name

    assert names.index(additive) < names.index(cleanup), f"{additive} must sort before {cleanup}"


def test_cluster_id_cleanup_is_terminal():
    """No migration after the cleanup may reintroduce the retired field.

    A later reference would mean a second drop is needed (a competing
    producer) or that the cleanup was undone; either way the ordering
    contract no longer holds.
    """
    files = _migration_files()
    cleanup_index = files.index(_cleanup_migration())
    later = [path.name for path in files[cleanup_index + 1 :] if "cluster_id" in path.read_text()]

    assert later == [], f"migrations after the cleanup mention cluster_id: {later}"


def test_cleanup_migration_rebuilds_the_view_around_duplicate_group():
    """The drop and the view rebuild ship together, self-consistently.

    The existing view definition selects ``cluster_id``, so the cleanup must
    drop the view before the column and recreate it around the route's
    ``duplicate_group`` field with the NULL-isolation key.
    """
    sql = _cleanup_migration().read_text()

    assert "DROP MATERIALIZED VIEW IF EXISTS deduplicated_events" in sql
    assert sql.index("DROP MATERIALIZED VIEW") < sql.index("DROP COLUMN IF EXISTS cluster_id")
    assert "CREATE MATERIALIZED VIEW deduplicated_events" in sql
    assert "duplicate_group" in sql
    assert "'row:' || e.id::text" in sql


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

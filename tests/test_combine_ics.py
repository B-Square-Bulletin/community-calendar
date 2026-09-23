#!/usr/bin/env python3
"""combine_ics de-duplication tests (#150 item 7).

combine_ics used to run a title+date cross-source merge (``dedupe_cross_source``)
between UID de-duplication and ICS assembly, so a fuzzy title match could delete
a listing *before* the confidence route ever saw it. That layer is retired: the
only de-duplication combine_ics performs is by UID, and
``scripts/ics_to_json.py``'s route is the one authority on whether two different
listings are one event.

The integration tests below drive the real ``combine_ics_files`` and
``ics_to_json`` boundary: both same-title listings survive combination, and only
the route removes one.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.combine_ics import combine_ics_files, dedupe_by_uid
from scripts.ics_to_json import ics_to_json
from tests.helpers import VTIMEZONE_LA, make_ics, make_vevent

# ===========================================================================
# UID-level de-duplication (the only de-duplication combine_ics keeps)
# ===========================================================================


def _event(uid, title="Heist"):
    if uid is None:
        content = f"SUMMARY:{title}\r\nLOCATION:Waldron Auditorium\r\n"
    else:
        content = f"SUMMARY:{title}\r\nUID:{uid}\r\nLOCATION:Waldron Auditorium\r\n"
    return {"dtstart": None, "content": content}


class TestDedupeByUid:
    def test_keeps_only_the_first_listing_for_a_repeated_uid(self):
        first = _event("dup-uid", title="Early Copy")
        second = _event("dup-uid", title="Late Copy")

        kept = dedupe_by_uid([first, second])

        assert kept == [first]

    def test_listings_without_a_uid_are_never_dropped(self):
        # Missing identity must fail closed upstream in the route, not silently
        # disappear at combination.
        no_uid_a = _event(None, title="No UID A")
        no_uid_b = _event(None, title="No UID B")

        kept = dedupe_by_uid([no_uid_a, no_uid_b])

        assert kept == [no_uid_a, no_uid_b]


# ===========================================================================
# No title-based deletion before the confidence route
# ===========================================================================


def _write_source_ics(tmp_path, name, summary, location, uid, dtstart):
    event = make_vevent(summary, dtstart, "DTEND:20990601T190000Z", uid)
    event = event.replace("END:VEVENT", f"LOCATION:{location}\r\nEND:VEVENT")
    (tmp_path / f"{name}.ics").write_text(make_ics(event, vtimezone=VTIMEZONE_LA), encoding="utf-8")


def _combine(tmp_path):
    """Combine the ICS files in ``tmp_path``; return the combined ICS text."""
    combined = tmp_path / "combined.ics"
    combine_ics_files(tmp_path, combined, "Test Calendar")
    return combined.read_text(encoding="utf-8")


class TestNoTitleDeletionBeforeRoute:
    def test_combine_keeps_same_title_listings_the_route_will_separate(self, tmp_path):
        # Two different venues (incompatible locations) carrying an identical
        # title at the same instant. The old title+date merge would have deleted
        # one here, overriding the location guard before the route ran.
        _write_source_ics(
            tmp_path,
            "alpha",
            "Rescheduled Show",
            "100 Elm St, Bloomington, IN",
            "uid-alpha",
            "DTSTART:20990601T180000Z",
        )
        _write_source_ics(
            tmp_path,
            "beta",
            "Rescheduled Show",
            "100 Elm St, Columbus, OH",
            "uid-beta",
            "DTSTART:20990601T180000Z",
        )

        combined = _combine(tmp_path)
        assert combined.count("BEGIN:VEVENT") == 2

        events = ics_to_json(
            tmp_path / "combined.ics",
            tmp_path / "events.json",
            future_only=False,
            city="bloomington",
        )

        assert {event["source_uid"] for event in events} == {"uid-alpha", "uid-beta"}
        assert all(event["duplicate_group"] is None for event in events)

    def test_route_is_the_only_place_a_same_title_listing_is_deleted(self, tmp_path):
        # Exact title, same instant, compatible locations: the route merges, so
        # the deletion is attributable to the audited exact-title band.
        _write_source_ics(
            tmp_path,
            "gamma",
            "Shared Concert",
            "Musical Arts Center",
            "uid-gamma",
            "DTSTART:20990601T180000Z",
        )
        _write_source_ics(
            tmp_path,
            "delta",
            "Shared Concert",
            "Musical Arts Center, 101 N Eagleson Ave, Bloomington, IN",
            "uid-delta",
            "DTSTART:20990601T180000Z",
        )

        combined = _combine(tmp_path)
        # Combination keeps both; only the route deletes.
        assert combined.count("BEGIN:VEVENT") == 2

        events = ics_to_json(
            tmp_path / "combined.ics",
            tmp_path / "events.json",
            future_only=False,
            city="bloomington",
        )

        assert len(events) == 1
        diagnostics = _route_diagnostics(tmp_path / "events.json")
        assert diagnostics["merge_deleted"] == 1


def _route_diagnostics(events_json):
    sidecar = Path(events_json).with_name(Path(events_json).stem + ".route.json")
    return json.loads(sidecar.read_text())

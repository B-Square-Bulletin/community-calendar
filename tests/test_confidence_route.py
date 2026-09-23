#!/usr/bin/env python3
"""Tests for the build-time confidence route (#150 / #151).

These tests drive the route through its public seam: the pure
``confidence_route`` function and the ``ics_to_json`` ICS boundary. They assert
on the routed outcome (which band a pair lands in, which sources survive a
merge, which group id members share), never on union-find internals.

Expected values come from the spec's worked examples (#145 pairs, the prototype
trap set) and from independently computed token-set scores, so a change in the
route's internals cannot make a test pass by construction.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.ics_to_json import (
    ROUTE_MAX_COMPARISONS,
    ROUTE_MAX_GROUP_SIZE,
    ROUTE_THRESHOLD,
    ROUTE_VERSION,
    RouteInvariantError,
    confidence_route,
    ics_to_json,
    locations_compatible_both,
    locations_compatible_or_empty,
    normalize_route_title,
    structured_source_names,
    validate_route_result,
)
from tests.helpers import VTIMEZONE_LA, make_ics, make_vevent

FIXTURE = Path(__file__).parent / "fixtures/confidence_route/bloomington_2026-09-21_27.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ev(
    source_uid,
    title,
    start_time="2026-10-01T19:00:00-04:00",
    location="",
    source="Source A",
    url="",
    all_day=None,
    source_urls=None,
):
    event = {
        "source_uid": source_uid,
        "title": title,
        "start_time": start_time,
        "location": location,
        "source": source,
        "url": url,
        "all_day": all_day,
    }
    if source_urls is not None:
        event["source_urls"] = source_urls
    return event


def by_uid(result):
    return {outcome.source_uid: outcome for outcome in result.outcomes}


def surviving_uids(result):
    return {event.get("source_uid") for event in result.events}


# ===========================================================================
# Pure route: Merge
# ===========================================================================


class TestMerge:
    def test_exact_title_merge_uses_full_cleaned_title(self):
        """The #145 Cook-Off pair merges: same cleaned full title, compatible locations."""
        events = [
            ev(
                "iu-cookoff",
                "\u201cThe Cook-Off\u201d \u2013 Music by Shawn E. Okpebholo; Libretto by Mark Campbell",
                location="Musical Arts Center & LIVE@jacobs",
                source="IU Jacobs School of Music",
            ),
            ev(
                "vb-cookoff",
                "\u201cThe Cook-Off\u201d \u2013 Music by Shawn E. Okpebholo; Libretto by Mark Campbell",
                location="Musical Arts Center, 101 N Eagleson Ave, Bloomington, IN 47406",
                source="Visit Bloomington",
            ),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        assert len(result.events) == 1
        assert outcomes["iu-cookoff"].outcome == "merge"
        assert outcomes["vb-cookoff"].outcome == "merge"
        assert outcomes["vb-cookoff"].survivor_uid == "iu-cookoff"

    def test_merge_requires_both_locations_present(self):
        """Identical title, same instant, one empty location => no deletion."""
        events = [
            ev("a", "Trivia Night", location="The Back Door, 207 S College Ave"),
            ev("b", "Trivia Night", location=""),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        assert len(result.events) == 2
        assert result.diagnostics["merge_deleted"] == 0
        assert outcomes["a"].outcome != "merge"
        assert outcomes["b"].outcome != "merge"

    def test_merge_requires_compatible_locations(self):
        """Identical title at two incompatible venues stays two rows (Separate)."""
        events = [
            ev(
                "a",
                "Community Band Spring Concert",
                location="Buskirk-Chumley Theater, 114 E Kirkwood Ave, Bloomington",
            ),
            ev(
                "b",
                "Community Band Spring Concert",
                location="First United Methodist Church, 219 E 4th St, Bloomington",
            ),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        assert len(result.events) == 2
        assert outcomes["a"].outcome == "separate"
        assert outcomes["b"].outcome == "separate"
        assert outcomes["a"].duplicate_group is None

    def test_merge_survivor_is_input_order_independent(self):
        events = [
            ev("b", "Exact Title", location="Venue, 1 Main St"),
            ev("a", "Exact Title", location="Venue, 1 Main St"),
        ]
        forward = by_uid(confidence_route(events))
        backward = by_uid(confidence_route(list(reversed(events))))
        assert forward["a"].survivor_uid == backward["a"].survivor_uid
        survivors_forward = {o.survivor_uid for o in forward.values() if o.survivor_uid}
        survivors_backward = {o.survivor_uid for o in backward.values() if o.survivor_uid}
        assert survivors_forward == survivors_backward == {"a"}

    def test_identical_title_different_instants_stay_separate(self):
        """Two sessions of one workshop on one day are two events, not one."""
        events = [
            ev(
                "a",
                "It's On Us: Bystander Intervention Workshop",
                start_time="2026-09-21T18:00:00-04:00",
            ),
            ev(
                "b",
                "It's On Us: Bystander Intervention Workshop",
                start_time="2026-09-21T20:00:00-04:00",
            ),
        ]
        result = confidence_route(events)
        assert len(result.events) == 2
        assert result.diagnostics["merge_deleted"] == 0
        assert by_uid(result)["a"].outcome == "separate"

    def test_location_guard_disabled_allows_incompatible_merge(self):
        events = [
            ev(
                "a",
                "Community Band Spring Concert",
                location="Buskirk-Chumley Theater, 114 E Kirkwood Ave, Bloomington",
            ),
            ev(
                "b",
                "Community Band Spring Concert",
                location="First United Methodist Church, 219 E 4th St, Bloomington",
            ),
        ]
        guarded = confidence_route(events, location_guard=True)
        unguarded = confidence_route(events, location_guard=False)
        assert guarded.diagnostics["merge_deleted"] == 0
        assert unguarded.diagnostics["merge_deleted"] == 1

    def test_merge_survivor_prefers_primary_over_aggregator(self):
        """A primary source wins even when the aggregator has the smaller uid."""
        events = [
            ev(
                "zzz-primary",
                "Exact Title",
                location="Venue, 1 Main St",
                source="IU Jacobs School of Music",
                source_urls={"IU Jacobs School of Music": "http://primary"},
            ),
            ev(
                "aaa-aggregator",
                "Exact Title",
                location="Venue, 1 Main St",
                source="WFIU Community Calendar",
                source_urls={"WFIU Community Calendar": "http://agg"},
            ),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        assert len(result.events) == 1
        assert outcomes["aaa-aggregator"].survivor_uid == "zzz-primary"
        assert result.events[0]["source"] == "IU Jacobs School of Music, WFIU Community Calendar"

    def test_merge_folds_structured_source_urls(self):
        events = [
            ev(
                "a",
                "Exact Title",
                location="Venue, 1 Main St",
                source="IU Jacobs School of Music",
                source_urls={"IU Jacobs School of Music": "http://primary"},
            ),
            ev(
                "b",
                "Exact Title",
                location="Venue, 1 Main St",
                source="WFIU Community Calendar",
                url="http://agg",
                source_urls={"WFIU Community Calendar": "http://agg"},
            ),
        ]
        result = confidence_route(events)
        survivor = result.events[0]
        assert survivor["source_urls"] == {
            "IU Jacobs School of Music": "http://primary",
            "WFIU Community Calendar": "http://agg",
        }


# ===========================================================================
# Pure route: Group
# ===========================================================================


class TestGroup:
    def test_threshold_boundary_groups_at_080_not_at_090(self):
        """The Wine & Paint pair scores 0.857: groups at 0.80, not at 0.90."""
        events = [
            ev(
                "bc-wine1",
                "Wine & Paint Saturday Night",
                location="20 N Van Buren St, Nashville, IN 47448",
            ),
            ev(
                "bc-wine2",
                "Wine & Paint Saturdays",
                location="20 N Van Buren St, Nashville, IN 47448",
            ),
        ]
        at_default = by_uid(confidence_route(events, threshold=0.80))
        at_strict = by_uid(confidence_route(events, threshold=0.90))
        assert at_default["bc-wine1"].outcome == "group"
        assert at_strict["bc-wine1"].outcome == "separate"

    def test_group_requires_same_instant(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", start_time="2026-10-01T19:00:00-04:00"),
            ev("b", "Wine & Paint Saturdays", start_time="2026-10-01T21:00:00-04:00"),
        ]
        outcomes = by_uid(confidence_route(events))
        assert outcomes["a"].outcome == "separate"
        assert outcomes["b"].outcome == "separate"

    def test_group_uses_true_instant_across_zone_spellings(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", start_time="2026-10-01T18:00:00+00:00"),
            ev("b", "Wine & Paint Saturdays", start_time="2026-10-01T14:00:00-04:00"),
        ]
        result = confidence_route(events)
        assert result.diagnostics["groups"] == 1
        assert by_uid(result)["a"].duplicate_group is not None

    def test_group_is_transitive_over_a_chain(self):
        events = [
            ev("chain-a", "Beginner Pottery Class", location="Clay Studio, 123 W 6th St"),
            ev(
                "chain-b", "Beginner Pottery Class for Adults", location="Clay Studio, 123 W 6th St"
            ),
            ev("chain-c", "Pottery Class for Adults", location="Clay Studio, 123 W 6th St"),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        groups = {outcomes[uid].duplicate_group for uid in ("chain-a", "chain-b", "chain-c")}
        assert len(groups) == 1
        assert None not in groups
        assert result.diagnostics["max_group_size"] == 3

    def test_empty_location_pair_groups(self):
        events = [
            ev("trivia-a", "Trivia Night w/Bloomington Pub Quiz", location=""),
            ev("trivia-b", "Trivia Night w/Bloomington Pub Quiz!", location=""),
        ]
        result = confidence_route(events)
        assert result.diagnostics["groups"] == 1
        assert by_uid(result)["trivia-a"].outcome == "group"

    def test_variant_guard_blocks_squad_variants(self):
        events = [
            ev("jv", "Greencastle Girls JV Soccer @ Martinsville", location=""),
            ev("varsity", "Greencastle Girls Varsity Soccer @ Martinsville", location=""),
        ]
        guarded = confidence_route(events, variant_guard=True)
        unguarded = confidence_route(events, variant_guard=False)
        assert by_uid(guarded)["jv"].outcome == "separate"
        assert by_uid(unguarded)["jv"].outcome == "group"

    def test_timed_only_guard_blocks_all_day_listings(self):
        events = [
            ev(
                "a",
                "Wine & Paint Saturday Night",
                start_time="2026-10-01T00:00:00-04:00",
                all_day=True,
            ),
            ev(
                "b",
                "Wine & Paint Saturdays",
                start_time="2026-10-01T00:00:00-04:00",
                all_day=True,
            ),
        ]
        guarded = confidence_route(events, timed_only_guard=True)
        unguarded = confidence_route(events, timed_only_guard=False)
        assert by_uid(guarded)["a"].outcome == "separate"
        assert by_uid(unguarded)["a"].outcome == "group"

    def test_timed_midnight_event_with_all_day_false_still_groups(self):
        """The all_day flag wins over the midnight fallback."""
        events = [
            ev(
                "a",
                "Wine & Paint Saturday Night",
                start_time="2026-10-01T00:00:00-04:00",
                all_day=False,
            ),
            ev(
                "b",
                "Wine & Paint Saturdays",
                start_time="2026-10-01T00:00:00-04:00",
                all_day=False,
            ),
        ]
        result = confidence_route(events)
        assert by_uid(result)["a"].outcome == "group"

    def test_all_day_exact_title_still_merges(self):
        """All-day listings participate in the exact-title Merge band."""
        events = [
            ev(
                "a",
                "The Declaration of Independence",
                start_time="2026-10-01T00:00:00-04:00",
                location="LILLY LIBRARY",
                all_day=True,
            ),
            ev(
                "b",
                "The Declaration of Independence",
                start_time="2026-10-01T00:00:00-04:00",
                location="LILLY LIBRARY",
                all_day=True,
            ),
        ]
        result = confidence_route(events)
        assert result.diagnostics["merge_deleted"] == 1


# ===========================================================================
# Pure route: persisted representative and structured source names (#152)
# ===========================================================================


class TestRoutePersistedContract:
    """The route persists the structured decision the view and RSS consume.

    ``duplicate_group_representative`` and ``source_names`` are what let the
    database view pick the route's canonical representative and union source
    names without splitting ambiguous comma-joined text.
    """

    def test_group_representative_is_the_route_priority_survivor(self):
        events = [
            ev(
                "zzz-aggregator",
                "Wine & Paint Saturday Night",
                source="WFIU Community Calendar",
                url="http://agg",
                source_urls={"WFIU Community Calendar": "http://agg"},
            ),
            ev(
                "aaa-primary",
                "Wine & Paint Saturdays",
                source="IU Jacobs School of Music",
                url="http://primary",
                source_urls={"IU Jacobs School of Music": "http://primary"},
            ),
        ]
        result = confidence_route(events)
        reps = {e["source_uid"]: e.get("duplicate_group_representative") for e in result.events}
        assert reps == {"aaa-primary": "aaa-primary", "zzz-aggregator": "aaa-primary"}

    def test_group_representative_is_input_order_independent(self):
        forward = [
            ev("a", "Wine & Paint Saturday Night", source="Source A"),
            ev("b", "Wine & Paint Saturdays", source="Source B"),
        ]
        backward = [forward[1], forward[0]]
        first = {
            e["source_uid"]: e["duplicate_group_representative"]
            for e in confidence_route(forward).events
        }
        second = {
            e["source_uid"]: e["duplicate_group_representative"]
            for e in confidence_route(backward).events
        }
        assert first == second
        assert first["a"] == first["b"] == "a"

    def test_separate_rows_carry_no_representative(self):
        events = [
            ev("a", "Trivia Night", location="The Back Door"),
            ev("b", "Yoga in the Park", location="Schulz Museum"),
        ]
        result = confidence_route(events)
        assert all(e["duplicate_group"] is None for e in result.events)
        assert all(e["duplicate_group_representative"] is None for e in result.events)

    def test_merged_survivor_carries_ordered_structured_source_names(self):
        events = [
            ev(
                "iu",
                "The Cook-Off",
                location="Musical Arts Center",
                source="IU Jacobs School of Music",
                source_urls={"IU Jacobs School of Music": "http://iu"},
            ),
            ev(
                "wfiu",
                "The Cook-Off",
                location="Musical Arts Center",
                source="WFIU Community Calendar",
                source_urls={"WFIU Community Calendar": "http://wfiu"},
            ),
        ]
        result = confidence_route(events)
        assert len(result.events) == 1
        survivor = result.events[0]
        assert survivor["source_uid"] == "iu"
        # Primaries keep the route order ahead of aggregators, and the merged
        # survivor's names come from the folded component, not the source text.
        assert survivor["source_names"] == ["IU Jacobs School of Music", "WFIU Community Calendar"]

    def test_grouped_member_carries_its_structured_source_names_unsplit(self):
        events = [
            ev(
                "a",
                "Wine & Paint Saturday Night",
                source="Taste, Inc.",
                source_urls={"Taste, Inc.": "http://t"},
            ),
            ev("b", "Wine & Paint Saturdays", source="Other"),
        ]
        result = confidence_route(events)
        by = {e["source_uid"]: e for e in result.events}
        assert by["a"]["duplicate_group"] is not None
        assert by["a"]["source_names"] == ["Taste, Inc."]


# ===========================================================================
# Pure route: Separate authority and no propagation
# ===========================================================================


class TestSeparateAuthority:
    def test_similarity_edge_never_deletes(self):
        """A==B exact, B~C similar: C survives and groups with the survivor."""
        events = [
            ev("a", "Wine & Paint Saturday Night", location="20 N Van Buren St, Nashville"),
            ev("b", "Wine & Paint Saturday Night", location="20 N Van Buren St, Nashville"),
            ev("c", "Wine & Paint Saturdays", location="20 N Van Buren St, Nashville"),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        assert "c" in surviving_uids(result)
        assert outcomes["c"].outcome == "group"
        assert outcomes["b"].outcome == "merge"
        assert outcomes["c"].duplicate_group == outcomes["a"].duplicate_group

    def test_different_programmes_sharing_words_stay_separate(self):
        """Common words are not evidence of sameness."""
        events = [
            ev("coffee", "Community Coffee Tasting", location="BloomingTea, 208 S Rogers St"),
            ev("yoga", "Community Yoga", location="BloomingTea, 208 S Rogers St"),
        ]
        result = confidence_route(events)
        assert result.diagnostics["groups"] == 0
        assert by_uid(result)["coffee"].outcome == "separate"

    def test_truncation_collision_does_not_merge(self):
        """Shared 40-char prefix must not delete a row (empty locations)."""
        events = [
            ev(
                "trunc-a",
                "Spring Concert And Community Band Celebration Tonight Downtown",
                location="",
            ),
            ev(
                "trunc-b",
                "Spring Concert And Community Band Celebration Tonight Downtown Encore",
                location="",
            ),
        ]
        result = confidence_route(events)
        assert len(result.events) == 2
        assert result.diagnostics["merge_deleted"] == 0

    def test_truncation_trap_with_identical_full_title_still_merges(self):
        """Full-title equality (not a 40-char prefix) drives Merge."""
        title = "Spring Concert And Community Band Celebration Tonight Downtown Encore"
        events = [
            ev("a", title, location="Venue, 1 Main St"),
            ev("b", title, location="Venue, 1 Main St"),
        ]
        result = confidence_route(events)
        assert result.diagnostics["merge_deleted"] == 1


# ===========================================================================
# Pure route: identity, determinism, versioned ids
# ===========================================================================


class TestIdentityAndIds:
    def test_missing_source_uid_is_neither_merged_nor_grouped(self):
        events = [
            ev("", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        result = confidence_route(events)
        outcomes = by_uid(result)
        assert outcomes[""].outcome == "separate"
        assert outcomes["b"].outcome == "separate"
        assert result.diagnostics["missing_identity"] == 1

    def test_validate_fails_closed_on_missing_identity(self):
        events = [ev("", "Solo Event", location="")]
        result = confidence_route(events)
        with pytest.raises(RouteInvariantError) as excinfo:
            validate_route_result(result)
        assert "missing source_uid" in str(excinfo.value)

    def test_group_id_is_versioned_and_deterministic(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        first = confidence_route(events)
        second = confidence_route(list(reversed(events)))
        group_id = by_uid(first)["a"].duplicate_group
        assert group_id is not None
        assert group_id.startswith(f"{ROUTE_VERSION}-")
        assert by_uid(second)["a"].duplicate_group == group_id

    def test_group_id_changes_when_membership_changes(self):
        pair = [
            ev("a", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        trio = [
            *pair,
            ev("c", "Wine & Paint Saturday", location="Venue"),
        ]
        pair_id = by_uid(confidence_route(pair))["a"].duplicate_group
        trio_id = by_uid(confidence_route(trio))["a"].duplicate_group
        assert pair_id is not None and trio_id is not None
        assert pair_id != trio_id

    def test_route_is_idempotent(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        first = confidence_route(events)
        second = confidence_route(first.events)
        assert by_uid(second)["a"].duplicate_group == by_uid(first)["a"].duplicate_group


# ===========================================================================
# Pure route: invariants fail closed
# ===========================================================================


class TestInvariants:
    def test_excessive_group_size_fails_closed(self):
        events = [
            ev("a", "Beginner Pottery Class", location="Clay Studio, 123 W 6th St"),
            ev("b", "Beginner Pottery Class for Adults", location="Clay Studio, 123 W 6th St"),
            ev("c", "Pottery Class for Adults", location="Clay Studio, 123 W 6th St"),
        ]
        result = confidence_route(events, max_group_size=2)
        with pytest.raises(RouteInvariantError) as excinfo:
            validate_route_result(result)
        assert "component size" in str(excinfo.value)

    def test_excessive_comparisons_fails_closed(self):
        events = [
            ev("a", "Beginner Pottery Class", location="Clay Studio, 123 W 6th St"),
            ev("b", "Beginner Pottery Class for Adults", location="Clay Studio, 123 W 6th St"),
            ev("c", "Pottery Class for Adults", location="Clay Studio, 123 W 6th St"),
        ]
        result = confidence_route(events, max_comparisons=1)
        with pytest.raises(RouteInvariantError) as excinfo:
            validate_route_result(result)
        assert "comparison" in str(excinfo.value)

    def test_clean_route_passes_validation(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        validate_route_result(confidence_route(events))

    def test_group_without_a_single_member_representative_fails_closed(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        result = confidence_route(events)
        for event in result.events:
            event["duplicate_group_representative"] = None
        with pytest.raises(RouteInvariantError) as excinfo:
            validate_route_result(result)
        assert "representative" in str(excinfo.value)

    def test_representative_that_is_not_a_member_fails_closed(self):
        events = [
            ev("a", "Wine & Paint Saturday Night", location="Venue"),
            ev("b", "Wine & Paint Saturdays", location="Venue"),
        ]
        result = confidence_route(events)
        for event in result.events:
            event["duplicate_group_representative"] = "ghost"
        with pytest.raises(RouteInvariantError) as excinfo:
            validate_route_result(result)
        assert "representative" in str(excinfo.value)


# ===========================================================================
# Location and source primitives
# ===========================================================================


class TestPrimitives:
    def test_normalize_route_title_keeps_the_whole_string(self):
        long_a = "Spring Concert And Community Band Celebration Tonight Downtown"
        long_b = long_a + " Encore"
        assert normalize_route_title(long_a) != normalize_route_title(long_b)

    def test_normalize_route_title_strips_leading_article(self):
        assert normalize_route_title("The Sam Grisman Project") == normalize_route_title(
            "Sam Grisman Project"
        )

    def test_merge_location_requires_both_sides(self):
        assert locations_compatible_both("", "Bloomington") is False
        assert locations_compatible_or_empty("", "Bloomington") is True

    def test_source_name_containing_comma_is_not_split(self):
        event = ev("a", "Title", source="Taste, Inc.", source_urls=None)
        assert structured_source_names(event) == ["Taste, Inc."]

    def test_structured_sources_prefer_url_map_keys(self):
        event = ev(
            "a",
            "Title",
            source="Primary, Secondary",
            source_urls={"Primary": "http://p", "Secondary": "http://s"},
        )
        assert structured_source_names(event) == ["Primary", "Secondary"]

    def test_single_source_name_wins_over_a_divergent_url_map_key(self):
        """A lone source string is the name; only a comma-joined string defers.

        The URL map's keys come from the ICS-assembly fallback name, which can
        be a slug ("Events Livewhale 135") while the stored ``source`` is the
        human name. Preferring the map key would surface the slug in the view.
        """
        event = ev(
            "a",
            "Title",
            source="IU Hamilton Lugar School",
            source_urls={"Events Livewhale 135": "http://x"},
        )
        assert structured_source_names(event) == ["IU Hamilton Lugar School"]


# ===========================================================================
# ICS boundary seam
# ===========================================================================


class TestIcsBoundary:
    def _write_ics(self, tmp_path, block):
        ics = make_ics(block, vtimezone=VTIMEZONE_LA)
        path = tmp_path / "combined.ics"
        path.write_text(ics, encoding="utf-8")
        return path

    def test_encoded_summary_merges_with_decoded_copy(self, tmp_path):
        """The #145 root-cause fix: cleaning before the Merge equality test."""
        event_a = make_vevent(
            '"The Cook-Off" - Music',
            "DTSTART:20260919T210000Z",
            "DTEND:20260919T220000Z",
            "uid-a",
        )
        event_b = make_vevent(
            "&#8220;The Cook-Off&#8221; &#8211; Music",
            "DTSTART:20260919T210000Z",
            "DTEND:20260919T220000Z",
            "uid-b",
        )
        # Locations differ in spelling but are compatible; source names come last
        # so the ICS text stays valid.
        event_a = event_a.replace(
            "END:VEVENT", "LOCATION:Musical Arts Center & LIVE@jacobs\r\nEND:VEVENT"
        )
        event_b = event_b.replace(
            "END:VEVENT",
            "LOCATION:Musical Arts Center, 101 N Eagleson Ave, Bloomington, IN 47406\r\nEND:VEVENT",
        )
        ics_path = self._write_ics(tmp_path, event_a + event_b)
        out_path = tmp_path / "events.json"

        events = ics_to_json(ics_path, out_path, future_only=False, city="bloomington")

        assert len(events) == 1
        assert events[0]["source_uid"] == "uid-a"
        diagnostics = json.loads((tmp_path / "events.route.json").read_text())
        assert diagnostics["version"] == ROUTE_VERSION
        assert diagnostics["merge_deleted"] == 1
        assert diagnostics["threshold"] == ROUTE_THRESHOLD

    def test_artifact_carries_duplicate_group_for_groups(self, tmp_path):
        event_a = make_vevent(
            "Wine & Paint Saturday Night",
            "DTSTART:20261001T190000Z",
            "DTEND:20261001T210000Z",
            "uid-a",
        )
        event_b = make_vevent(
            "Wine & Paint Saturdays",
            "DTSTART:20261001T190000Z",
            "DTEND:20261001T210000Z",
            "uid-b",
        )
        event_a = event_a.replace("END:VEVENT", "LOCATION:Venue, 20 N Van Buren St\r\nEND:VEVENT")
        event_b = event_b.replace("END:VEVENT", "LOCATION:Venue, 20 N Van Buren St\r\nEND:VEVENT")
        ics_path = self._write_ics(tmp_path, event_a + event_b)
        out_path = tmp_path / "events.json"

        events = ics_to_json(ics_path, out_path, future_only=False, city="bloomington")

        assert len(events) == 2
        group_ids = {event["duplicate_group"] for event in events}
        assert len(group_ids) == 1
        assert None not in group_ids

    def test_artifact_omits_retired_cluster_id(self, tmp_path):
        """#155: the build emits one grouping authority, not the dead column.

        ``cluster_id`` was the legacy per-timeslot similarity index. Every
        consumer now reads ``duplicate_group``, so the build must not write a
        competing field into the artifact the loader upserts.
        """
        event = make_vevent(
            "Solo Show",
            "DTSTART:20261002T190000Z",
            "DTEND:20261002T210000Z",
            "uid-solo",
        )
        ics_path = self._write_ics(tmp_path, event)
        out_path = tmp_path / "events.json"

        events = ics_to_json(ics_path, out_path, future_only=False, city="bloomington")

        assert events
        for artifact_event in events:
            assert "cluster_id" not in artifact_event
            assert "duplicate_group" in artifact_event


# ===========================================================================
# Blast radius over the real built artifact
# ===========================================================================


class TestBlastRadius:
    def test_real_fixture_route_invariants(self):
        """Route the real (sliced) artifact; fail loudly on any invariant breach.

        The fixture is a one-week slice of the production Bloomington
        ``events.json`` (1,029 listings) kept small enough to commit. It
        exercises real merge/group pairs, so a regression that deletes a row
        without an exact-title survivor or explodes a similarity chain fails
        here rather than in production.
        """
        events = json.loads(FIXTURE.read_text())
        assert events and all(event.get("source_uid") for event in events)

        result = confidence_route(events)
        validate_route_result(result)

        diagnostics = result.diagnostics
        assert diagnostics["version"] == ROUTE_VERSION
        assert diagnostics["merge_deleted"] >= 1
        assert diagnostics["groups"] >= 1
        assert diagnostics["max_group_size"] <= ROUTE_MAX_GROUP_SIZE
        assert diagnostics["comparisons"] <= ROUTE_MAX_COMPARISONS

        survivors = surviving_uids(result)
        for outcome in result.outcomes:
            if outcome.outcome == "merge" and outcome.source_uid not in survivors:
                assert outcome.survivor_uid in survivors

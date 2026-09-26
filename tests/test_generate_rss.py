#!/usr/bin/env python3
"""Tests for the RSS consumer of the stored confidence-route decisions (#154).

The RSS generator is a pure consumer: it must render one item per stored
``duplicate_group``, using the route's ``duplicate_group_representative`` and
never recomputing similarity, location, or grouping. These tests drive the feed
artifact through ``generate`` and read the written XML, so they assert on what a
reader actually receives rather than on internal helpers.

Two consecutive builds share state through the previous build's ``-full.xml``,
which is why the tests write each build to its own outdir and pass the earlier
outdir as the later build's state directory.
"""

import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.generate_rss import generate

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
NEXT_DAY = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
START = "2026-10-01T19:00:00+00:00"


def ev(uid, title, group=None, representative=None, start=START):
    return {
        "source_uid": uid,
        "title": title,
        "start_time": start,
        "location": "Venue, 1 Main St",
        "source": "Source A",
        "url": f"https://example.com/{uid}",
        "all_day": False,
        "duplicate_group": group,
        "duplicate_group_representative": representative,
    }


def read_items(path):
    root = ET.fromstring(path.read_text())
    return [
        {
            "title": item.findtext("title"),
            "link": item.findtext("link"),
            "guid": item.findtext("guid"),
            "pubDate": item.findtext("pubDate"),
            "categories": [cat.text for cat in item.findall("category")],
        }
        for item in root.findall("./channel/item")
    ]


def test_full_feed_renders_one_item_per_stored_group(tmp_path):
    events = [
        ev("uid-a", "Wine & Paint Saturday Night", "cr1-abc", "uid-a"),
        ev("uid-b", "Wine and Paint Saturdays", "cr1-abc", "uid-a"),
        ev("uid-c", "Wine & Paint Saturday", "cr1-abc", "uid-a"),
        ev("uid-d", "Unrelated Concert"),
    ]

    generate("bloomington", events, tmp_path, tmp_path, NOW)

    items = read_items(tmp_path / "bloomington-full.xml")
    assert {item["guid"] for item in items} == {"uid-a", "uid-d"}

    # The Group renders the route's canonical representative, and the members
    # suppressed from rendering stay visible as item categories so the next
    # build still knows about them.
    grouped = next(item for item in items if item["guid"] == "uid-a")
    assert (grouped["title"] or "").startswith("Wine & Paint Saturday Night")
    assert grouped["categories"] == ["uid-b", "uid-c"]


def test_null_group_rows_stay_separate(tmp_path):
    """A NULL duplicate_group is one row is one group — never collapsed."""
    events = [
        ev("uid-a", "Community Band Concert"),
        ev("uid-b", "Community Band Concert"),
    ]

    generate("bloomington", events, tmp_path, tmp_path, NOW)

    items = read_items(tmp_path / "bloomington-full.xml")
    assert {item["guid"] for item in items} == {"uid-a", "uid-b"}


def test_grouping_uses_the_stored_decision_not_title_similarity(tmp_path):
    """Identical titles left Separate stay two items; different titles the
    route Grouped collapse to one. RSS must not recompute grouping."""
    events = [
        ev("uid-a", "Community Band Concert"),
        ev("uid-b", "Community Band Concert"),
        ev("uid-c", "Wine & Paint Night", "cr1-xyz", "uid-c"),
        ev("uid-d", "Painting with Wine Evening", "cr1-xyz", "uid-c"),
    ]

    generate("bloomington", events, tmp_path, tmp_path, NOW)

    items = read_items(tmp_path / "bloomington-full.xml")
    assert {item["guid"] for item in items} == {"uid-a", "uid-b", "uid-c"}


def test_second_build_with_unchanged_membership_announces_nothing_new(tmp_path):
    events = [
        ev("uid-a", "Wine & Paint Saturday Night", "cr1-abc", "uid-a"),
        ev("uid-b", "Wine and Paint Saturdays", "cr1-abc", "uid-a"),
    ]
    build1 = tmp_path / "build1"
    build2 = tmp_path / "build2"

    generate("bloomington", events, build1, build1, NOW)
    first_full = read_items(build1 / "bloomington-full.xml")
    first_latest = read_items(build1 / "bloomington-latest.xml")
    assert len(first_full) == 1
    assert [item["pubDate"] for item in first_latest] == [format_datetime(NOW)]

    generate("bloomington", events, build2, build1, NEXT_DAY)

    # Still one item per Group in the full feed…
    assert len(read_items(build2 / "bloomington-full.xml")) == 1
    # …and the still-upcoming Group is carried with its first-seen pubDate,
    # not re-announced as new on the second build.
    second_latest = read_items(build2 / "bloomington-latest.xml")
    assert [item["pubDate"] for item in second_latest] == [format_datetime(NOW)]


def test_new_member_joining_a_group_is_announced(tmp_path):
    """Newness considers every member UID, including suppressed ones."""
    build1 = tmp_path / "build1"
    build2 = tmp_path / "build2"

    generate(
        "bloomington",
        [
            ev("uid-a", "Wine & Paint Saturday Night", "cr1-abc", "uid-a"),
            ev("uid-b", "Wine and Paint Saturdays", "cr1-abc", "uid-a"),
        ],
        build1,
        build1,
        NOW,
    )
    generate(
        "bloomington",
        [
            ev("uid-a", "Wine & Paint Saturday Night", "cr1-abc", "uid-a"),
            ev("uid-b", "Wine and Paint Saturdays", "cr1-abc", "uid-a"),
            ev("uid-c", "Wine & Paint Saturday", "cr1-abc", "uid-a"),
        ],
        build2,
        build1,
        NEXT_DAY,
    )

    latest = read_items(build2 / "bloomington-latest.xml")
    assert [item["pubDate"] for item in latest] == [format_datetime(NEXT_DAY)]
    assert latest[0]["guid"] == "uid-a"

    grouped = next(
        item for item in read_items(build2 / "bloomington-full.xml") if item["guid"] == "uid-a"
    )
    assert grouped["categories"] == ["uid-b", "uid-c"]


def test_representative_change_without_membership_change_is_not_reannounced(tmp_path):
    build1 = tmp_path / "build1"
    build2 = tmp_path / "build2"

    generate(
        "bloomington",
        [
            ev("uid-a", "Wine & Paint Saturday Night", "cr1-abc", "uid-a"),
            ev("uid-b", "Wine and Paint Saturdays", "cr1-abc", "uid-a"),
        ],
        build1,
        build1,
        NOW,
    )
    generate(
        "bloomington",
        [
            ev("uid-a", "Wine & Paint Saturday Night", "cr1-abc", "uid-b"),
            ev("uid-b", "Wine and Paint Saturdays", "cr1-abc", "uid-b"),
        ],
        build2,
        build1,
        NEXT_DAY,
    )

    # Same membership, so nothing is new; the representative can change the
    # rendered GUID without re-announcing the Group.
    latest = read_items(build2 / "bloomington-latest.xml")
    assert latest == []

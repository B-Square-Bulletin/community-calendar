"""One ICS text rule (#251).

Every writer and reader imports it, so a title that holds a bare carriage
return cannot split a property line in one output path and survive in another.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.lib.ics_text import escape_ics, unescape_ics
from scripts.ics_to_json import ics_to_json
from tests.helpers import make_ics, make_vevent

ICS_TITLE = "Fright\\, Night\\nPart 2"


def test_a_bare_carriage_return_is_escaped_as_a_line_break():
    assert escape_ics("Fright\rNight") == "Fright\\nNight"


def test_escape_covers_every_reserved_character():
    assert escape_ics("path\\to; a,b\nc\rd") == "path\\\\to\\; a\\,b\\nc\\nd"


def test_unescape_reverses_escape_in_one_pass():
    # "\\n" is a literal backslash followed by n, not an escaped newline.
    assert unescape_ics("a\\\\nb") == "a\\nb"
    assert unescape_ics("a\\nb") == "a\nb"
    assert unescape_ics("a\\,b\\;c\\\\d") == "a,b;c\\d"


def test_json_artifact_and_feed_agree_on_the_same_title(tmp_path):
    event = make_vevent(
        ICS_TITLE, "DTSTART:20301031T190000Z", "DTEND:20301031T210000Z", "ics-text-1"
    )
    ics_path = tmp_path / "ics_text.ics"
    ics_path.write_text(make_ics(event), encoding="utf-8")

    [stored] = ics_to_json(ics_path, future_only=False)

    # What events.json (the browser's input) renders ...
    assert stored["title"] == "Fright, Night\nPart 2"
    # ... is exactly what the one escaping rule puts back into an ICS feed.
    assert escape_ics(stored["title"]) == ICS_TITLE
    assert unescape_ics(escape_ics(stored["title"])) == stored["title"]

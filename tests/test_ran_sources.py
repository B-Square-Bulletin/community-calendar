#!/usr/bin/env python3
"""Tests for the shared source-outcome classifier (#285).

One rule decides what a source's bytes are, so the download runner, the
scraper runner, local_build and the report cannot disagree about whether a
source ran, went quiet, or failed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import ran_sources as rs

from tests.helpers import VTIMEZONE_LA, make_ics, make_vevent


def _event():
    return make_vevent(
        "Book club",
        "DTSTART:20990101T190000Z",
        "DTEND:20990101T200000Z",
        "book-club@example.com",
    )


class TestClassify:
    def test_calendar_counts_events(self):
        outcome = rs.classify(make_ics(_event()))
        assert outcome == rs.Outcome(rs.CALENDAR, None, 1)

    def test_quiet_calendar_is_still_a_calendar(self):
        assert rs.classify(make_ics("")) == rs.Outcome(rs.CALENDAR, None, 0)

    def test_cut_off_calendar_is_its_own_kind(self):
        """An opener without a closer is a failed ingestion, not a quiet source."""
        outcome = rs.classify("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n")
        assert outcome.kind == rs.TRUNCATED
        assert outcome.events == 0

    def test_cut_off_inside_a_timezone_is_its_own_kind(self):
        """A body that stops before an inner block closes is a cut-off download."""
        body = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VTIMEZONE\r\nTZID:America/Indiana/Indianapolis\r\n"
        assert rs.classify(body) == rs.Outcome(rs.TRUNCATED, None, 0)

    def test_event_open_when_the_calendar_closes_is_not_a_calendar(self):
        """An event still open when the calendar closes is out of order (#293)."""
        body = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:x\r\nEND:VCALENDAR\r\n"
        assert rs.classify(body) == rs.Outcome(rs.NOT_CALENDAR, "unknown", 0)

    def test_block_page_is_not_calendar_html(self):
        assert rs.classify("<html>Access denied</html>") == rs.Outcome(rs.NOT_CALENDAR, "html", 0)

    def test_json_error_body_is_not_calendar_json(self):
        assert rs.classify('{"error": "rate limited"}') == rs.Outcome(rs.NOT_CALENDAR, "json", 0)

    def test_json_body_quoting_both_markers_is_not_a_calendar(self):
        """Both marker strings inside a JSON body are not a calendar (#293)."""
        body = '{"body": "BEGIN:VCALENDAR END:VCALENDAR"}'
        assert rs.classify(body) == rs.Outcome(rs.NOT_CALENDAR, "json", 0)

    def test_empty_body_is_not_calendar_empty(self):
        assert rs.classify("") == rs.Outcome(rs.NOT_CALENDAR, "empty", 0)

    def test_unrecognized_body_is_not_calendar_unknown(self):
        assert rs.classify("Service unavailable") == rs.Outcome(rs.NOT_CALENDAR, "unknown", 0)

    def test_end_before_any_begin_is_not_a_calendar(self):
        body = "BEGIN:VCALENDAR\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        assert rs.classify(body) == rs.Outcome(rs.NOT_CALENDAR, "unknown", 0)

    def test_block_page_before_the_calendar_is_not_a_calendar(self):
        body = "<html>Access denied</html>\r\n" + make_ics(_event())
        assert rs.classify(body) == rs.Outcome(rs.NOT_CALENDAR, "html", 1)

    def test_junk_after_the_calendar_is_not_a_calendar(self):
        body = make_ics(_event()) + "<html>oops</html>\r\n"
        assert rs.classify(body) == rs.Outcome(rs.NOT_CALENDAR, "html", 1)

    def test_concatenated_calendars_are_a_calendar(self):
        """The extractor reads every VEVENT, so two calendars is still one body."""
        body = make_ics(_event()) + make_ics(_event())
        assert rs.classify(body) == rs.Outcome(rs.CALENDAR, None, 2)

    def test_mixed_case_component_names_are_a_calendar(self):
        """Block names are case-insensitive; the extractor still reads the VEVENT."""
        body = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VTIMEZONE\r\n"
            "begin:STANDARD\r\n"
            "DTSTART:20241103T020000\r\n"
            "END:STANDARD\r\n"
            "END:VTIMEZONE\r\n" + _event() + "END:VCALENDAR\r\n"
        )
        assert rs.classify(body) == rs.Outcome(rs.CALENDAR, None, 1)

    def test_lowercase_calendar_markers_are_a_calendar(self):
        body = "begin:vcalendar\r\n" + _event() + "end:vcalendar\r\n"
        assert rs.classify(body) == rs.Outcome(rs.CALENDAR, None, 1)

    def test_lowercase_event_markers_are_not_a_calendar(self):
        """combine_ics reads only uppercase VEVENT markers, so these are unreadable."""
        body = (
            "BEGIN:VCALENDAR\r\n"
            "begin:vevent\r\n"
            "DTSTART:20990101T190000Z\r\n"
            "UID:x@example.com\r\n"
            "end:vevent\r\n"
            "END:VCALENDAR\r\n"
        )
        assert rs.classify(body) == rs.Outcome(rs.NOT_CALENDAR, "unknown", 0)

    def test_nested_components_are_a_calendar(self):
        body = make_ics(_event(), vtimezone=VTIMEZONE_LA)
        assert rs.classify(body) == rs.Outcome(rs.CALENDAR, None, 1)

    def test_a_folded_line_is_not_structure(self):
        body = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "DESCRIPTION:first\r\n"
            " BEGIN:VEVENT\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        assert rs.classify(body) == rs.Outcome(rs.CALENDAR, None, 1)

    def test_a_unicode_separator_inside_a_value_is_not_a_line_break(self):
        """U+2028 is ordinary ICS text, so it cannot open a phantom block."""
        body = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "SUMMARY:Agenda\u2028BEGIN:VALARM\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        assert rs.classify(body) == rs.Outcome(rs.CALENDAR, None, 1)

    def test_byte_order_mark_and_leading_blank_lines_are_ignored(self):
        assert rs.classify("\ufeff" + make_ics(_event())) == rs.Outcome(rs.CALENDAR, None, 1)
        assert rs.classify("\r\n\r\n" + make_ics(_event())) == rs.Outcome(rs.CALENDAR, None, 1)


@pytest.mark.parametrize(
    "path", sorted(Path(__file__).parent.glob("fixtures/*/*.ics")), ids=lambda p: p.name
)
def test_checked_in_calendars_still_classify_as_calendars(path):
    """Every legitimate calendar in the tree passes the structural rule."""
    assert rs.classify_file(path).kind == rs.CALENDAR


class TestClassifyFile:
    def test_reads_a_calendar_file(self, tmp_path):
        path = tmp_path / "feed.ics"
        path.write_text(make_ics(_event()))
        assert rs.classify_file(path).kind == rs.CALENDAR

    def test_missing_file_is_unreadable(self, tmp_path):
        assert rs.classify_file(tmp_path / "absent.ics") == rs.Outcome(rs.UNREADABLE)


class TestRecordRan:
    """record_ran is the only manifest writer and the only gate."""

    def _write(self, tmp_path, body):
        path = tmp_path / "cities" / "bloomington" / "feed.ics"
        path.parent.mkdir(parents=True)
        path.write_text(body)
        return path

    def test_calendar_is_recorded_and_reported(self, tmp_path):
        path = self._write(tmp_path, make_ics(""))
        assert rs.record_ran(path).kind == rs.CALENDAR
        assert (path.parent / rs.FILENAME).read_text() == "feed\n"

    def test_cut_off_calendar_is_refused(self, tmp_path):
        path = self._write(tmp_path, "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n")
        assert rs.record_ran(path).kind == rs.TRUNCATED
        assert not (path.parent / rs.FILENAME).exists()

    @pytest.mark.parametrize(
        "body",
        [
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:x\r\nEND:VCALENDAR\r\n",
            '{"body": "BEGIN:VCALENDAR END:VCALENDAR"}',
        ],
        ids=["unclosed-event", "json-quoting-markers"],
    )
    def test_malformed_bodies_are_refused(self, tmp_path, body):
        """The write gate refuses both bodies from #293, not just a bad verdict."""
        path = self._write(tmp_path, body)
        assert rs.record_ran(path).kind != rs.CALENDAR
        assert not (path.parent / rs.FILENAME).exists()

    def test_block_page_is_refused(self, tmp_path):
        path = self._write(tmp_path, "<html>Access denied</html>")
        assert rs.record_ran(path).kind == rs.NOT_CALENDAR
        assert not (path.parent / rs.FILENAME).exists()

    def test_missing_file_is_refused(self, tmp_path):
        path = tmp_path / "cities" / "bloomington" / "absent.ics"
        assert rs.record_ran(path).kind == rs.UNREADABLE
        assert not (path.parent / rs.FILENAME).exists()

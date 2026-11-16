#!/usr/bin/env python3
"""Tests for the shared source-outcome classifier (#285).

One rule decides what a source's bytes are, so the download runner, the
scraper runner, local_build and the report cannot disagree about whether a
source ran, went quiet, or failed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import ran_sources as rs

from tests.helpers import make_ics, make_vevent


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
        assert outcome.events == 1

    def test_block_page_is_not_calendar_html(self):
        assert rs.classify("<html>Access denied</html>") == rs.Outcome(rs.NOT_CALENDAR, "html", 0)

    def test_json_error_body_is_not_calendar_json(self):
        assert rs.classify('{"error": "rate limited"}') == rs.Outcome(rs.NOT_CALENDAR, "json", 0)

    def test_empty_body_is_not_calendar_empty(self):
        assert rs.classify("") == rs.Outcome(rs.NOT_CALENDAR, "empty", 0)

    def test_unrecognized_body_is_not_calendar_unknown(self):
        assert rs.classify("Service unavailable") == rs.Outcome(rs.NOT_CALENDAR, "unknown", 0)


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

    def test_block_page_is_refused(self, tmp_path):
        path = self._write(tmp_path, "<html>Access denied</html>")
        assert rs.record_ran(path).kind == rs.NOT_CALENDAR
        assert not (path.parent / rs.FILENAME).exists()

    def test_missing_file_is_refused(self, tmp_path):
        path = tmp_path / "cities" / "bloomington" / "absent.ics"
        assert rs.record_ran(path).kind == rs.UNREADABLE
        assert not (path.parent / rs.FILENAME).exists()

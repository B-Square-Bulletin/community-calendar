#!/usr/bin/env python3
"""Tests for local_build's output summary (#285).

`summarize_output` publishes the four statuses the audit report and the
`fix` action list read, so the mapping from a classified file to a status is
worth pinning: a cut-off or unreadable file must land in `not_ics`, never in
the zero-event review queue.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import local_build

from tests.helpers import make_ics, make_vevent


def _event():
    return make_vevent(
        "Book club",
        "DTSTART:20990101T190000Z",
        "DTEND:20990101T200000Z",
        "book-club@example.com",
    )


class TestSummarizeOutput:
    def _summarize(self, tmp_path, monkeypatch, body=None):
        monkeypatch.setattr(local_build, "ROOT", tmp_path)
        path = tmp_path / "feed.ics"
        if body is not None:
            path.write_text(body)
        return local_build.summarize_output(path)

    def test_missing_file_is_missing(self, tmp_path, monkeypatch):
        summary = self._summarize(tmp_path, monkeypatch)
        assert summary["status"] == "missing"
        assert summary["exists"] is False
        assert "content_kind" not in summary

    def test_quiet_calendar_is_no_events(self, tmp_path, monkeypatch):
        summary = self._summarize(tmp_path, monkeypatch, make_ics(""))
        assert (summary["status"], summary["events"]) == ("no_events", 0)

    def test_calendar_with_events_is_ok(self, tmp_path, monkeypatch):
        summary = self._summarize(tmp_path, monkeypatch, make_ics(_event()))
        assert (summary["status"], summary["events"]) == ("ok", 1)

    def test_block_page_is_not_ics_html(self, tmp_path, monkeypatch):
        summary = self._summarize(tmp_path, monkeypatch, "<html>Access denied</html>")
        assert (summary["status"], summary["content_kind"]) == ("not_ics", "html")

    def test_cut_off_calendar_is_not_ics_truncated(self, tmp_path, monkeypatch):
        summary = self._summarize(tmp_path, monkeypatch, "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n")
        assert (summary["status"], summary["content_kind"]) == ("not_ics", "truncated")

    def test_unreadable_path_is_not_ics_unreadable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(local_build, "ROOT", tmp_path)
        path = tmp_path / "feed.ics"
        path.mkdir()
        summary = local_build.summarize_output(path)
        assert (summary["status"], summary["content_kind"]) == ("not_ics", "unreadable")

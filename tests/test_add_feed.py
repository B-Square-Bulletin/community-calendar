#!/usr/bin/env python3
"""Tests for the feed registration smoke test (scripts/add_feed.py, #285).

The registration test now shares the build's source-outcome rule, so a body
that opens a calendar without closing it is rejected at registration time
instead of being fetched as a valid feed.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import add_feed

from tests.helpers import make_ics, make_vevent


def _respond(monkeypatch, body: str) -> None:
    monkeypatch.setattr(add_feed.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=body))


class TestTestFeed:
    def test_complete_calendar_is_accepted(self, monkeypatch):
        _respond(
            monkeypatch,
            make_ics(
                make_vevent(
                    "Book club",
                    "DTSTART:20990101T190000Z",
                    "DTEND:20990101T200000Z",
                    "book-club@example.com",
                )
            ),
        )
        assert add_feed.test_feed("https://example.com/feed.ics") == (True, 1)

    def test_cut_off_calendar_is_rejected(self, monkeypatch):
        _respond(monkeypatch, "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n")
        assert add_feed.test_feed("https://example.com/feed.ics") == (False, 0)

    def test_block_page_is_rejected(self, monkeypatch):
        _respond(monkeypatch, "<html>Access denied</html>")
        assert add_feed.test_feed("https://example.com/feed.ics") == (False, 0)

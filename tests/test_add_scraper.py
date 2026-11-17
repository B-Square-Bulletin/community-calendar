#!/usr/bin/env python3
"""Tests for the DB-first scraper registration helper (scripts/add_scraper.py).

`add_scraper.py` smoke-tests the exact command it is about to register under a
120s timeout. That is too short for a source that crawls a large listing, so the
harness arms environment-only test bounds (``SCRAPE_MONTHS``,
``SCRAPER_TEST_PAGE_CAP``). They are passed through the process environment, not
the command line, so the registered command itself stays unbounded.

The smoke test shares the build's source-outcome rule (#288), so only a
complete calendar is registrable: an HTML page, a JSON body, an empty body or a
cut-off calendar fails it, while a valid calendar with zero events still
registers with a warning.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import add_scraper

from tests.helpers import make_ics, make_vevent

OUTPUT = add_scraper.TEST_OUTPUT
SCRAPER = Path("scrapers/wfiu_community_calendar.py")


def _event():
    return make_vevent(
        "Book club",
        "DTSTART:20990101T190000Z",
        "DTEND:20990101T200000Z",
        "book-club@example.com",
    )


def _run_writing(monkeypatch, body: str) -> None:
    def fake_run(cmd, **kwargs):
        OUTPUT.write_text(body)
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(add_scraper.subprocess, "run", fake_run)


class TestSmokeTestBounds:
    def test_smoke_test_arms_environment_only_bounds(self, monkeypatch):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs["env"]
            OUTPUT.write_text(make_ics(""))
            return SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(add_scraper.subprocess, "run", fake_run)

        ok = add_scraper.test_scraper(SCRAPER, "")

        assert ok is True
        assert captured["env"]["SCRAPE_MONTHS"] == "2"
        assert captured["env"]["SCRAPER_TEST_PAGE_CAP"] == "1"
        # The bounds are env-only; the registered command must not carry them.
        assert not any("SCRAPER_TEST_PAGE_CAP" in str(arg) for arg in captured["cmd"])


class TestNonCalendarOutput:
    @pytest.mark.parametrize(
        ("body", "reason"),
        [
            ("<html>Access denied</html>", "html"),
            ('{"error": "rate limited"}', "json"),
            ("", "empty"),
            # CONTEXT.md reserves "truncation" for the horizon, so the printed
            # reason names the cut-off body instead of echoing the kind.
            ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n", "cut-off calendar"),
        ],
        ids=["html", "json", "empty", "cut-off"],
    )
    def test_not_a_complete_calendar_fails_and_says_why(self, monkeypatch, capsys, body, reason):
        _run_writing(monkeypatch, body)

        assert add_scraper.test_scraper(SCRAPER, "") is False
        assert f"not a usable ICS calendar ({reason})" in capsys.readouterr().out

    def test_leftover_file_cannot_pass_for_a_silent_run(self, monkeypatch, capsys):
        OUTPUT.write_text(make_ics(_event()))
        monkeypatch.setattr(
            add_scraper.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stderr=""),
        )

        assert add_scraper.test_scraper(SCRAPER, "") is False
        # The stale file was cleared before the run, not classified.
        assert "did not produce output file" in capsys.readouterr().out

    def test_valid_calendar_with_no_events_still_registers(self, monkeypatch, capsys):
        _run_writing(monkeypatch, make_ics(""))

        assert add_scraper.test_scraper(SCRAPER, "") is True
        assert "0 events" in capsys.readouterr().out

    def test_valid_calendar_with_events_registers(self, monkeypatch, capsys):
        _run_writing(monkeypatch, make_ics(_event()))

        assert add_scraper.test_scraper(SCRAPER, "") is True
        assert "1 events" in capsys.readouterr().out

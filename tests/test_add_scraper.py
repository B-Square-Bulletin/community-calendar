#!/usr/bin/env python3
"""Tests for the DB-first scraper registration helper (scripts/add_scraper.py).

`add_scraper.py` smoke-tests the exact command it is about to register under a
120s timeout. That is too short for a source that crawls a large listing, so the
harness arms environment-only test bounds (``SCRAPE_MONTHS``,
``SCRAPER_TEST_PAGE_CAP``). They are passed through the process environment, not
the command line, so the registered command itself stays unbounded.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import add_scraper


class TestSmokeTestBounds:
    def test_smoke_test_arms_environment_only_bounds(self, monkeypatch):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs["env"]
            Path("/tmp/scraper_test.ics").write_text("BEGIN:VEVENT\nEND:VEVENT\n")
            return SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr(add_scraper.subprocess, "run", fake_run)

        ok = add_scraper.test_scraper(Path("scrapers/wfiu_community_calendar.py"), "")

        assert ok is True
        assert captured["env"]["SCRAPE_MONTHS"] == "2"
        assert captured["env"]["SCRAPER_TEST_PAGE_CAP"] == "1"
        # The bounds are env-only; the registered command must not carry them.
        assert not any("SCRAPER_TEST_PAGE_CAP" in str(arg) for arg in captured["cmd"])

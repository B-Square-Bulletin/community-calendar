#!/usr/bin/env python3
"""Tests for the Bloomington Brewing sitemap parse (#243)."""

import sys
from pathlib import Path

import pytest

# Add project root to path so scraper imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

import scrapers.bloomington_brewing as bb
from scrapers.bloomington_brewing import BloomingtonBrewingScraper


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, body: bytes) -> None:
    monkeypatch.setattr(bb, "urlopen", lambda req, timeout: _FakeResponse(body))


def test_non_sitemap_body_fails_without_writing_a_calendar(tmp_path, monkeypatch):
    _serve(monkeypatch, b"<html><body>blocked</body></html>")
    out = tmp_path / "brew.ics"

    with pytest.raises(RuntimeError, match="no <loc> entries"):
        BloomingtonBrewingScraper().run(str(out))

    assert not out.exists()


def test_sitemap_without_event_urls_stays_quiet(tmp_path, monkeypatch):
    _serve(
        monkeypatch,
        b"<urlset><url><loc>https://bloomingtonbrew.com/about</loc></url></urlset>",
    )
    out = tmp_path / "brew.ics"

    BloomingtonBrewingScraper().run(str(out))

    ics = out.read_text()
    assert "BEGIN:VCALENDAR" in ics
    assert "VEVENT" not in ics

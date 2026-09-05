#!/usr/bin/env python3
"""Tests for download_feeds.py retry/throttle behavior.

Locks down the 429 retry path and the same-host throttle so rate-limited
sources (events.in.gov / Localist) stop flapping between "a good build" and
"serving html, not ICS" — the alternating pass/fail signature from the report.
"""

import email.message
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import urllib.error

import download_feeds as df
import pytest


def _rate_limited(req) -> urllib.error.HTTPError:
    """Build the HTTPError urllib raises for an HTTP 429 response."""
    return urllib.error.HTTPError(
        req.full_url, 429, "Too Many Requests", email.message.Message(), None
    )


class _Resp:
    """Minimal urllib success-response stand-in."""

    def __init__(self, body=b""):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class TestRateLimitRetry:
    def test_retries_then_recovers_on_429(self, monkeypatch):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise _rate_limited(req)
            return _Resp(b"BEGIN:VEVENT\r\nEND:VEVENT\r\n")

        monkeypatch.setattr(df.urllib.request, "urlopen", fake_urlopen)

        body = df._download_body("https://fake.example/ics")
        assert body.count(b"BEGIN:VEVENT") == 1
        assert calls["n"] == 3

    def test_exhausted_retries_raise(self, monkeypatch):
        def always_429(req, timeout=None):
            raise _rate_limited(req)

        monkeypatch.setattr(df.urllib.request, "urlopen", always_429)

        with pytest.raises(df._RateLimited):
            df._download_body("https://fake.example/ics")


class TestHostThrottle:
    def test_host_of_extracts_netloc(self):
        assert df._host_of("https://events.in.gov/search/events.ics") == "events.in.gov"
        assert df._host_of("https://calendar.google.com/ical/x") == "calendar.google.com"

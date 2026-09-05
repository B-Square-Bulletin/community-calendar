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
    def _no_backoff_sleep(self, monkeypatch):
        # tenacity's nap sleep calls the global time.sleep; make the
        # exponential backoff instant so retry tests don't wait ~24s.
        monkeypatch.setattr(df.time, "sleep", lambda _s: None)

    def test_retries_then_recovers_on_429(self, monkeypatch):
        self._no_backoff_sleep(monkeypatch)
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

    def test_retries_then_recovers_on_503(self, monkeypatch):
        self._no_backoff_sleep(monkeypatch)
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError(
                    req.full_url, 503, "Service Unavailable", email.message.Message(), None
                )
            return _Resp(b"BEGIN:VEVENT\r\nEND:VEVENT\r\n")

        monkeypatch.setattr(df.urllib.request, "urlopen", fake_urlopen)

        body = df._download_body("https://fake.example/ics")
        assert body.count(b"BEGIN:VEVENT") == 1
        assert calls["n"] == 3

    def test_exhausted_retries_raise(self, monkeypatch):
        self._no_backoff_sleep(monkeypatch)

        def always_429(req, timeout=None):
            raise _rate_limited(req)

        monkeypatch.setattr(df.urllib.request, "urlopen", always_429)

        with pytest.raises(df._RateLimited):
            df._download_body("https://fake.example/ics")


class TestHostThrottle:
    def test_host_of_extracts_netloc(self):
        assert df._host_of("https://events.in.gov/search/events.ics") == "events.in.gov"
        assert df._host_of("https://calendar.google.com/ical/x") == "calendar.google.com"

    def test_interleaved_same_host_is_throttled(self, monkeypatch):
        sleeps: list[float] = []
        now = {"t": 10.0}

        def fake_now():
            now["t"] += 1.0
            return now["t"]

        def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(df.time, "monotonic", fake_now)
        monkeypatch.setattr(df.time, "sleep", fake_sleep)

        last_request_at: dict[str, float] = {}
        df._wait_for_host("events.in.gov", last_request_at)  # t=11
        df._wait_for_host("calendar.google.com", last_request_at)  # t=12
        df._wait_for_host("events.in.gov", last_request_at)  # t=13, 2s later

        assert sleeps == []

    def test_same_host_within_window_sleeps(self, monkeypatch):
        sleeps: list[float] = []
        now = {"t": 10.0}

        def fake_now():
            now["t"] += 0.2
            return now["t"]

        def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(df.time, "monotonic", fake_now)
        monkeypatch.setattr(df.time, "sleep", fake_sleep)

        last_request_at: dict[str, float] = {}
        df._wait_for_host("events.in.gov", last_request_at)  # t=10.2
        df._wait_for_host("events.in.gov", last_request_at)  # t=10.4, 0.2s later

        assert 0 < sleeps[0] <= 1.0


class TestCurlFallback:
    def test_non_rate_limited_error_falls_through_to_curl(self, monkeypatch, tmp_path):
        """URLError (DNS/TLS/connection) must not crash the run — curl takes over."""
        outfile = tmp_path / "x.ics"

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(df.urllib.request, "urlopen", fake_urlopen)

        def fake_run(cmd, *args, **kwargs):
            outfile.write_bytes(b"BEGIN:VEVENT\r\nEND:VEVENT\r\n")

        monkeypatch.setattr(df.subprocess, "run", fake_run)

        assert df.fetch_with_curl_fallback("https://fake.example/ics", outfile) is True
        assert outfile.read_bytes().count(b"BEGIN:VEVENT") == 1

    def test_exhausted_retries_fall_through_to_curl(self, monkeypatch, tmp_path):
        """After 429 retries are exhausted, curl still gets a shot."""
        outfile = tmp_path / "x.ics"

        def always_429(req, timeout=None):
            raise _rate_limited(req)

        monkeypatch.setattr(df.urllib.request, "urlopen", always_429)

        def fake_run(cmd, *args, **kwargs):
            outfile.write_bytes(b"BEGIN:VEVENT\r\nEND:VEVENT\r\n")

        monkeypatch.setattr(df.subprocess, "run", fake_run)

        assert df.fetch_with_curl_fallback("https://fake.example/ics", outfile) is True
        assert outfile.read_bytes().count(b"BEGIN:VEVENT") == 1

    def test_stale_outfile_removed_before_fetch(self, monkeypatch, tmp_path):
        """A failed fetch must not leave a prior run's file reported as success."""
        outfile = tmp_path / "x.ics"
        outfile.write_bytes(b"BEGIN:VEVENT\r\nEND:VEVENT\r\n")  # from a prior run

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(df.urllib.request, "urlopen", fake_urlopen)

        # curl also fails: no output written
        monkeypatch.setattr(df.subprocess, "run", lambda cmd, *a, **k: None)

        assert df.fetch_with_curl_fallback("https://fake.example/ics", outfile) is False
        assert not outfile.exists()

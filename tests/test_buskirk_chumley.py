#!/usr/bin/env python3
"""Tests for Buskirk-Chumley Theater scraper."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add project root and scrapers/ to path so scraper imports resolve
_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))
sys.path.insert(0, str(_proj_root / "scrapers"))

from scrapers.buskirk_chumley import BuskirkChumleyScraper  # noqa: E402

# The SiteGround bot-protection challenge the site serves when a request
# comes from a flagged IP (e.g. shared GitHub Actions egress). Instead of
# the events page it returns a meta-refresh to a captcha endpoint.
CAPTCHA_HTML = """\
<html><head><link rel="icon" href="data:;"><meta http-equiv="refresh" \
content="0;/.well-known/sgcaptcha/?r=%2Fevents%2F&y=ipr:52.152.180.196:1788750503.466">\
</meta></head></html>"""

# Minimal HTML with one event tile that the scraper can parse.
# Structure matches what the site serves: div[data-id] > .tile > .thumb + .details
TILE_HTML = """\
<html><body>
<div data-id="abc123">
  <div class="tile">
    <div class="thumb">
      <ul>
        <li>15</li>
        <li>July<br /><small>Tuesday</small></li>
      </ul>
    </div>
    <div class="details">
      <a href="https://buskirkchumley.org/event/test-show/">Test Show</a>
      <span>Test Presenter</span>
      <p>Doors: 6:30 PM / Show: 8:00 PM<br />@ Buskirk-Chumley Theater</p>
    </div>
  </div>
</div>
</body></html>"""


class TestAcceptEncoding:
    """Regression tests for #35: Accept-Encoding header triggers stripped page."""

    def test_accept_encoding_not_in_request_headers(self):
        """Accept-Encoding header must not be sent with requests.

        The SiteGround CDN serves a stripped page (no div[data-id] .tile
        elements) when Accept-Encoding: gzip, deflate is present.  urllib3
        handles transparent decompression regardless, so removing the
        header is safe.  Regression test for issue #35.
        """
        scraper = BuskirkChumleyScraper()
        captured_headers: dict[str, str] = {}

        def intercept_get(_self, url, **kwargs):
            """Replace Session.get — capture headers, return fixture HTML."""
            captured_headers.update(dict(_self.headers))
            mock = Mock()
            mock.text = TILE_HTML
            mock.content = TILE_HTML.encode()
            mock.raise_for_status = Mock()
            return mock

        with patch.object(__import__("requests").Session, "get", intercept_get):
            events = scraper.fetch_events()

        assert "Accept-Encoding" not in captured_headers, (
            "Accept-Encoding header was present in request — "
            "SiteGround CDN will serve stripped page (issue #35)"
        )

        # Also verify we got an event back (the tile was parsed)
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        assert events[0]["title"] == "Test Show"


class TestCaptchaChallenge:
    """fetch_events must not swallow a SiteGround CAPTCHA challenge.

    A `sgcaptcha` redirect from a flagged IP is not an empty calendar; it is
    a block. Returning [] here overwrites a previously-good calendar with 0
    events, silently. Raising surfaces the real failure in CI instead.
    """

    def test_captcha_response_raises(self):
        scraper = BuskirkChumleyScraper()

        def intercept_get(_self, url, **kwargs):
            mock = Mock()
            mock.text = CAPTCHA_HTML
            mock.content = CAPTCHA_HTML.encode()
            mock.raise_for_status = Mock()
            return mock

        with (
            patch.object(__import__("requests").Session, "get", intercept_get),
            pytest.raises(RuntimeError, match="captcha"),
        ):
            scraper.fetch_events()

    def test_no_tiles_but_not_captcha_warns_not_raises(self):
        """An empty page (not a captcha) keeps the existing warn-only path."""
        scraper = BuskirkChumleyScraper()

        def intercept_get(_self, url, **kwargs):
            mock = Mock()
            mock.text = "<html><body>no tiles here</body></html>"
            mock.content = mock.text.encode()
            mock.raise_for_status = Mock()
            return mock

        with patch.object(__import__("requests").Session, "get", intercept_get):
            events = scraper.fetch_events()
        assert events == []

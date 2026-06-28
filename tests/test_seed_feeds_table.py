#!/usr/bin/env python3
"""
Tests for scripts/seed_feeds_table.py — feed normalization helpers.

Run: python -m pytest tests/test_seed_feeds_table.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.seed_feeds_table import _normalize_feed


class TestNormalizeFeed:
    """Tests for _normalize_feed() post-processing of parsed feeds."""

    def test_detects_curator_feed(self):
        """my-picks ICS URLs get feed_type='curator'."""
        feed = {
            'type': 'ics_url',
            'name': 'My Picks',
            'url': 'https://example.supabase.co/functions/v1/my-picks?token=abc',
        }

        result = _normalize_feed(feed, 'bloomington')

        assert result['feed_type'] == 'curator'
        assert result['city'] == 'bloomington'
        assert result['url'] == 'https://example.supabase.co/functions/v1/my-picks?token=abc'
        assert result['type'] == 'ics_url'  # original type preserved

    def test_scraper_url_from_path(self):
        """Scraper with only a path gets url synthesized from that path."""
        feed = {
            'type': 'scraper',
            'name': 'My Scraper',
            'path': 'cities/bloomington/my_scraper.ics',
        }

        result = _normalize_feed(feed, 'bloomington')

        assert result['url'] == 'cities/bloomington/my_scraper.ics'
        assert result['feed_type'] == 'scraper'

    def test_non_curator_ics_unchanged(self):
        """Regular ICS feed without 'my-picks' stays feed_type='ics_url'."""
        feed = {
            'type': 'ics_url',
            'name': 'Regular Feed',
            'url': 'https://example.com/events/?ical=1',
        }

        result = _normalize_feed(feed, 'bloomington')

        assert result['feed_type'] == 'ics_url'
        assert result['url'] == 'https://example.com/events/?ical=1'

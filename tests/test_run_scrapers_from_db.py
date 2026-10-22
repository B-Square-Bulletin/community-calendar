#!/usr/bin/env python3
"""Tests for run_scrapers_from_db.py source_id recording (#232)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import run_scrapers_from_db as rs


def _row(**overrides):
    row = {
        "id": 4,
        "city": "bloomington",
        "url": "cities/bloomington/iu_events.ics",
        "name": "IU Events",
        "feed_type": "scraper",
        "source_ids": [],
    }
    row.update(overrides)
    return row


class TestRecordSourceId:
    def test_patches_the_output_stem(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
        sent: list[tuple[str, dict]] = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            sent.append((req.full_url, json.loads(req.data)))
            return FakeResponse()

        monkeypatch.setattr(rs.urllib.request, "urlopen", fake_urlopen)

        rs.record_source_id(_row(source_ids=["old_stem"]))

        assert sent == [
            (
                "https://fake.supabase.co/rest/v1/feeds?id=eq.4",
                {"source_ids": ["old_stem", "iu_events"]},
            )
        ]

    def test_rows_without_an_id_are_skipped(self, monkeypatch):
        """feeds.txt fallback rows have no DB id, so there is nothing to PATCH."""
        monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")

        def boom(req, timeout=None):
            raise AssertionError("must not PATCH an id-less row")

        monkeypatch.setattr(rs.urllib.request, "urlopen", boom)

        rs.record_source_id(_row(id=None))

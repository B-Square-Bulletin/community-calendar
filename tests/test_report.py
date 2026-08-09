#!/usr/bin/env python3
"""
Tests for the feed health report script.

Run: python -m pytest tests/test_report.py -v
"""

import json
import os
import sys
from pathlib import Path

# Add project root and scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.report import update_report, get_city_timezone, _build_health_payload


class TestStaleCityCleanup:
    """Test that stale cities from upstream are filtered out."""

    def test_removes_cities_not_in_input_list(self, tmp_path):
        """Cities in report.json but not in the cities list get removed."""
        cities_dir = tmp_path / "cities" / "bloomington"
        cities_dir.mkdir(parents=True)

        # Create an empty .ics so the directory has a feed
        (cities_dir / "test_feed.ics").write_text(
            "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        )

        # Create a report.json with multiple cities
        initial_report = {
            "generated": "2026-01-01T00:00:00",
            "cities": {
                "santarosa": {
                    "feeds": {
                        "example": {"history": [{"date": "2026-01-01", "count": 5}]}
                    }
                },
                "bloomington": {
                    "feeds": {
                        "test_feed": {"history": [{"date": "2026-01-01", "count": 3}]}
                    }
                },
                "davis": {
                    "feeds": {
                        "another": {"history": [{"date": "2026-01-01", "count": 10}]}
                    }
                },
            },
            "anomalies": [
                {
                    "city": "santarosa",
                    "feed": "example",
                    "type": "test",
                    "date": "2026-01-01",
                    "message": "old anomaly",
                    "severity": "high",
                },
                {
                    "city": "bloomington",
                    "feed": "test_feed",
                    "type": "test",
                    "date": "2026-01-01",
                    "message": "keep me",
                    "severity": "low",
                },
            ],
        }

        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(initial_report))

        # Run update_report with only bloomington
        cwd = tmp_path
        old_cwd = Path.cwd()
        try:
            os.chdir(cwd)
            update_report(["bloomington"], str(report_path))
        finally:
            os.chdir(old_cwd)

        # Verify result
        result = json.loads(report_path.read_text())

        # Only bloomington should remain
        assert set(result["cities"].keys()) == {"bloomington"}, (
            f"Expected only bloomington, got {set(result['cities'].keys())}"
        )

        # Anomalies: only bloomington's anomaly should remain
        city_names = {a["city"] for a in result["anomalies"]}
        assert city_names == {"bloomington"}, (
            f"Expected only bloomington anomalies, got {city_names}"
        )

    def test_preserves_all_active_cities(self, tmp_path):
        """When two cities are processed, both remain."""
        for city in ["bloomington", "davis"]:
            cities_dir = tmp_path / "cities" / city
            cities_dir.mkdir(parents=True)
            (cities_dir / f"{city}_feed.ics").write_text(
                "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
            )

        initial_report = {
            "generated": "2026-01-01T00:00:00",
            "cities": {
                "bloomington": {"feeds": {"bloomington_feed": {"history": []}}},
                "davis": {"feeds": {"davis_feed": {"history": []}}},
                "santarosa": {"feeds": {"old": {"history": []}}},
            },
            "anomalies": [],
        }

        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(initial_report))

        cwd = tmp_path
        old_cwd = Path.cwd()
        try:
            os.chdir(cwd)
            update_report(["bloomington", "davis"], str(report_path))
        finally:
            os.chdir(old_cwd)

        result = json.loads(report_path.read_text())
        assert set(result["cities"].keys()) == {"bloomington", "davis"}

    def test_new_city_not_in_report_still_added(self, tmp_path):
        """A city not in report.json but in the cities list gets added."""
        cities_dir = tmp_path / "cities" / "newcity"
        cities_dir.mkdir(parents=True)
        (cities_dir / "new_feed.ics").write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")

        initial_report = {
            "generated": "2026-01-01T00:00:00",
            "cities": {"santarosa": {"feeds": {}}},
            "anomalies": [],
        }

        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(initial_report))

        cwd = tmp_path
        old_cwd = Path.cwd()
        try:
            os.chdir(cwd)
            update_report(["newcity"], str(report_path))
        finally:
            os.chdir(old_cwd)

        result = json.loads(report_path.read_text())
        assert "newcity" in result["cities"]
        assert "santarosa" not in result["cities"]


class TestGetCityTimezone:
    """Tests for get_city_timezone() city.conf resolution."""

    def test_returns_none_when_city_conf_missing(self, tmp_path):
        """Returns None when cities/{city}/city.conf does not exist."""
        result = get_city_timezone("nonexistent", _project_root=tmp_path)
        assert result is None

    def test_returns_timezone_from_conf(self, tmp_path):
        """Parses # timezone: line from city.conf."""
        conf_dir = tmp_path / "cities" / "testcity"
        conf_dir.mkdir(parents=True)
        (conf_dir / "city.conf").write_text("# timezone: America/Indianapolis\n")

        result = get_city_timezone("testcity", _project_root=tmp_path)
        assert result == "America/Indianapolis"

    def test_ignores_lines_without_timezone_prefix(self, tmp_path):
        """Only # timezone: lines are parsed; other comments ignored."""
        conf_dir = tmp_path / "cities" / "testcity"
        conf_dir.mkdir(parents=True)
        (conf_dir / "city.conf").write_text(
            "# geo_radius: 20\n# timezone: America/Chicago\n# notes: test\n"
        )

        result = get_city_timezone("testcity", _project_root=tmp_path)
        assert result == "America/Chicago"

    def test_returns_correct_timezone_for_real_city(self):
        """Bloomington's real city.conf returns its configured timezone."""
        result = get_city_timezone("bloomington")
        assert result == "America/Indiana/Indianapolis"


class TestBuildHealthPayload:
    """Tests for _build_health_payload() timezone fallback behavior."""

    def test_warns_and_falls_back_when_city_conf_missing(self, tmp_path):
        """When city.conf is missing, warns and uses DEFAULT_TIMEZONE."""
        report = {
            "cities": {
                "noconf": {
                    "feeds": {
                        "test_feed": {
                            "history": [{"count": 5}],
                        },
                    },
                },
            },
            "anomalies": [],
        }

        payload = _build_health_payload(report, "noconf", _project_root=tmp_path)
        assert payload is not None
        assert payload["city"] == "noconf"
        assert len(payload["feeds"]) == 1
        assert payload["feeds"][0]["feed_type"] == "scraper"  # default
        assert payload["feeds"][0]["checked_date"] is not None

    def test_returns_none_for_unknown_city(self):
        """Returns None when city not in report."""
        report = {"cities": {}, "anomalies": []}
        result = _build_health_payload(report, "ghost")
        assert result is None

    def test_feed_type_from_meta(self, tmp_path):
        """feed_type comes from feeds_meta, defaulting to 'scraper'."""
        # Set up feeds.txt so _load_feeds_meta can resolve
        feeds_dir = tmp_path / "cities" / "withfeeds"
        feeds_dir.mkdir(parents=True)
        (feeds_dir / "feeds.txt").write_text(
            "# My ICS Feed\nhttps://example.com/events/?ical=1\n"
        )

        report = {
            "cities": {
                "withfeeds": {
                    "feeds": {
                        "example": {
                            "history": [{"count": 3}],
                        },
                    },
                },
            },
            "anomalies": [],
        }

        # _load_feeds_meta resolves relative to cwd, so chdir to tmp_path
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            payload = _build_health_payload(report, "withfeeds", _project_root=tmp_path)
            assert payload is not None
            # The ICS feed should have feed_type='ics_url' from feeds.txt
            assert payload["feeds"][0]["feed_type"] == "ics_url"
        finally:
            os.chdir(old_cwd)

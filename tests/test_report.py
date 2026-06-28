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

from scripts.report import update_report, load_report


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
                "santarosa": {"feeds": {"example": {"history": [
                    {"date": "2026-01-01", "count": 5}
                ]}}},
                "bloomington": {"feeds": {"test_feed": {"history": [
                    {"date": "2026-01-01", "count": 3}
                ]}}},
                "davis": {"feeds": {"another": {"history": [
                    {"date": "2026-01-01", "count": 10}
                ]}}},
            },
            "anomalies": [
                {"city": "santarosa", "feed": "example", "type": "test",
                 "date": "2026-01-01", "message": "old anomaly",
                 "severity": "high"},
                {"city": "bloomington", "feed": "test_feed", "type": "test",
                 "date": "2026-01-01", "message": "keep me",
                 "severity": "low"},
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
        (cities_dir / "new_feed.ics").write_text(
            "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        )

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

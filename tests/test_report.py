#!/usr/bin/env python3
"""Tests for the feed-health report's missing-calendar handling.

A source listed in feeds.txt whose .ics is absent after a build produced no
calendar — a blocked scraper or a failed download. The report must keep it as
a failed build so the source stays visible, instead of deleting the entry and
letting the failure go dark.
"""

import json
import sys
from pathlib import Path

# Add project root to path so the scripts package imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import report


def _scraper_reference(*stems: str) -> dict:
    return {
        stem: {"kind": "scraper", "name": stem, "cmd": f"python scrapers/{stem}.py"}
        for stem in stems
    }


def test_expected_source_with_no_calendar_is_reported_not_deleted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cities" / "bloomington").mkdir(parents=True)
    monkeypatch.setattr(
        report, "parse_feeds_reference", lambda city: _scraper_reference("hardtruth")
    )

    report_path = tmp_path / "report.json"
    report.update_report(["bloomington"], report_path=str(report_path))

    saved = json.loads(report_path.read_text())
    assert saved["cities"]["bloomington"]["feeds"]["hardtruth"]["content"] == "no_calendar"

    slice_ = report.build_city_slice(saved, "bloomington", set())
    problems = slice_["problems"]
    assert [i["kind"] for i in problems] == ["no_calendar"]
    assert problems[0]["severity"] == 1
    assert problems[0]["feed"] == "hardtruth"


def test_source_removed_from_feeds_txt_is_dropped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cities" / "bloomington").mkdir(parents=True)
    monkeypatch.setattr(report, "parse_feeds_reference", lambda city: {})

    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "generated": None,
                "cities": {
                    "bloomington": {
                        "feeds": {"retired": {"history": [{"date": "2020-01-01", "count": 3}]}}
                    }
                },
                "anomalies": [],
            }
        )
    )
    report.update_report(["bloomington"], report_path=str(report_path))

    saved = json.loads(report_path.read_text())
    assert "retired" not in saved["cities"]["bloomington"]["feeds"]


def test_present_source_is_not_marked_no_calendar(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    city_dir = tmp_path / "cities" / "bloomington"
    city_dir.mkdir(parents=True)
    (city_dir / "hardtruth.ics").write_text("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n")
    monkeypatch.setattr(
        report, "parse_feeds_reference", lambda city: _scraper_reference("hardtruth")
    )

    report_path = tmp_path / "report.json"
    report.update_report(["bloomington"], report_path=str(report_path))

    saved = json.loads(report_path.read_text())
    feed = saved["cities"]["bloomington"]["feeds"]["hardtruth"]
    assert feed["content"] == "quiet"
    assert report.build_city_slice(saved, "bloomington", set())["problems"] == []

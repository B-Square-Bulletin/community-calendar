#!/usr/bin/env python3
"""Tests for the PR feed/scraper validation script.

The DB-first model registers a scraper through a pending_feeds.txt entry
whose command begins "python scrapers/" (or "python scripts/") and whose
output is cities/<city>/<name>.ics — the feeds-table insert-time trigger
contract in supabase/ddl/16_feeds.sql. The nightly runner executes active
rows from the DB, so the workflow carries no per-scraper lines.

These tests pin that contract: a new-scraper PR with only a pending entry
validates clean (no workflow edit), contract violations are reported, and
ICS-URL entries stay self-contained.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import validate_pr_feeds as vpf

VALID_ENTRY = (
    "# Visit Bloomington\n"
    '# cmd: python scrapers/visit_bloomington.py --name "Visit Bloomington" '
    "--output cities/bloomington/visit_bloomington.ics\n"
    "cities/bloomington/visit_bloomington.ics\n"
)


def _setup(tmp_path, monkeypatch, pending: str, *, scraper_files=(), feeds=None):
    """Point the validator at a tmp repo and return the changed-file entries."""
    monkeypatch.setattr(vpf, "ROOT", tmp_path)
    city = tmp_path / "cities" / "bloomington"
    city.mkdir(parents=True, exist_ok=True)
    (city / "pending_feeds.txt").write_text(pending)
    if feeds is not None:
        (city / "feeds.txt").write_text(feeds)
    for name in scraper_files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# stub\n")


class TestDbFirstScraperEntry:
    def test_new_scraper_pending_entry_validates_clean_without_workflow(
        self, tmp_path, monkeypatch
    ):
        _setup(
            tmp_path,
            monkeypatch,
            VALID_ENTRY,
            scraper_files=["scrapers/visit_bloomington.py"],
        )
        changed = [
            ("M", "cities/bloomington/pending_feeds.txt"),
            ("A", "scrapers/visit_bloomington.py"),
        ]
        monkeypatch.setattr(vpf, "get_changed_file_statuses", lambda base_ref: changed)

        assert vpf.validate("origin/main") == []

    def test_command_violating_trigger_contract_is_flagged(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            monkeypatch,
            "# Visit Bloomington\n"
            "# cmd: python other/visit_bloomington.py --output "
            "cities/bloomington/visit_bloomington.ics\n"
            "cities/bloomington/visit_bloomington.ics\n",
            scraper_files=["other/visit_bloomington.py"],
        )
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("M", "cities/bloomington/pending_feeds.txt")],
        )

        errors = vpf.validate("origin/main")
        assert len(errors) == 1
        assert "DB trigger contract" in errors[0]
        assert "python scrapers/" in errors[0]

    def test_output_violating_trigger_contract_is_flagged(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            monkeypatch,
            "# Visit Bloomington\n"
            "# cmd: python scrapers/visit_bloomington.py --output "
            "cities/Bloomington/visit_bloomington.ics\n"
            "cities/Bloomington/visit_bloomington.ics\n",
            scraper_files=["scrapers/visit_bloomington.py"],
        )
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("M", "cities/bloomington/pending_feeds.txt")],
        )

        errors = vpf.validate("origin/main")
        assert len(errors) == 1
        assert "DB trigger contract" in errors[0]
        assert "cities/<city>/<file>.ics" in errors[0]

    def test_missing_command_is_flagged(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            monkeypatch,
            "# Visit Bloomington\ncities/bloomington/visit_bloomington.ics\n",
            scraper_files=["scrapers/visit_bloomington.py"],
        )
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("M", "cities/bloomington/pending_feeds.txt")],
        )

        errors = vpf.validate("origin/main")
        assert len(errors) == 1
        assert "python scrapers/" in errors[0]

    def test_missing_scraper_file_is_flagged(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch, VALID_ENTRY)
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("M", "cities/bloomington/pending_feeds.txt")],
        )

        errors = vpf.validate("origin/main")
        assert len(errors) == 1
        assert "scrapers/visit_bloomington.py" in errors[0]
        assert "doesn't exist" in errors[0]


class TestIcsUrlEntry:
    def test_ics_url_entry_is_self_contained(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            monkeypatch,
            "# Some Org\nhttps://example.com/events.ics\n",
        )
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("M", "cities/bloomington/pending_feeds.txt")],
        )

        assert vpf.validate("origin/main") == []


class TestNewScraperRegistration:
    def test_new_scraper_without_pending_entry_is_flagged(self, tmp_path, monkeypatch):
        _setup(tmp_path, monkeypatch, "# empty\n", scraper_files=["scrapers/orphan.py"])
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("A", "scrapers/orphan.py")],
        )

        errors = vpf.validate("origin/main")
        assert len(errors) == 1
        assert "scrapers/orphan.py" in errors[0]
        assert "pending_feeds.txt" in errors[0]

    def test_new_scraper_registered_in_feeds_txt_passes(self, tmp_path, monkeypatch):
        _setup(
            tmp_path,
            monkeypatch,
            "# empty\n",
            scraper_files=["scrapers/orphan.py"],
            feeds="# Orphan\ncities/bloomington/orphan.ics\n",
        )
        monkeypatch.setattr(
            vpf,
            "get_changed_file_statuses",
            lambda base_ref: [("A", "scrapers/orphan.py")],
        )

        assert vpf.validate("origin/main") == []


class TestRelevance:
    def test_workflow_only_change_is_not_relevant(self):
        assert vpf.is_relevant([".github/workflows/generate-calendar.yml"]) is False

    def test_scraper_change_is_relevant(self):
        assert vpf.is_relevant(["scrapers/foo.py"]) is True

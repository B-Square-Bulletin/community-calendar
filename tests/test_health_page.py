#!/usr/bin/env python3
"""The feed-health page must render the current build, never a stale copy (#244).

report.py writes report.json on every run and the workflow publishes it to the
archive branch only. A same-origin copy therefore never updates, and letting it
come first in the fetch order silently pinned the page to a months-old build.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Where every build lands report.json for the deployed site.
ARCHIVE_REPORT_URL = (
    "https://raw.githubusercontent.com/B-Square-Bulletin/community-calendar/archive/report.json"
)


def test_page_reads_report_json_from_the_archive_branch():
    page = (ROOT / "report.html").read_text()
    assert ARCHIVE_REPORT_URL in page
    # A relative fetch would read the never-updated copy on main (#244).
    assert "fetch('report.json'" not in page


def test_root_report_json_is_untracked():
    result = subprocess.run(
        ["git", "ls-files", "--", "report.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    # Fail on "no git" instead of passing vacuously.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", "report.json is tracked, so it goes stale"

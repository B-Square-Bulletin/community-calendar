#!/usr/bin/env python3
"""Generated build artifacts stay off main (#253).

The nightly job rewrites rss/<city>-full.xml (4 MB), report/<city>/report.json
(435 KB) and cities/<city>/geo_filtered.json on every run. The first two were
committed nightly, so the repository grew by megabytes a night. They are build
output: the archive branch is their single published home (#244), and the pages
fetch them from there.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARCHIVE = "https://raw.githubusercontent.com/B-Square-Bulletin/community-calendar/archive"

UNTRACKED = [
    "build.log",
    "rss/",
    "report/*/report.json",
    "cities/*/geo_filtered.json",
]


def test_generated_artifacts_are_not_tracked():
    # Globs, not explicit paths, so a new city or feed cannot start tracking
    # its copies unnoticed.
    result = subprocess.run(
        ["git", "ls-files", "--", *UNTRACKED],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    # Fail on "no git" instead of passing vacuously.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"regenerated every run: {result.stdout}"


def test_city_health_page_reads_its_slice_from_the_archive_branch():
    page = (ROOT / "scripts/report_page_template.html").read_text()
    assert f"{ARCHIVE}/report/" in page
    # A same-origin copy is the never-updated file on main (#253). Strip the
    # good URL first so it cannot match itself.
    leftover = page.replace(f"{ARCHIVE}/report/", "")
    assert "report.json'" not in leftover and 'report.json"' not in leftover
    # One template serves every city page, so the city comes from the URL.
    assert "location.pathname" in page


def test_committed_city_page_matches_the_template():
    template = (ROOT / "scripts/report_page_template.html").read_text()
    committed = (ROOT / "report/bloomington/index.html").read_text()
    assert committed == template

#!/usr/bin/env python3
"""The feed-health page must render the current build, never a stale copy (#244).

report.py writes report.json on every run and the workflow publishes it to the
archive branch only. A same-origin copy therefore never updates, and letting it
come first in the fetch order silently pinned the page to a months-old build.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _report_urls() -> list[str]:
    page = (ROOT / "report.html").read_text()
    match = re.search(r"const REPORT_URLS = \[(.*?)\]", page, re.S)
    assert match, "report.html no longer defines REPORT_URLS"
    return re.findall(r"'([^']+)'", match.group(1))


def test_page_only_fetches_absolute_urls():
    urls = _report_urls()
    assert urls, "no report source configured"
    # A relative URL would resolve to the never-updated main-branch copy.
    assert all(url.startswith("https://") for url in urls), urls


def test_root_report_json_is_untracked():
    tracked = subprocess.run(
        ["git", "ls-files", "--", "report.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tracked == "", "report.json is tracked, so it can never be updated safely"

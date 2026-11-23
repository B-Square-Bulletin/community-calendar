#!/usr/bin/env python3
"""cities.json is generated, but it stays on main (#320).

Unlike the other build output, `cities.json` cannot move to the archive
branch: the frontend fetches it same-origin (xmlui/index.html,
xmlui/shell.js) and the my-picks edge function hardcodes the main URL. The
build no longer commits it, so the PR that adds, renames or removes a city
must carry the regenerated copy (ADR 0024). This test is that guard.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = "scripts/generate_cities_json.py"
CITIES_JSON = ROOT / "cities.json"


def test_cities_json_matches_the_generator():
    before = CITIES_JSON.read_bytes()
    try:
        result = subprocess.run(
            [sys.executable, GENERATOR],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        generated = CITIES_JSON.read_bytes()
    finally:
        # A drift failure must not leave the worktree dirty.
        CITIES_JSON.write_bytes(before)

    assert generated == before, (
        f"cities.json does not match the cities/*/city.conf files: "
        f"run `python {GENERATOR}` and commit the result"
    )

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "cities.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert status.returncode == 0, status.stderr
    assert status.stdout.strip() == "", f"test dirtied cities.json: {status.stdout}"

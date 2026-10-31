#!/usr/bin/env python3
"""cc-cli's resume file stays out of git (#249).

init writes .cc-cli-state.json (service-role key and other secrets) to the repo
root and deletes it on success. An interrupted run leaves the file behind, and
the next `git add -A` would stage it.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def state_file_name():
    # Read the name the tool writes, so a rename in state.go cannot outrun the
    # ignore rule and leave the test green.
    source = (ROOT / "cli/internal/state/state.go").read_text()
    match = re.search(r'const stateFile = "([^"]+)"', source)
    assert match, "state.go no longer declares const stateFile"
    return match.group(1)


def test_cli_state_file_is_ignored():
    name = state_file_name()
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", name],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    # 0 = ignored, 1 = not ignored (git errors use other codes).
    assert result.returncode == 0, f"{name} is trackable: {result.stderr}"

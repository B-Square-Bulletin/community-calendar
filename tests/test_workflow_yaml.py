#!/usr/bin/env python3
"""Every GitHub Actions workflow parses (#301).

Nothing else reads .github/workflows/*.yml: make lint's prettier glob is JS
only and the PR checks never parse those files, so a syntax slip surfaced as a
failed nightly build instead of a failed test. This runs under `make test`.

PyYAML implements YAML 1.1 and GitHub a 1.2-family parser, so this asserts only
that each document parses -- never its structure (PyYAML reads `on:` as the key
True). Duplicate mapping keys are the one error PyYAML accepts and GitHub
rejects; actionlint covers that in CI. The glob covers a new workflow with no
edit here.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def test_workflow_glob_finds_files():
    # A glob that silently stopped matching would make every case below vanish.
    assert WORKFLOWS, f"no workflow files under {WORKFLOW_DIR}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses(path: Path):
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail(f"{path.name} is not valid YAML: {exc}", pytrace=False)

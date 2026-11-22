#!/usr/bin/env python3
"""Every GitHub Actions workflow parses (#301).

Nothing else reads .github/workflows/*.yml: make lint's prettier glob is JS
only and the PR checks never parse those files, so a syntax slip surfaced as a
failed nightly build instead of a failed test. This runs under `make test`.

PyYAML implements YAML 1.1 and GitHub a 1.2-family parser, so this asserts only
that each document parses (PyYAML reads `on:` as the key True), plus one
structural case: the PR check names the main ruleset requires. Duplicate
mapping keys are the one error PyYAML accepts and GitHub rejects; actionlint
covers that in CI. The glob covers a new workflow with no edit here.
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


# Ruleset "main-required-checks" matches check contexts by job name, so a
# renamed job leaves a context that never reports and every PR waits on it.
RULESET_URL = "https://github.com/B-Square-Bulletin/community-calendar/rules/27823830"
REQUIRED_CHECKS = {
    "validate-feeds",
    "db-tests",
    "perf-gate",
    "node-tests",
    "deno-tests",
    "browser-tests",
    "Lint",
    "actionlint",
}


def test_pr_check_names_match_ruleset():
    """Keep validate-pr.yml job names in sync with the merge-blocking ruleset."""
    path = WORKFLOW_DIR / "validate-pr.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = doc.get("jobs") or {}
    names = {(job or {}).get("name") or key for key, job in jobs.items()}
    assert names == REQUIRED_CHECKS, (
        f"{path.name} job names differ from the required checks in {RULESET_URL}.\n"
        f"required but missing: {sorted(REQUIRED_CHECKS - names)}\n"
        f"present but not required: {sorted(names - REQUIRED_CHECKS)}\n"
        "Update that ruleset's required status checks, then this set."
    )

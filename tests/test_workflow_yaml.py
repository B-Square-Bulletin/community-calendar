#!/usr/bin/env python3
"""Every GitHub Actions workflow parses (#301).

Nothing else reads .github/workflows/*.yml: make lint's prettier glob is JS
only and the PR checks never parse those files, so a syntax slip surfaced as a
failed nightly build instead of a failed test. This runs under `make test`.

PyYAML implements YAML 1.1 and GitHub a 1.2-family parser, so this asserts only
that each document parses (PyYAML reads `on:` as the key True), plus structural
cases: the PR check names the main ruleset requires, that only the archive step
writes to git, that step's condition and its worktree guard, and what each
publishes (the PRODID inventory, the live feeds.txt export). Duplicate
mapping keys are the one error PyYAML accepts and GitHub rejects; actionlint
covers that in CI. The glob covers a new workflow with no edit here.
"""

import os
import subprocess
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


# The archive holds the only copy of the health report, RSS baselines and run
# histories (#253), so a plain `if:` silently starves it after any failure.
ARCHIVE_STEP = "Push build artifacts to archive branch"
GUARD_STEP = "Guard the build worktree"

# ADR 0024: main changes only through a human PR, so no step may stage or push
# a tracked file. Both steps below did exactly that.
DELETED_WRITE_STEPS = (
    "Commit metadata changes",
    "Commit processed pending_feeds.txt",
)


def test_no_step_writes_to_main():
    """Only the archive force-push writes to git; the deleted writers stay gone."""
    path = WORKFLOW_DIR / "generate-calendar.yml"
    text = path.read_text(encoding="utf-8")
    steps = (yaml.safe_load(text) or {})["jobs"]["generate-calendar"]["steps"]
    assert {s.get("name") for s in steps}.isdisjoint(DELETED_WRITE_STEPS)
    # The token existed only to author those commits and the archive push.
    assert "COMMUNITY_CALENDAR" not in text
    writers = [
        s.get("name")
        for s in steps
        if s.get("name") != ARCHIVE_STEP
        and any(cmd in (s.get("run") or "") for cmd in ("git add", "git commit", "git push"))
    ]
    assert writers == [], f"steps stage or push to main: {writers}"


def test_archive_publish_survives_failure_but_not_cancellation():
    """The archive publishes after a failure, but not after a cancellation."""
    path = WORKFLOW_DIR / "generate-calendar.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = doc["jobs"]["generate-calendar"]["steps"]
    step = next((s for s in steps if s.get("name") == ARCHIVE_STEP), None)
    assert step is not None, f"{path.name} has no step named {ARCHIVE_STEP!r}"
    assert step.get("if") == "${{ !cancelled() }}", (
        "The archive publish step must run after a failure but not after a "
        "cancellation (a cancelled run force-pushes a partial snapshot)."
    )


def test_build_worktree_guard_precedes_the_archive_push():
    """ADR 0024 §3: a dirty tracked file reds the run before the archive cleans it."""
    path = WORKFLOW_DIR / "generate-calendar.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = doc["jobs"]["generate-calendar"]["steps"]
    names = [s.get("name") for s in steps]
    assert GUARD_STEP in names, f"{path.name} has no step named {GUARD_STEP!r}"
    assert names.index(GUARD_STEP) == names.index(ARCHIVE_STEP) - 1, (
        "The worktree guard must sit immediately before the archive push, "
        "which is the only step allowed to write to git."
    )
    step = steps[names.index(GUARD_STEP)]
    assert step.get("if") == "${{ !cancelled() }}", (
        "The guard must run after an earlier failure, or the archive step's "
        "cleanup hides the offending paths."
    )
    assert not step.get("continue-on-error"), "A dirty worktree must red the run."
    run = step.get("run") or ""
    # Both diff halves: an unstaged write and a staged one are both offenders.
    assert "git diff --name-only" in run
    assert "git diff --cached --name-only" in run
    # The DB export's worktree copy is the one tracked file a build may touch.
    assert "feeds.txt" in run and "cities/" in run
    # -v is what makes it an exclusion; without it every real export reds.
    assert "grep -v" in run
    # A failure has to name the offending paths, not just exit 1.
    assert "GITHUB_STEP_SUMMARY" in run


# The inventory covers every city. A scoped run that wrote one over the archive
# copy would serve a wrong count at the documented URL until the next nightly.
PRODID_STEP = "Generate PRODID platform report"


def test_prodid_inventory_is_only_published_from_a_full_run():
    path = WORKFLOW_DIR / "generate-calendar.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = doc["jobs"]["generate-calendar"]["steps"]
    step = next((s for s in steps if s.get("name") == PRODID_STEP), None)
    assert step is not None, f"{path.name} has no step named {PRODID_STEP!r}"
    condition = step.get("if") or ""
    # Empty covers the schedule (a null input compares equal to '').
    assert "locations == ''" in condition and "'all'" in condition, (
        "A scoped run must leave the archive's full PRODID inventory alone; "
        f"the step's condition was {condition!r}."
    )


# feeds.txt on main is a frozen seed; the live export rides to the archive, and
# city discovery reads directories so a city without a seed still builds (#321).
def test_feeds_txt_lives_on_the_archive_and_cities_are_directories():
    path = WORKFLOW_DIR / "generate-calendar.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = doc["jobs"]["generate-calendar"]["steps"]
    by_name = {s.get("name"): s for s in steps}
    assert 'cp "cities/$city/feeds.txt"' in by_name[ARCHIVE_STEP]["run"], (
        "The archive snapshot must carry each city's live feeds.txt export; "
        "main keeps only the frozen seed."
    )
    # A skipped or failed export leaves main's seed in place, so the copy is
    # gated on this run's success manifest rather than on file content.
    assert "feeds_exported.txt" in by_name[ARCHIVE_STEP]["run"]
    export_run = by_name["Export feeds.txt from DB"]["run"]
    assert "feeds_exported.txt" in export_run
    # `cmd && echo` exits 0 when a failure precedes a success under bash -e.
    assert 'exit "$failed"' in export_run
    locations = by_name["Determine locations to process"]["run"]
    assert "cities/*/" in locations and "cities/*/feeds.txt" not in locations, (
        "City discovery must list cities/*/ directories, not feeds.txt files."
    )


# cities.json and the PRODID inventory describe what the build serves, so a
# variable that disagrees with cities/ must name itself, not red the nightly
# later as an unexplained dirty worktree.
def test_enabled_cities_guard_runs_the_real_comparison(tmp_path):
    """Execute the step's own shell, so breaking the comparison fails a test."""
    result, output = _run_determine(tmp_path / "match", "santarosa, bloomington")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "list=bloomington,santarosa" in output

    # The variable is a check, not the scope: duplicates cannot reach a loop.
    result, output = _run_determine(tmp_path / "dupes", "bloomington,santarosa,santarosa")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "list=bloomington,santarosa" in output

    result, _ = _run_determine(tmp_path / "subset", "bloomington")
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "does not match cities/" in combined, combined


# cities.json and the PRODID inventory describe what the build serves, so a
# variable that disagrees with cities/ must name itself, not red the nightly
# later as an unexplained dirty worktree.
DETERMINE_STEP = "Determine locations to process"


def _determine_run():
    path = WORKFLOW_DIR / "generate-calendar.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = doc["jobs"]["generate-calendar"]["steps"]
    step = next((s for s in steps if s.get("name") == DETERMINE_STEP), None)
    assert step is not None, f"no step named {DETERMINE_STEP!r}"
    # The step interpolates two workflow expressions at build time; read them
    # from the environment instead so the shell can run here.
    return (
        step["run"]
        .replace("${{ github.event.inputs.locations }}", "$INPUT")
        .replace("${{ vars.ENABLED_CITIES }}", "$ENABLED")
    )


def _run_determine(root, enabled, input_value=""):
    for city in ("bloomington", "santarosa"):
        (root / "cities" / city).mkdir(parents=True, exist_ok=True)
    output = root / "github_output"
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", _determine_run()],
        cwd=root,
        env={
            **os.environ,
            "ENABLED": enabled,
            "INPUT": input_value,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    return result, output.read_text() if output.exists() else ""

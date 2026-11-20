#!/usr/bin/env python3
"""The archive-restore script is the nightly guards' only baseline source.

`*.runs.json` run histories and the `rss/` feeds live on the archive branch
(ADR 0022), so each build must restore them before the guards run. The
workflow calls `scripts/restore_from_archive.sh`, and these tests run the
same script against a throwaway git remote: a restore failure here means the
silent-degradation and new-feed guards would run blind in production.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "restore_from_archive.sh"

RUNS = '{"runs": [{"date": "2026-11-19", "emitted": 306}]}'


def _git(*args, cwd):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _make_origin_with_archive(tmp_path, files):
    """A bare remote whose only branch is `archive`, holding `files`."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        capture_output=True,
        text=True,
        check=True,
    )
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(seed)], capture_output=True, check=True)
    for path, content in files.items():
        target = seed / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _git("add", "-A", cwd=seed)
    _git("-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-m", "seed", cwd=seed)
    _git("push", "--force", f"file://{origin}", "HEAD:refs/heads/archive", cwd=seed)
    return origin


def _make_workdir(tmp_path, origin):
    """A checkout whose `origin` remote points at the throwaway archive."""
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-b", "main", str(work)], capture_output=True, check=True)
    _git("remote", "add", "origin", f"file://{origin}", cwd=work)
    return work


def _run_script(work, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(work),
        capture_output=True,
        text=True,
    )


def test_no_archive_branch_starts_clean(tmp_path):
    # A bare remote with no branches at all: the fork's first build.
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        capture_output=True,
        text=True,
        check=True,
    )
    work = _make_workdir(tmp_path, origin)

    result = _run_script(work, "run histories", "report/", r"\.runs\.json$")

    assert result.returncode == 0, result.stderr
    assert "No archive branch yet" in result.stdout
    assert not (work / "report").exists()


def test_failed_restore_fails_the_build_and_leaves_no_baseline(tmp_path):
    origin = _make_origin_with_archive(
        tmp_path,
        {"report/bloomington/visit_bloomington.runs.json": RUNS},
    )
    work = _make_workdir(tmp_path, origin)
    # A read-only report dir makes the `git show > file` redirect fail, the
    # same failure mode as a corrupt or missing blob in the archive.
    city = work / "report/bloomington"
    city.mkdir(parents=True)
    city.chmod(0o555)

    result = _run_script(work, "run histories", "report/", r"\.runs\.json$")

    assert result.returncode != 0
    assert "Could not restore" in result.stderr
    assert not (city / "visit_bloomington.runs.json").exists()


def test_second_call_reuses_the_already_fetched_archive(tmp_path):
    # One build restores run histories and then the RSS baseline: the second
    # call must not need the network again, and must still restore.
    origin = _make_origin_with_archive(tmp_path, {"rss/full.xml": "<rss/>"})
    work = _make_workdir(tmp_path, origin)

    first = _run_script(work, "run histories", "report/", r"\.runs\.json$")
    second = _run_script(work, "an RSS baseline", "rss/")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (work / "rss/full.xml").read_text() == "<rss/>"


def test_restores_only_the_named_files_from_the_archive(tmp_path):
    origin = _make_origin_with_archive(
        tmp_path,
        {
            "report/bloomington/visit_bloomington.runs.json": RUNS,
            "report/bloomington/index.html": "<html>not state</html>",
        },
    )
    work = _make_workdir(tmp_path, origin)

    result = _run_script(work, "run histories", "report/", r"\.runs\.json$")

    assert result.returncode == 0, result.stderr
    restored = work / "report/bloomington/visit_bloomington.runs.json"
    assert restored.read_text() == RUNS
    # The pattern keeps the script off the tracked pages that Pages serves.
    assert not (work / "report/bloomington/index.html").exists()

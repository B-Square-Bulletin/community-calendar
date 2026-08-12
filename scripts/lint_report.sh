#!/usr/bin/env bash
# Lint checks for PR CI, mirroring the local `make lint` target.
#
# Ruff (format + check) GATES the job: findings fail it so ruff violations
# block the PR, matching ADR 0006 phase 1 ("ruff gates now"). The four type
# checkers are report-only: their diagnostics are printed in a findings summary
# but never fail the job, so the existing type-checker baseline does not block
# merges while it is still being ratcheted down (ADR 0006; the final ticket in
# this series flips the type checkers to gating too).
#
# Must be run from the repository root (the PR CI workflow runs it from the
# checkout root). Requires the project's uv-managed venv to be installed.

set -uo pipefail

cd "$(dirname "$0")/.." || exit

# Cap per-check output so a large baseline doesn't blow up the CI log. The full
# output is preserved in a temp file; the cap only limits what we echo.
OUTPUT_LIMIT=200

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

pass=0
fail=0
failed_names=()
gate_failed=0

# $1: "gate" (findings fail the job) or "report" (findings are report-only)
# $2: check name; remaining args: the command to run (via `uv run`)
run_check() {
  local gate="$1"
  local name="$2"
  shift 2
  local log
  log="$tmpdir/$(echo "$name" | tr ' ' '_').log"

  echo ""
  echo "==== $name ===="
  if uv run "$@" >"$log" 2>&1; then
    echo "  OK — $name found no issues"
    ((pass++)) || true
  else
    echo "  FINDINGS — $name reported diagnostics:"
    sed 's/^/    /' "$log" | head -"$OUTPUT_LIMIT"
    if [ "$(wc -l <"$log")" -gt "$OUTPUT_LIMIT" ]; then
      echo "    ... ($(wc -l <"$log") total lines; output truncated)"
    fi
    if [ "$gate" = "gate" ]; then
      echo "  => gating — fixes required for the PR to merge"
      gate_failed=1
    else
      echo "  => report-only — findings do not block this PR"
    fi
    ((fail++)) || true
    failed_names+=("$name")
  fi
}

run_check gate "ruff format check" ruff format --check .
run_check gate "ruff check" ruff check .
run_check report "pyright" pyright
run_check report "ty check" ty check
run_check report "pyrefly check" pyrefly check
run_check report "zuban (mypy mode)" zuban mypy .

echo ""
echo "========================================"
echo "Lint summary"
echo "  clean checks:   $pass"
echo "  with findings:  $fail"
if [ "$fail" -gt 0 ]; then
  echo "  checks with findings: ${failed_names[*]}"
fi
if [ "$gate_failed" -ne 0 ]; then
  echo "  RESULT: gating (ruff) checks failed — this job fails the PR"
  exit 1
else
  echo "  RESULT: gating (ruff) checks clean; type-checker findings are report-only — job passes"
  exit 0
fi

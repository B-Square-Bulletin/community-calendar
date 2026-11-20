#!/usr/bin/env bash
# Restore the previous build's baseline files from the archive branch.
#
# Usage: restore_from_archive.sh <label> <path-under-archive> [file-pattern]
#
# The named files are state, not output: they carry the baselines the nightly
# guards compare against, and main no longer tracks them (ADR 0022). Losing a
# baseline blinds a guard, so only "no such branch" (ls-remote exit 2) may start
# without one; every other lookup or restore failure fails the build.
set -eu

label=$1
path=$2
pattern=${3:-}

if git rev-parse --verify origin/archive >/dev/null 2>&1; then
  # Already local from an earlier restore call in this build.
  :
else
  lookup=0
  git ls-remote --exit-code --heads origin archive >/dev/null || lookup=$?
  if [ "$lookup" -eq 2 ]; then
    echo "No archive branch yet; starting without $label"
    exit 0
  elif [ "$lookup" -ne 0 ]; then
    echo "Could not look up the archive branch (ls-remote exit $lookup)" >&2
    exit 1
  fi
  git fetch --depth=1 origin archive
fi

files=$(git ls-tree -r --name-only origin/archive "$path")
[ -n "$pattern" ] && files=$(printf '%s\n' "$files" | grep "$pattern" || true)
for f in $files; do
  mkdir -p "$(dirname "$f")"
  # Redirect truncates before git show runs, so a failed show must not
  # leave an empty file behind as a baseline.
  if ! git show "origin/archive:$f" > "$f" 2>/dev/null; then
    rm -f "$f"
    echo "Could not restore $f from the archive baseline" >&2
    exit 1
  fi
done

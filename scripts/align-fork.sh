#!/usr/bin/env bash
#
# align-fork.sh — Prepare a fork for smoother upstream syncs.
#
# What it does:
#   1. Adds upstream remote (if missing)
#   2. Restores city directories that were deleted from the fork
#      (so upstream merges stop re-adding them as conflicts)
#   3. Sets up the keepours merge driver (so config.json, cities.json,
#      and feeds.txt auto-resolve to the fork's version on merge)
#   4. Creates config.local.js from the .example template (if missing)
#   5. Reminds you to set ENABLED_CITIES if it's not already configured
#
# After running this script, upstream syncs become:
#   git fetch upstream && git merge upstream/main
#
# Usage:
#   bash scripts/align-fork.sh
#   bash scripts/align-fork.sh --upstream https://github.com/judell/community-calendar.git

set -euo pipefail

UPSTREAM_URL="${1:-https://github.com/judell/community-calendar.git}"
if [[ "$UPSTREAM_URL" == "--upstream" ]]; then
  UPSTREAM_URL="${2:?Usage: align-fork.sh --upstream <url>}"
fi

echo "=== Fork Alignment ==="
echo

# 1. Upstream remote
if git remote get-url upstream &>/dev/null; then
  echo "[ok] upstream remote already set: $(git remote get-url upstream)"
else
  echo "[+] Adding upstream remote: $UPSTREAM_URL"
  git remote add upstream "$UPSTREAM_URL"
fi

git fetch upstream --quiet
echo "[ok] Fetched upstream/main"
echo

# 2. Restore deleted city directories
echo "--- Restoring upstream city directories ---"
RESTORED=0
for dir in $(git ls-tree -d --name-only upstream/main cities/ 2>/dev/null); do
  if [ ! -d "$dir" ]; then
    echo "[+] Restoring $dir/"
    git checkout upstream/main -- "$dir"
    RESTORED=$((RESTORED + 1))
  fi
done

if [ "$RESTORED" -eq 0 ]; then
  echo "[ok] All upstream city directories already present"
else
  echo "[+] Restored $RESTORED city directories"
  echo "    These will be ignored at build time if ENABLED_CITIES is set."
  echo "    Keeping them avoids merge conflicts on every upstream sync."
fi
echo

# 3. Keepours merge driver
echo "--- Setting up keepours merge driver ---"
git config merge.keepours.name "keep fork versions of generated files"
git config merge.keepours.driver true
echo "[ok] Merge driver configured. Files covered by .gitattributes:"
grep 'merge=keepours' .gitattributes 2>/dev/null | sed 's/merge=keepours//' | while read -r f; do
  echo "     $f"
done
echo

# 4. config.local.js
echo "--- Checking config.local.js ---"
if [ -f xmlui/config.local.js ]; then
  echo "[ok] xmlui/config.local.js exists"
else
  if [ -f xmlui/config.local.js.example ]; then
    cp xmlui/config.local.js.example xmlui/config.local.js
    echo "[+] Created xmlui/config.local.js from .example"
    echo "    Edit it to set your Supabase URL and key."
  else
    echo "[!] No config.local.js.example found — create xmlui/config.local.js manually"
  fi
fi
echo

# 5. ENABLED_CITIES reminder
echo "--- ENABLED_CITIES ---"
echo "If your fork only serves a subset of cities, set a repository variable"
echo "so the build skips the rest without deleting their directories:"
echo
echo "  GitHub repo > Settings > Secrets and variables > Actions > Variables"
echo "  Name:  ENABLED_CITIES"
echo "  Value: bloomington          (or comma-separated: bloomington,bedford)"
echo
echo "This scopes scheduled builds without fork-specific workflow edits."
echo

# Summary
if [ "$RESTORED" -gt 0 ]; then
  echo "=== Next steps ==="
  echo "  1. Review the restored directories: git status"
  echo "  2. Commit: git add cities/ && git commit -m 'Restore upstream city dirs for cleaner merges'"
  echo "  3. Set ENABLED_CITIES (see above) if you haven't already"
  echo "  4. Sync: git fetch upstream && git merge upstream/main"
else
  echo "=== Ready ==="
  echo "  Your next upstream sync: git fetch upstream && git merge upstream/main"
fi

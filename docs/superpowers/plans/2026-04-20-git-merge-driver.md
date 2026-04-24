# Git Merge Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate upstream merge conflicts for city filtering and generated files using a custom git merge driver

**Architecture:** A bash script filters cities based on `ENABLED_CITIES` env var during git merge. Git routes files through the script via `.gitattributes` declarations. Keeps fork's city content and generated files, accepts all other upstream changes.

**Tech Stack:** Bash, jq, Git merge drivers, .gitattributes

---

## File Structure

**Created:**
- `scripts/merge-cities-filter.sh` - Custom merge driver script that filters cities

**Modified:**
- `.gitattributes` - Route files to appropriate merge drivers
- `docs/syncing-your-fork.md` - Add setup instructions and update merge workflow docs

**No tests needed** - validation is manual merge testing with upstream

---

### Task 1: Create Merge Driver Script

**Files:**
- Create: `scripts/merge-cities-filter.sh`

- [ ] **Step 1: Create the script file with header and env var check**

\`\`\`bash
cat > scripts/merge-cities-filter.sh << 'EOF'
#!/usr/bin/env bash
# Git merge driver that filters cities based on ENABLED_CITIES environment variable
# Usage: Called automatically by Git during merge via .gitattributes
# Arguments: %O (base) %A (ours) %B (theirs) %P (path)

set -euo pipefail

# Read which cities this fork wants to keep from environment
if [[ -z "${ENABLED_CITIES:-}" ]]; then
    echo "Error: ENABLED_CITIES environment variable not set" >&2
    echo "Add to .envrc in the repo root:" >&2
    echo "  export ENABLED_CITIES='bloomington'" >&2
    echo "Then run: source .envrc  (or 'direnv allow .' if using direnv)" >&2
    exit 1
fi

EOF
\`\`\`

- [ ] **Step 2: Add jq availability check**

\`\`\`bash
cat >> scripts/merge-cities-filter.sh << 'EOF'
# Check for jq (needed for JSON filtering)
if ! command -v jq &> /dev/null; then
    echo "Error: jq is not installed" >&2
    echo "Install with: brew install jq  (macOS) or apt-get install jq  (Linux)" >&2
    exit 1
fi

EOF
\`\`\`

- [ ] **Step 3: Add cities.json filtering logic**

\`\`\`bash
cat >> scripts/merge-cities-filter.sh << 'EOF'
# Extract arguments
BASE="$1"
OURS="$2"
THEIRS="$3"
PATH_NAME="$4"

# Handle cities.json specially - filter to only enabled cities
if [[ "$PATH_NAME" == "cities.json" ]]; then
    # Convert comma-separated ENABLED_CITIES to jq object filter
    # Example: "bloomington,bedford" becomes '{bloomington: .bloomington, bedford: .bedford}'
    FILTER=$(echo "$ENABLED_CITIES" | awk -F',' '{
        printf "{"
        for(i=1; i<=NF; i++) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)  # trim whitespace
            if(i>1) printf ", "
            printf "%s: .%s", $i, $i
        }
        printf "}"
    }')
    
    # Apply filter to our version (which may already have upstream cities merged in)
    # Write filtered result back to OURS
    if jq "$FILTER" "$OURS" > "$OURS.tmp" 2>/dev/null; then
        mv "$OURS.tmp" "$OURS"
        exit 0
    else
        echo "Error: Failed to filter cities.json with jq" >&2
        echo "Filter expression: $FILTER" >&2
        rm -f "$OURS.tmp"
        exit 1
    fi
fi

EOF
\`\`\`

- [ ] **Step 4: Add cities/** files keep-ours logic**

\`\`\`bash
cat >> scripts/merge-cities-filter.sh << 'EOF'
# For all other files (cities/** contents), keep ours unchanged
# Git has already placed our version in OURS, we just signal success
exit 0
EOF
\`\`\`

- [ ] **Step 5: Make script executable**

\`\`\`bash
chmod +x scripts/merge-cities-filter.sh
\`\`\`

- [ ] **Step 6: Test script syntax**

\`\`\`bash
bash -n scripts/merge-cities-filter.sh
\`\`\`

Expected: No output (clean syntax)

- [ ] **Step 7: Test script with missing ENABLED_CITIES**

\`\`\`bash
unset ENABLED_CITIES
bash scripts/merge-cities-filter.sh /tmp/base /tmp/ours /tmp/theirs cities.json 2>&1 | head -3
\`\`\`

Expected output:
\`\`\`
Error: ENABLED_CITIES environment variable not set
Add to .envrc in the repo root:
  export ENABLED_CITIES='bloomington'
\`\`\`

- [ ] **Step 8: Commit the merge driver script**

\`\`\`bash
git add scripts/merge-cities-filter.sh
git commit -m "feat: add git merge driver for city filtering

Custom merge driver that:
- Filters cities.json to only ENABLED_CITIES entries
- Keeps fork's version of cities/** files
- Reads configuration from ENABLED_CITIES env var in .envrc

Part of automated upstream sync solution.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
\`\`\`

---

### Task 2: Configure .gitattributes

**Files:**
- Modify: `.gitattributes`

- [ ] **Step 1: Add merge driver rules to .gitattributes**

\`\`\`bash
cat >> .gitattributes << 'EOF'

# Git merge driver rules for fork sync automation
# City-specific content - keep fork's enabled cities only
cities/** merge=city-filter
cities.json merge=city-filter

# Generated files - keep fork's versions during upstream sync
report.json merge=keepours
xmlui/version.txt merge=keepours
EOF
\`\`\`

- [ ] **Step 2: Verify .gitattributes syntax**

\`\`\`bash
cat .gitattributes
\`\`\`

Expected: File contains the new rules with proper formatting

- [ ] **Step 3: Commit .gitattributes changes**

\`\`\`bash
git add .gitattributes
git commit -m "feat: configure merge drivers for automated fork sync

Routes city files through custom filter driver.
Routes generated files through keepours driver.

Requires one-time git config setup to activate drivers.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
\`\`\`

---

### Task 3: Update Documentation

**Files:**
- Modify: `docs/syncing-your-fork.md`

- [ ] **Step 1: Add automated merge driver setup section**

Find line 67 ("## Syncing with upstream") and insert this NEW section before "### Step 1: Pull upstream changes":

\`\`\`markdown
### One-Time Setup: Automated Merge Drivers (Optional but Recommended)

To avoid manual conflict resolution during upstream syncs, configure merge drivers once:

#### 1. Set ENABLED_CITIES in .envrc

\`\`\`bash
# Add to .envrc in the repo root (create if it doesn't exist)
echo 'export ENABLED_CITIES="bloomington"' >> .envrc

# For multiple cities: echo 'export ENABLED_CITIES="city1,city2"' >> .envrc
\`\`\`

If using direnv, allow the directory:
\`\`\`bash
direnv allow .
\`\`\`

If not using direnv, source manually before merging:
\`\`\`bash
source .envrc
\`\`\`

#### 2. Configure Git merge drivers

\`\`\`bash
# Configure the city filter driver
git config merge.city-filter.name "Filter cities to fork's enabled cities"
git config merge.city-filter.driver "bash scripts/merge-cities-filter.sh %O %A %B %P"

# Configure the keepours driver for generated files
git config merge.keepours.name "Keep our generated files"
git config merge.keepours.driver true
\`\`\`

#### 3. Set ENABLED_CITIES in GitHub Actions

In GitHub: **Settings > Secrets and variables > Actions > Variables**

Add variable:
\`\`\`
Name: ENABLED_CITIES
Value: bloomington
\`\`\`

(Or \`city1,city2\` for multiple cities - must match your .envrc)

#### 4. Verify setup

\`\`\`bash
echo $ENABLED_CITIES  # Should show your cities
git config --get merge.city-filter.driver
git config --get merge.keepours.driver
\`\`\`

**After this setup**, \`git merge upstream/main\` will automatically:
- Keep only your enabled cities in \`cities/\` and \`cities.json\`
- Preserve your generated files (\`report.json\`, \`xmlui/version.txt\`)
- Accept all other upstream changes without conflicts

If you skip this setup, you can still merge manually as described below.

---

\`\`\`

- [ ] **Step 2: Add troubleshooting section at end of document**

Add this section at the very end of the file (after "## Verifying it works"):

\`\`\`markdown
## Troubleshooting Merge Drivers

If automated merging fails:

**ENABLED_CITIES not set:**
\`\`\`bash
# Add to .envrc and reload
echo 'export ENABLED_CITIES="bloomington"' >> .envrc
source .envrc
\`\`\`

**Script not executable:**
\`\`\`bash
chmod +x scripts/merge-cities-filter.sh
\`\`\`

**jq not found:**
\`\`\`bash
# macOS
brew install jq

# Linux
sudo apt-get install jq
\`\`\`

**Wrong cities kept after merge:**
\`\`\`bash
# Check variable value
echo $ENABLED_CITIES

# May need to source again
source .envrc
\`\`\`

**Build processes wrong cities:**
Check that ENABLED_CITIES GitHub Actions variable matches your local .envrc value.

**Merge driver not activating:**
\`\`\`bash
# Verify git config
git config --get merge.city-filter.driver
git config --get merge.keepours.driver

# If empty, rerun the git config commands from setup
\`\`\`

**To disable merge drivers temporarily:**
\`\`\`bash
git config merge.city-filter.driver false
git config merge.keepours.driver false
\`\`\`

**To revert a bad merge:**
\`\`\`bash
# Before committing
git merge --abort

# After committing
git reset --hard HEAD^
\`\`\`
\`\`\`

- [ ] **Step 3: Commit documentation changes**

\`\`\`bash
git add docs/syncing-your-fork.md
git commit -m "docs: add automated merge driver setup and troubleshooting

Adds one-time setup section for merge drivers:
- Setting ENABLED_CITIES in .envrc
- Configuring git merge drivers locally
- Setting GitHub Actions variable
- Verification steps

Includes comprehensive troubleshooting section.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
\`\`\`

---

### Task 4: Test Merge Driver

**Files:**
- No file changes (validation only)

- [ ] **Step 1: Verify ENABLED_CITIES is set**

\`\`\`bash
echo $ENABLED_CITIES
\`\`\`

Expected: \`bloomington\` (or your configured cities)

If not set:
\`\`\`bash
source .envrc
\`\`\`

- [ ] **Step 2: Configure git merge drivers locally**

\`\`\`bash
git config merge.city-filter.name "Filter cities to fork's enabled cities"
git config merge.city-filter.driver "bash scripts/merge-cities-filter.sh %O %A %B %P"
git config merge.keepours.name "Keep our generated files"
git config merge.keepours.driver true
\`\`\`

- [ ] **Step 3: Verify git config**

\`\`\`bash
git config --get merge.city-filter.driver
git config --get merge.keepours.driver
\`\`\`

Expected output:
\`\`\`
bash scripts/merge-cities-filter.sh %O %A %B %P
true
\`\`\`

- [ ] **Step 4: Fetch latest upstream**

\`\`\`bash
git fetch upstream
\`\`\`

- [ ] **Step 5: Attempt dry-run merge**

\`\`\`bash
git merge --no-commit --no-ff upstream/main
\`\`\`

Expected: Merge completes without conflicts in:
- \`cities/\` (only bloomington should exist)
- \`cities.json\` (only bloomington entry)
- \`report.json\` (your version kept)
- \`xmlui/version.txt\` (your version kept)

- [ ] **Step 6: Verify city filtering worked**

\`\`\`bash
ls cities/
cat cities.json
\`\`\`

Expected: 
- \`cities/\` contains only \`bloomington\` directory
- \`cities.json\` has only bloomington entry

- [ ] **Step 7: Check generated files unchanged**

\`\`\`bash
git diff HEAD report.json
git diff HEAD xmlui/version.txt
\`\`\`

Expected: No diff (files unchanged from your pre-merge version)

- [ ] **Step 8: Check upstream code changes merged**

\`\`\`bash
git log --oneline --graph -10
\`\`\`

Expected: Merge commit appears with upstream commits integrated

- [ ] **Step 9: Abort the test merge**

\`\`\`bash
git merge --abort
\`\`\`

- [ ] **Step 10: Document test results**

Create a quick validation note:

\`\`\`bash
cat > /tmp/merge-driver-test-results.txt << 'EOF'
Git Merge Driver Test Results
Date: $(date)

✓ ENABLED_CITIES set correctly
✓ Git config drivers configured
✓ Merge completed without city conflicts
✓ cities/ contains only enabled cities
✓ cities.json filtered correctly
✓ Generated files preserved
✓ Upstream code changes integrated

Test merge aborted successfully.
Merge driver is ready for production use.
EOF

cat /tmp/merge-driver-test-results.txt
\`\`\`

---

## Validation Checklist

Before considering this complete:

- [ ] Script executes without syntax errors
- [ ] Script exits with clear error when ENABLED_CITIES not set
- [ ] Script checks for jq availability
- [ ] .gitattributes routes files to correct drivers
- [ ] Documentation includes setup steps
- [ ] Documentation includes troubleshooting section
- [ ] Dry-run merge with upstream succeeds
- [ ] Only enabled cities remain after merge
- [ ] Generated files preserved after merge
- [ ] Upstream code changes integrated after merge

---

## Post-Implementation Notes

**For the next upstream sync:**

1. Ensure \`ENABLED_CITIES\` is set (check with \`echo $ENABLED_CITIES\`)
2. Run \`git fetch upstream && git merge upstream/main\`
3. Merge should complete cleanly with no manual conflict resolution
4. Verify with \`ls cities/\` and \`cat cities.json\`
5. Commit the merge

**If GitHub Actions ENABLED_CITIES variable is not set:**

The merge driver will work locally, but CI builds may process all cities from upstream. Set the variable in:
- GitHub repo > Settings > Secrets and variables > Actions > Variables
- Name: \`ENABLED_CITIES\`
- Value: Same as your local .envrc (e.g., \`bloomington\`)

# Git Merge Driver for Fork Sync Automation

**Date:** 2026-04-20  
**Status:** Approved for implementation

## Problem Statement

When syncing this fork with the upstream judell/community-calendar repository, the merge process requires manual conflict resolution for:

1. **City-specific content** - Upstream maintains 9+ cities (santarosa, davis, toronto, etc.), but forks typically serve only a subset. Each upstream sync brings unwanted city directories and entries that must be manually removed.

2. **Generated files** - Files like `report.json`, `xmlui/version.txt`, and `cities.json` are generated during the fork's own build process and should not be overwritten by upstream's versions.

3. **Fork's city content** - Even the fork's own city directories (e.g., `cities/bloomington/`) should stay as the fork's version, not be replaced by upstream changes.

This manual cleanup is error-prone and time-consuming. We need an automated solution that handles these merge conflicts declaratively.

## Goals

1. **Silent city filtering** - When upstream adds new cities, they should never appear in the fork's working tree, not even temporarily.
2. **Preserve generated files** - Fork's build artifacts should automatically be kept during merges.
3. **Preserve fork's city content** - The fork's version of its enabled cities takes precedence over upstream versions.
4. **Zero manual intervention** - After one-time setup, `git merge upstream/main` should complete cleanly without conflicts in city-related files.
5. **Non-invasive** - Upstream code, scripts, workflows, and documentation changes should merge normally.
6. **Reusable** - Any fork (single-city or multi-city) can use the same merge driver by configuring which cities to keep.

## Non-Goals

- Selective syncing of certain files within enabled cities (all-or-nothing approach is simpler)
- Handling workflow file conflicts (those remain manual since they're fork-specific customizations)
- Automatic rebasing or squashing (standard merge workflow preserved)

## Proposed Solution: Two-Layer Filtering Strategy

The solution combines two complementary mechanisms:

1. **Git merge driver** - Keeps the repository clean by filtering city content during upstream merges
2. **ENABLED_CITIES variable** - Ensures CI builds only generate Bloomington content

This dual approach provides defense in depth: even if upstream content somehow enters the repo, the build pipeline won't process it.

### Architecture

We'll use Git's merge driver mechanism to route files through custom conflict resolution logic:

```
┌─────────────────┐
│ git merge       │
│ upstream/main   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│ .gitattributes rules:           │
│ - cities/** → city-filter       │
│ - cities.json → city-filter     │
│ - report.json → keepours        │
│ - xmlui/version.txt → keepours  │
└────────┬────────────────────────┘
         │
         ├──────────────────┬──────────────────┐
         ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
│ city-filter      │ │ keepours     │ │ (Git default)│
│ (custom script)  │ │ (passthrough)│ │              │
└────────┬─────────┘ └──────┬───────┘ └──────┬───────┘
         │                  │                │
         ▼                  ▼                ▼
┌───────────────────────────────────────────────────┐
│ Merged working tree:                              │
│ - Only enabled cities exist (from ENABLED_CITIES) │
│ - cities.json has only enabled city entries       │
│ - Generated files unchanged from pre-merge        │
│ - All other upstream changes applied normally     │
└───────────────────────────────────────────────────┘
```

### Components

#### 1. Merge Driver Script: `scripts/merge-cities-filter.sh`

Bash script invoked by Git during three-way merges. Receives four arguments:

- `%O` - Base version (common ancestor)
- `%A` - Ours (current branch)
- `%B` - Theirs (upstream branch)
- `%P` - Path being merged

**Logic flow:**

```bash
#!/usr/bin/env bash
# scripts/merge-cities-filter.sh

# Read which cities this fork wants to keep from environment
if [[ -z "$ENABLED_CITIES" ]]; then
    echo "Error: ENABLED_CITIES environment variable not set" >&2
    echo "Add to .envrc in the repo root:" >&2
    echo "  export ENABLED_CITIES='bloomington'" >&2
    echo "Then run: source .envrc  (or 'direnv allow .' if using direnv)" >&2
    exit 1
fi

if [[ "$4" == "cities.json" ]]; then
    # Parse JSON, extract only enabled cities, write to %A
    # Convert comma-separated list to jq object filter
    FILTER=$(echo "$ENABLED_CITIES" | awk -F',' '{
        printf "{"
        for(i=1; i<=NF; i++) {
            if(i>1) printf ", "
            printf "%s: .%s", $i, $i
        }
        printf "}"
    }')
    jq "$FILTER" "$2" > "$2.tmp" && mv "$2.tmp" "$2"
    exit $?
else
    # For cities/** files, keep ours unchanged
    # %A already contains our version, just signal success
    exit 0
fi
```

**Error handling:**
- Check for `jq` presence at script start
- Validate JSON parsing succeeds before overwriting
- Exit 1 on errors to trigger manual conflict resolution
- Log errors to stderr for debugging

**File handling:**
- Preserve file permissions and ownership
- Use atomic writes (write to temp, then move)
- Clean up temp files on error

#### 2. Git Attributes: `.gitattributes`

Declarative rules that route files to merge drivers. Committed to repo:

```gitattributes
# City-specific content - keep fork's Bloomington-only version
cities/** merge=city-filter
cities.json merge=city-filter

# Generated files - keep fork's versions during upstream sync
report.json merge=keepours
xmlui/version.txt merge=keepours
```

The `**` glob ensures all files under `cities/` (including subdirectories) use the custom driver.

#### 3. Git Configuration (One-Time Setup)

Local configuration that defines the merge drivers. Not committed (lives in `.git/config`):

```bash
# Configure the city filter driver
git config merge.city-filter.name "Filter cities to Bloomington only"
git config merge.city-filter.driver "bash scripts/merge-cities-filter.sh %O %A %B %P"

# Configure the keepours driver
git config merge.keepours.name "Keep our generated files"
git config merge.keepours.driver true
```

The `true` driver is Git's built-in no-op - it signals success and keeps "ours" unchanged.

#### 5. GitHub Actions Variable: ENABLED_CITIES

Set a repository variable to ensure the CI build pipeline only processes Bloomington:

**In GitHub:** Settings > Secrets and variables > Actions > Variables

Add variable:
```
ENABLED_CITIES=bloomington
```

This works together with the merge driver:
- **Merge driver** prevents upstream cities from entering the git repository
- **ENABLED_CITIES** ensures the build workflow only processes Bloomington (defense in depth)

The workflow already checks this variable (see `.github/workflows/generate-calendar.yml`), so no workflow changes needed.

#### 5. Documentation: `docs/syncing-your-fork.md`

Update the existing sync documentation with:

**Setup section:**
```markdown
## One-Time Setup: Automated Merge Drivers

To avoid manual conflict resolution during upstream syncs, configure merge drivers:

```bash
# From the repo root
git config merge.city-filter.name "Filter cities to Bloomington only"
git config merge.city-filter.driver "bash scripts/merge-cities-filter.sh %O %A %B %P"
git config merge.keepours.name "Keep our generated files"
git config merge.keepours.driver true

# Verify setup
git config --get merge.city-filter.driver
git config --get merge.keepours.driver
```

Then set the ENABLED_CITIES repository variable in GitHub:
Settings > Secrets and variables > Actions > Variables > New repository variable

```
Name: ENABLED_CITIES
Value: bloomington
```

After setup, city filtering happens automatically during `git merge upstream/main`, and CI builds will only process Bloomington.
```

**Troubleshooting section:**
- `ENABLED_CITIES not set`: Add `export ENABLED_CITIES="yourcity"` to `.envrc` and run `source .envrc` (or `direnv allow .`)
- Script not executable: `chmod +x scripts/merge-cities-filter.sh`
- `jq` not found: Install via package manager
- Merge fails with driver error: Check script syntax with `bash -n scripts/merge-cities-filter.sh`
- Build processes wrong cities: Check ENABLED_CITIES variable is set in GitHub repo settings and matches your `.envrc`
- Wrong cities kept after merge: Check `echo $ENABLED_CITIES` returns correct value; may need to `source .envrc` again

### Behavior Specifications

**Scenario 1: Upstream adds new city (e.g., cities/chicago/)**

```
Before merge: cities/ contains only bloomington/
Upstream adds: cities/chicago/
After merge: cities/ still contains only bloomington/
Result: No conflict shown, chicago silently filtered
```

**Scenario 2: Upstream updates cities.json**

```
Fork's cities.json (ENABLED_CITIES="bloomington"):
{
  "bloomington": {"timezone": "America/Indiana/Indianapolis"}
}

Upstream's cities.json:
{
  "bloomington": {"timezone": "America/Indiana/Indianapolis"},
  "chicago": {"timezone": "America/Chicago"},
  "toronto": {"timezone": "America/Toronto"}
}

After merge:
{
  "bloomington": {"timezone": "America/Indiana/Indianapolis"}
}

Result: Only bloomington preserved, no conflict
```

**Scenario 2b: Multi-city fork**

```
Fork's cities.json (ENABLED_CITIES="bloomington,bedford"):
{
  "bloomington": {"timezone": "America/Indiana/Indianapolis"},
  "bedford": {"timezone": "America/Indiana/Indianapolis"}
}

After merge with upstream's cities.json (9 cities):
{
  "bloomington": {"timezone": "America/Indiana/Indianapolis"},
  "bedford": {"timezone": "America/Indiana/Indianapolis"}
}

Result: Only enabled cities preserved, others filtered
```

**Scenario 3: Upstream updates a fork's enabled city directory**

```
Example: cities/bloomington/feeds.txt
Fork's version: 10 feeds, custom formatting
Upstream's version: 15 feeds, different formatting
After merge: Fork's 10 feeds, custom formatting unchanged
Result: Fork's version kept, upstream changes ignored

Note: This applies to ALL files under cities/ directories listed in ENABLED_CITIES
```

**Scenario 4: Generated files conflict**

```
Fork's report.json: last built 2026-04-20
Upstream's report.json: last built 2026-04-21
After merge: Fork's report.json unchanged (2026-04-20)
Result: Fork's generated files preserved
```

**Scenario 5: Regular upstream changes**

```
Upstream updates: scripts/combine_ics.py, docs/procedures.md
After merge: Both files updated from upstream
Result: Normal Git merge behavior for non-filtered files
```

### Testing Strategy

**Manual verification after implementation:**

1. **Test with dry-run merge:**
   ```bash
   git fetch upstream
   git merge --no-commit --no-ff upstream/main
   # Inspect working tree
   ls cities/  # Should show only bloomington
   cat cities.json  # Should have only bloomington
   git merge --abort
   ```

2. **Test with actual merge:**
   ```bash
   git merge upstream/main
   # Verify no conflicts in cities/, cities.json, report.json, version.txt
   git log --oneline -1  # Check merge commit created
   ```

3. **Edge case: New city in upstream:**
   - Check upstream for cities not in fork
   - Verify they don't appear after merge

4. **Edge case: Script missing:**
   ```bash
   mv scripts/merge-cities-filter.sh scripts/merge-cities-filter.sh.bak
   git merge upstream/main
   # Should fail with clear error about missing driver
   mv scripts/merge-cities-filter.sh.bak scripts/merge-cities-filter.sh
   ```

5. **Edge case: Malformed cities.json:**
   - Manually corrupt cities.json syntax
   - Attempt merge
   - Verify script exits 1 and shows conflict

### Error Handling and Recovery

**If merge goes wrong:**

Before committing:
```bash
git merge --abort
```

After committing:
```bash
git reset --hard HEAD^
```

**If script fails:**

1. Git shows conflict in the file
2. User sees error message from script (stderr)
3. User can:
   - Fix the issue (e.g., install jq)
   - Manually resolve conflict
   - Abort merge and investigate

**Script failure modes:**

- `jq` not installed → Exit 1, clear error message
- Invalid JSON in cities.json → Exit 1, show jq error
- File permissions issue → Exit 1, show OS error
- Any unexpected error → Exit 1, preserve original file

### Implementation Checklist

1. Create `scripts/merge-cities-filter.sh` with:
   - Argument parsing
   - Path detection (cities.json vs cities/**)
   - JSON filtering logic for cities.json
   - Keep-ours logic for cities/** files
   - Error handling and validation
   - Executable permissions

2. Update `.gitattributes`:
   - Add cities/** and cities.json rules
   - Add generated file rules
   - Commit to repo

3. Document ENABLED_CITIES environment variable:
   - Document using `.envrc` (with direnv) or `.env` in the repo
   - Include examples for single-city and multi-city forks
   - Note that these files are gitignored
   - Emphasize keeping local env var in sync with GitHub variable

4. Set ENABLED_CITIES repository variable in GitHub:
   - Navigate to Settings > Secrets and variables > Actions > Variables
   - Add new variable with same value as local `ENABLED_CITIES`
   - Verify workflow respects this variable

5. Update `docs/syncing-your-fork.md`:
   - Add setup section with environment variable and git config commands
   - Include examples for both single and multi-city forks
   - Add GitHub variable setup instructions
   - Add troubleshooting section
   - Update existing merge instructions
   - Commit to repo

6. Test all scenarios listed above:
   - Single-city fork (bloomington)
   - Multi-city fork (bloomington,bedford) - if possible
   - Missing ENABLED_CITIES env var
   - Mismatched local and GitHub ENABLED_CITIES

7. Document any limitations or gotchas discovered during testing

### Future Enhancements (Not in Scope)

- Selective Bloomington file syncing (e.g., sync SOURCES_CHECKLIST.md but not feeds.txt)
- Automatic workflow conflict resolution
- Pre-merge validation that checks for unexpected changes
- Post-merge report showing what was filtered

These can be added later if needed, but the current design handles the core requirement: automatic, silent filtering of non-Bloomington cities during upstream syncs.

## Success Criteria

After implementation, the following should be true:

1. ✅ Running `git merge upstream/main` completes without conflicts in cities/, cities.json, report.json, or version.txt
2. ✅ The cities/ directory contains only enabled cities (from `ENABLED_CITIES`) after merge
3. ✅ The cities.json file contains only enabled city entries after merge  
4. ✅ Generated files remain unchanged from pre-merge state
5. ✅ Upstream changes to scripts, docs, and workflows merge normally
6. ✅ Setup takes < 5 minutes (set env var, run two git config commands, set GitHub variable)
7. ✅ No manual cleanup needed after merge
8. ✅ CI builds only process enabled cities (ENABLED_CITIES enforced)
9. ✅ Clear error messages if something goes wrong
10. ✅ Documentation updated with setup instructions and troubleshooting
11. ✅ Works for both single-city and multi-city forks
9. ✅ Clear error messages if something goes wrong
10. ✅ Documentation updated with setup instructions and troubleshooting

## Dependencies

- `jq` (JSON processor) - assumed to be installed
- `bash` - standard on macOS/Linux
- Git 2.0+ (merge driver support)
- **Optional but recommended:** `direnv` - for automatic .envrc sourcing

## Risks and Mitigations

**Risk:** Script has bugs and corrupts files during merge  
**Mitigation:** Script uses atomic writes (temp file then move), preserves originals

**Risk:** User forgets to set ENABLED_CITIES in .envrc  
**Mitigation:** Script exits with clear error message directing user to add to `.envrc` and source it

**Risk:** User forgets to source .envrc before merging (if not using direnv)  
**Mitigation:** Error message reminds them; direnv users get automatic sourcing

**Risk:** User forgets to run one-time git config setup  
**Mitigation:** Document clearly in syncing-your-fork.md, gitattributes alone won't cause harm (merge will just show normal conflicts)

**Risk:** Mismatch between .envrc ENABLED_CITIES and GitHub variable  
**Mitigation:** Document the requirement to keep them in sync; consider future enhancement to validate this

**Risk:** Upstream makes breaking changes to cities.json structure  
**Mitigation:** Script validates JSON parsing, exits with error if structure unexpected

**Risk:** Script silently fails and files get merged incorrectly  
**Mitigation:** Exit code 1 on any error, Git will show conflict and stop

**Risk:** Future maintainer doesn't understand custom merge driver  
**Mitigation:** Comprehensive documentation in spec and sync guide, clear script comments

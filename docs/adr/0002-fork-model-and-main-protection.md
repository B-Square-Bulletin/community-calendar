# 0002. Fork Model and Main Branch Protection

Date: 2026-06-28

## Status

Accepted

## Context

This repository is a hard fork of the upstream community-calendar project (judell/community-calendar). It intentionally diverges from upstream: origin/main contains ~60 Bloomington-only commits (custom scrapers, fork-specific infrastructure, city configuration) that are not present in upstream/main.

In June 2026, an accidental `git push origin HEAD:main` from a feature branch overwrote origin/main with feature commits. The recovery attempt incorrectly assumed origin/main should match upstream/main and force-pushed `upstream/main:main`, replacing the entire fork-specific history. This lost all 60 local commits from origin/main and required a multi-step reflog recovery to restore.

The root cause: no guard rails prevented the accidental push, and no documentation told the recovery agent that origin/main intentionally diverges from upstream/main.

## Decision

1. **Branch protection on origin/main.** GitHub branch protection requires pull requests for all pushes to main. The CI workflow identity (GITHUB_TOKEN) is exempt so automated build artifact commits continue to work.

2. **Hard fork model, documented.** This repository is a hard fork, not a tracking fork. origin/main ≠ upstream/main by design. This is documented in CONTEXT.md (glossary: "Fork") and AGENTS.md (agent directive).

3. **Agent directive.** AGENTS.md explicitly states: never reset or force-push origin/main to match upstream/main. Recovery procedures must preserve the fork's intentional divergence.

4. **GitHub-only guards.** No local pre-commit hooks on main. GitHub branch protection is the hard stop; local mistakes are recoverable via reflog.

## Consequences

**Easier:**
- Accidental pushes to main are blocked at the remote level
- Agents have explicit documentation of fork model — recovery procedures won't repeat the upstream-assumption error
- Fork model is visible to every contributor through CONTEXT.md

**Harder:**
- Every change to main requires a PR (small friction for quick fixes)
- Agents must be directed to use PR workflow for main changes

**Unchanged:**
- CI workflow continues to push build artifacts directly (bot exempt from branch protection)
- Feature branches and other branches are unaffected

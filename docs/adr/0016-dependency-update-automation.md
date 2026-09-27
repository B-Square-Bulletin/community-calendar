# 0016. Dependency Update Automation and Vulnerability Scanning

Date: 2026-09-27

## Status

Accepted.

## Context

[0015](0015-modernize-stale-runtime-dependencies.md) modernized the stale
2022-era runtime pins but named the structural cause: *"Nothing surfaced the
drift because the repository has no Dependabot/Renovate and no vulnerability
scan (tracked separately)."* It closed with an explicit deferral: adding
automation *"is policy and tooling, not versions, and deserves its own review.
Tracked in issue #163."* This is that review.

Fact on the ground: `pyproject.toml` carries exact `==` runtime pins and a
`[dependency-groups].dev` group for tooling; `uv.lock` is the resolved
lockfile installed by `uv sync` ([0005](0005-uv-for-python-dependency-management.md)).
Nothing watches either file.

## Decision

1. **Dependabot for the `uv` ecosystem, weekly and grouped.** One grouped PR
   per week carries minor and patch bumps across runtime dependencies and dev
   tools; major bumps open individually. The `uv` ecosystem (rather than `pip`)
   is required because it edits `pyproject.toml` and `uv.lock` together — a
   `pip`-ecosystem PR would touch the manifest without the lock.
2. **A native vulnerability scan on dependency changes and on a schedule.** A
   dedicated `Dependency Audit` workflow runs `uv audit --locked` on PRs that
   touch `pyproject.toml` or `uv.lock`, and weekly via cron. `uv audit` queries
   OSV and needs no extra tool dependency, so the scanner does not itself add to
   the audited surface. `--locked` guarantees the gate audits the committed
   resolution rather than a fresh one.
3. **Document the cadence.** [docs/dependencies.md](../dependencies.md) records
   what is automatic (Dependabot, the audit) and what needs a human (merging
   Dependabot PRs, acting on audit alerts), including the scoped `--ignore`
   escape hatch when no fix exists.
4. **The existing PR gates remain the merge condition.** No auto-merge: a bump
   lands only when lint, tests, and feeds validation pass.

## Consequences

**Easier:**

- Staleness and new advisories surface as PRs or failing checks instead of
  waiting for someone to notice.
- Because Dependabot ships `pyproject.toml` and `uv.lock` together, each bump
  is one reviewable change and CI exercises the exact locked environment.
- The audit runs even when nothing changed, catching advisories disclosed
  against a previously-clean lock.

**Harder:**

- `uv audit` is currently marked experimental by uv, so the command and its
  flags may shift; the workflow is a thin wrapper that is easy to update.
- Grouped minor/patch PRs bundle several bumps, so a red CI run requires
  narrowing to the offending package. Majors stay separate to limit this.
- A `--ignore` entry is a deliberate, reviewable exception rather than a silent
  bypass; it should name the advisory and a tracking issue.

## Alternatives Considered

### Renovate instead of Dependabot

Renovate is more configurable (grouping, scheduling, lockfile-only modes), but
the repository already uses GitHub-native tooling and needs no bot install or
token. Dependabot's uv support and grouping cover the requirement.

### `pip-audit` instead of `uv audit`

`pip-audit` would add a dev dependency that itself needs auditing and a separate
export step to feed it the resolution. `uv audit` reads the project's own lock
directly. The issue named either; the native tool is the smaller surface.

### Fold the audit into `validate-pr.yml`

Running it inside the existing PR workflow would couple an advisory database
change (which can fail a previously-green lock) to every PR. A separate
workflow keeps the dependency-specific trigger list and the weekly schedule
independent of the general PR suite.

### Auto-merge grouped Dependabot PRs

Rejected: a grouped minor/patch PR can still carry a behavior change, and the
repo's value is a merge that a human has seen. The gates make review cheap, not
the merge automatic.

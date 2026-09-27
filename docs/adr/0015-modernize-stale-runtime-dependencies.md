# 0015. Modernize Stale Runtime Dependencies

Date: 2026-09-26

## Status

Accepted.

## Context

[0014](0014-python-314-toolchain-floor.md) raised the toolchain to Python 3.14
and deliberately deferred the stale runtime pins: *"The stale runtime pins
(e.g. `requests` / `urllib3`) are a separate concern."* This is that concern.

Every stale pin was inherited verbatim from upstream
(`judell/community-calendar`) and carried through the uv migration
([0005](0005-uv-for-python-dependency-management.md)) one-for-one. All date to
2022:

- `requests==2.27.1` (Jan 2022) — incompatible with urllib3 2.x, so it held the
  urllib3 pin down with it.
- `urllib3==1.26.9` (Mar 2022) — the 1.26 line is end-of-life.
- `pytz==2022.1` and `Jinja2==3.1.2` — Jinja2 3.1.2 predates the
  `GHSA-cpwx-vrp4-4pq7` fix.
- transitive `charset-normalizer==2.0.12` (Feb 2022).

Nothing surfaced the drift because the repository has no Dependabot/Renovate
and no vulnerability scan (tracked separately).

Facts measured before deciding:

- Direct `urllib3` use is confined to `disable_warnings` /
  `InsecureRequestWarning`, both valid on urllib3 2.x. There is no `HTTPAdapter`,
  `Retry`, or `PoolManager` usage anywhere, so the usual urllib3-v2 breakage
  surface is absent.
- `requests` usage is a uniform `get`/`post` surface with `raise_for_status`,
  `.text`, `.json()`, and `RequestException`; no adapter customization.
- `requests 2.34.2` declares `charset_normalizer<4,>=2`, so re-resolving alone
  keeps `2.0.12`; reaching 3.x requires a deliberate move.
- `pytz` and `Jinja2` are each imported by exactly one module, and that module
  lives in the abandoned `legacy/` tree the toolchain already excludes.

## Decision

1. **Bump the four stale runtime pins to current**, keeping the repository's
   `==` pin style and `uv.lock` as the source of truth (`uv sync` installs from
   the lock): `requests==2.34.2`, `urllib3==2.8.0`, `pytz==2026.4`,
   `Jinja2==3.1.6`. `requests` and `urllib3` move together, since 2.27.1 cannot
   run on urllib3 2.x. Bump the matching dev stubs (`types-requests`,
   `types-pytz`); `types-urllib3` is dropped because urllib3 2.x ships its own
   types.
2. **Force `charset-normalizer` to 3.x** (`3.5.1`), accepting its changed
   detection heuristics rather than pinning it back to freeze decoding.
3. **Keep the `==` convention.** Do not relax pins to floors. The lockfile
   already provides reproducibility, and exact pins are the documented style
   (issue #57). Staleness is addressed by adding automation, not by loosening
   the manifest.
4. **Hold `icalendar` at 6.x.** The `<7.0.0` cap is deliberate; 7.x changes
   `Component.decoded()` to return `str`, raises `TypeError` where `ValueError`
   was raised, and moves expert APIs. Upgrade as its own change (issue #161).
5. **Bump `pytz` / `Jinja2` rather than removing them.** Removing them means
   resolving the abandoned `legacy/` tree first (issue #162).
6. **No CI or workflow changes.** Verification is `make lint` (ruff plus the
   four gating type checkers), `make test-python`, and feeds validation.

## Consequences

**Easier:**

- The runtime is off an end-of-life urllib3 and onto the supported 2.x line,
  with `requests` and its stubs aligned instead of mismatched.
- `Jinja2` carries the upstream security fix.
- The manifest no longer carries 2022-era pins, so a future interpreter bump
  (per 0014's minor-line policy) will not have to drag them along.

**Harder:**

- `charset-normalizer` 3.x can change how `Response.text` decodes a page that
  lacks a correct `Content-Type` charset. The unit suite uses fixtures and does
  not exercise live decoding, so the nightly `generate-calendar` pipeline is the
  regression net for encoding drift.
- `pytz` and `Jinja2` remain in the manifest purely for abandoned code until
  issue #162 lands.

## Alternatives Considered

### Relax the pins to floors

Let `uv.lock` pin the resolved versions and accept anything above a floor.
Rejected: it reverses the documented `==` convention (issue #57) without
solving the underlying problem, which is the absence of update automation.

### Pin `charset-normalizer<3` to freeze decoding

Rejected: it preserves today's byte-for-byte decoding but leaves a stale
dependency in place, defeating the purpose. The accepted risk is covered by the
nightly pipeline.

### Upgrade `icalendar` to 7.x in the same change

Deferred: 7.x is a genuine major with known call-site changes, and bundling it
would turn a dependency bump into an icalendar migration. Tracked in issue #161.

### Delete the abandoned `legacy/` tree to drop `pytz` and `Jinja2`

Deferred: deleting code is a separate, reviewable decision from bumping
versions. Tracked in issue #162.

### Add Dependabot/Renovate and a vulnerability scan now

Deferred: it is policy and tooling, not versions, and deserves its own review.
Tracked in issue #163.

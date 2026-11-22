# 0023. One Type Checker: Pyrefly

Date: 2026-11-21

## Status

Accepted. Supersedes [0006](0006-four-type-checkers-report-only-ratcheting.md).

## Context

ADR 0006 chose four type checkers — pyright, ty, pyrefly, and zuban in mypy
mode — on the theory that each catches a different class of issue and they
cross-check each other. The ratchet completed: all four gate in `make lint` and
the PR CI `lint` job, and pyrefly gates on warn-severity findings too.

That left four toolchains to pin, upgrade, and configure; four overlapping
diagnostic languages; and a lint step that runs the same files through four
programs. The Python typing [conformance
dashboard](https://htmlpreview.github.io/?https://github.com/python/typing/blob/main/conformance/results/results.html)
now reports pyrefly 1.5.0 at 146/146, pyright 1.1.414 at 96.2%, ty 0.0.93 at
96.9%, and zuban 0.10.2 at 146/146. Zuban matches on conformance but is a
single-maintainer project; pyrefly is backed by Meta and ships an official LSP.

We measured the cross-checking claim instead of assuming it. Nineteen isolated
probe cases covered wrong argument types, missing attributes, Optional
dereference, unannotated function bodies, return types, Liskov overrides,
TypedDict keys, protocols, non-callables, subscripting, generic invariance,
unpacking, third-party stubs, and ignore comments. The four diagnostic sets are
nested, not different. The only class the three dropped checkers catch and
pyrefly does not is an attribute error inside an unannotated function whose
parameter type has to be inferred from a typed default; zuban misses it too.
Ty's refusal to honour `# type: ignore[code]` has no effect here because the
repository contains no such comments.

In the other direction, the upgrade from pyrefly 1.2.0 to 1.5.0 caught a real
runtime bug that all four pinned checkers missed: `scrapers/jccc.py` compared a
`datetime` with a `date`, which raises `TypeError`. It type-checked because
`datetime` is a subclass of `date`.

## Decision

Run exactly one static type checker: pyrefly, pinned to `==1.5.0`, gating on
warnings (`--min-severity warn`) in `make lint` and the PR CI `lint` job.
Configuration lives in `[tool.pyrefly]` in `pyproject.toml`, using the
documented kebab-case keys. `required-version = "==1.5.0"` turns a stale binary
into a fatal configuration error rather than letting it check with different
rules.

Carry mypy's `warn_unused_ignores` across as gating `unused-ignore` and
`unused-type-ignore` warnings. Do not carry `ignore_missing_imports`: pyrefly
resolves every import in this project, and its glob form would blunt future
missing-stub errors. `check_untyped_defs` needs no carry-over because pyrefly
checks unannotated function bodies by default.

Editor support moves to pyrefly's own language server and the free
[`meta.pyrefly`](https://marketplace.visualstudio.com/items?itemName=meta.pyrefly)
extension. Contributors who use Pylance or pyright should disable it to avoid
duplicate diagnostics.

Revisit only on evidence: if a type error reaches `main`, record it and add
whichever checker would have caught it. There is no standing second checker.

## Consequences

- One toolchain to upgrade, one configuration section, one gate. Pyrefly checks
  this project's 232 files in well under a second.
- pyright's linter-style rules (duplicate imports, mutable defaults, implicit
  string concatenation, naming) are no longer reported. Ruff already owns them.
- pyright execution environments (per-path Python version, platform, or search
  path) cannot be expressed in a single pyrefly project. This repository needs
  none.
- The unannotated-parameter-inference class is no longer gated. This is a known,
  accepted gap, documented here so a future finding can be recognised rather
  than rediscovered.
- Conformance is measured against the typing spec, not this codebase. The probe
  above is the local evidence, and it can drift as pyrefly's rules change.
- A dependency bump must update both `pyrefly==` and `required-version`; a
  mismatch fails loudly, by design.

## Alternatives Considered

- **Keep pyright alongside pyrefly.** Rejected: pyright scores lower on
  conformance and the probe found no error class unique to it.
- **Keep zuban.** Rejected: equal conformance, but one maintainer against a
  larger team and an official editor story.
- **Keep ty.** Rejected: identical coverage to pyrefly on every probe case,
  slightly lower conformance, and incorrect `# type: ignore[code]` handling.
- **pyrefly plus a periodic audit run of another checker.** Rejected for now as
  the smaller version of the four-checker hedge. The tripwire is a concrete
  escaped bug, not a schedule.

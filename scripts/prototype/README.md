# PROTOTYPE — Confidence Route (throwaway)

**Question:** if we score every pair of listings sharing a start time and route them by a confidence band
(**Merge** near-certain / **Group** "looks like the same event" without deleting / **Separate**), does it get the
known pairs right, and can it avoid ever silently merging two listings that are actually different events?

**Open it:** double-click `confidence-route.html`, or `open scripts/prototype/confidence-route.html`.

It is one self-contained file. No server, no build, no dependencies.

- The pure, liftable module is `ConfidenceRoute` at the top of the file (no DOM inside). It is the bit worth keeping;
  the page around it is throwaway.
- `ConfidenceRoute.tokenSetSimilarity` is a faithful JS port of `token_set_similarity` in
  `scripts/similarity_test.py`; the scores match the Python exactly.
- Real listings are lifted from the `archive` branch `cities/bloomington/events.json` (122 listings from
  near-duplicate candidate timeslots). The four reported pairs are the rows from issue #145. Anything labelled
  "constructed" is a hand-built edge case.

## What it already shows

- **Merge is threshold- and guard-independent.** It fires only on "identical normalised title + same instant +
  compatible location". Across 0.80–0.95 the live sample merges the same 10 pairs, all correct (entity/formatting
  variance). Deletions can only come from this narrow path.
- **The threshold and the guards only move Group.** Raising 0.80 → 0.90 loses three of the four real live groups
  (FIXX, Concentus, Dr. Jekyll) — 0.80 recovers them with no cost once the two guards below are in place.
- **Token-set similarity cannot tell "same event" from "same team, different squad".** JV/Varsity/Freshman and
  Boys/Girls variants of one school-vs-opponent fixture group at 0.945–0.971, i.e. at *any* sensible threshold. The
  **squad/gender guard** removes all seven of them and keeps all four real groups.
- **"Same instant" is meaningless for all-day listings.** Every all-day event in the city starts at midnight, so two
  unrelated concurrent exhibitions (the Lilly Library's "The Motives, the Moment" vs "The Signers") grouped 12 times
  at 0.80. The **timed-only guard** drops them; exact-title Merge still catches real all-day duplicates.
- **The start-time and location guards are load-bearing.** With either off, genuinely different sessions and
  different venues collapse.
- **Grouping is transitive** (union-find): A~B and B~C pulls in A and C even when they score below threshold.

## Verdict (in progress)

0.80 + squad/gender guard + timed-only guard (on top of the existing start-time, location and clean-title guards)
gives, on the live 122-listings sample: **10 correct Merges, 4 correct Groups, 93 Separate** — and handles all four
reported pairs from #145 correctly (Cook-Off Merge; Tibet, Wine, Dance Day Group; third dance listing Separate).

## Status

Prototype. Not folded in, not tested, no error handling by design. Capture the verdict here when the question is
answered, then delete the file from `main`.

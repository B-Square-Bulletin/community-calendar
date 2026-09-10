# 0008. Date-Tab Accessibility: Hermetic Real-App Playwright + Scoped axe, Human VoiceOver Gate

Date: 2026-09-09

## Status

Accepted

## Context

Issue #109 gates the tabbed date-filtering effort on accessibility
acceptance. The ticket states it "cannot be signed off by automated checks
alone" because it needs "a person with a keyboard, a screen reader, and a
narrow viewport." At the same time, several of its criteria are structural and
machine-checkable: the pressed state is exposed, keyboard-only completion
works, focus discipline holds, and the strip wraps at 360px.

Two constraints shape how much can be automated:

- **vitest cannot see the UI.** It runs in `environment: 'node'` with a `vm` +
  stub loader (`tests/js/load-shipped.js`) that reads `Main.xmlui` and
  `helpers.js` as text. An `axe-core` scan there would inspect raw XMLUI
  markup (`<Button>`, `<HStack>`), not the DOM the browser paints. The XMLUI
  framework only compiles those components at runtime in a browser.
- **The real app is not hermetic by default.** `xmlui/index.html` boots over
  the network: CDN scripts (supabase-js, rrule) and live Supabase REST for
  event data. `xmlui/test.html` is a JS assertion report and renders no app
  DOM at all.

Inspection of the rendered app (not its source) surfaced three real gaps that
the text-level tests could not see:

1. The active tab was conveyed only by the `variant` style (`solid` vs
   `outlined`); no ARIA state was announced.
2. XMLUI renders a component `id` as the `data-xmlui-id` attribute, never a
   DOM `id`. `focusDateTabHeading()` queried `getElementById`, so the
   empty-state reset focus move silently failed in production.
3. Escape in the Custom picker closed the popup but left focus on `<body>` —
   not on the trigger, and certainly not on the Custom tab the spec names.

## Decision

1. **Automate the structural criteria in Playwright, not vitest.** A new spec,
   `tests/js/date-tabs-a11y.browser.spec.js`, matches the existing
   `**/*.browser.spec.js` glob and is therefore picked up by the existing
   `browser-tests` CI job with no workflow change.
2. **Load the real app hermetically.** The spec serves `xmlui/index.html` and
   intercepts Supabase REST (`deduplicated_events`, `event_enrichments`) with a
   deterministic fixture via `page.route`, so the run never depends on live
   data. CDN assets are allowed to load as in production.
3. **Scope the axe gate to the date-filter region.** The gating scan includes
   `[data-xmlui-id="dateTabStrip"]` and `[data-xmlui-id="dateTabHeading"]`
   with `wcag2a`/`wcag2aa` tags. A full-page scan runs for visibility but does
   not gate, so vendored components and unrelated app regions cannot block
   this ticket.
4. **Fix the semantics the automation proved missing, in scope.** Add
   `aria-pressed` to the eight date tabs and `id="customDateTab"` to the
   Custom tab; query `data-xmlui-id` in `focusDateTabHeading`; add
   `window.returnFocusToCustomTab()` plus a capture-phase Escape listener so
   Escape returns focus to the Custom tab. `openCustomPicker`'s row selector
   is aligned to the same `data-xmlui-id` contract. This deliberately deviates
   from the issue's "any failure is sent back to the blocking agent ticket"
   rule by agreement: the three known gaps are fixed inline here because their
   blocking tickets (#105-#108) are closed. Any *new* failure found by the
   human gate is still filed back, never fixed inline in the verification
   ticket.
5. **Keep the human gate.** VoiceOver speech quality and the live-data browser
   checklist stay manual, in `docs/date-tabs-a11y-checklist.md`.

## Consequences

**Easier:**
- The rendered DOM contract is proven in CI, so regressions in `aria-pressed`,
  keyboard commits, focus, Escape, or the 360px wrap fail fast.
- The suite runs on every PR through the existing browser-tests job and needs
  no new workflow.
- The `data-xmlui-id` bug class is now covered by a browser test rather than
  assumed by a `getElementById` stub.

**Harder:**
- The hermetic boot depends on XMLUI DOM internals (`data-xmlui-id`,
  `data-state="open"`, `data-mode="range"`). A vendored-bundle change to those
  attributes breaks the spec loudly; that is preferable to a silently passing
  text check, but it does couple the test to the framework.
- The region-scoped scan deliberately ignores full-page findings; a future
  full-page accessibility effort will need its own ticket.

**Unchanged:**
- vitest keeps its static-chrome and seam role (`pnpm vitest run`).
- The Python/feed/scraper pipeline and the prefetch horizon are untouched.

## Alternatives Considered

- **vitest + `vitest-axe`/jsdom.** Rejected: no rendered XMLUI, so the scan
  would assert on uncompiled markup and prove nothing about the shipped UI.
- **A purpose-built harness page rendering only the strip.** Rejected: it would
  duplicate the strip markup and drift from `Main.xmlui`; the real app is the
  only faithful source.
- **Full-page axe as the gate.** Rejected: it flags vendored components (the
  stock `DatePicker`) and unrelated app regions that are outside this ticket's
  scope, making the gate unactionable.
- **Accept the picker trigger (or `<body>`) as the post-Escape focus target.**
  Rejected: the spec explicitly says focus returns to the Custom tab, and the
  rendered app showed focus landing on `<body>`, so the criterion genuinely
  failed.

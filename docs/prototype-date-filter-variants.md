# Prototype: date filter UX variants (throwaway — never merge)

Branch: `prototype/date-filter-variants`. Ticket: [Prototype date filter UX variants for reaction](https://github.com/B-Square-Bulletin/community-calendar/issues/99), under the [filter map](https://github.com/B-Square-Bulletin/community-calendar/issues/95).

## Run it

From the repo root:

```bash
python3 -m http.server 8000
```

Then open (Bloomington data, live Supabase backend):

- A · Chips: `http://localhost:8000/xmlui/index.html?city=bloomington&variant=A`
- B · Calendar: `http://localhost:8000/xmlui/index.html?city=bloomington&variant=B`
- C · Slider: `http://localhost:8000/xmlui/index.html?city=bloomington&variant=C`
- D · Tabs (no slider): `http://localhost:8000/xmlui/index.html?city=bloomington&variant=D`
- Production (no param, untouched): `http://localhost:8000/xmlui/index.html?city=bloomington`

The switcher bar under the variants jumps between them (page reloads;
the variant lives in the URL so it is shareable). "Exit prototype"
drops the param and returns to the production slider.

## What to react to

- **A · Preset chips + collapsible custom** (RadioGroup strip, all seven
  presets + Custom… + All dates; custom opens a confirming DatePicker).
  Preset clicks commit instantly; custom commits on Proceed; clearing the
  picker resets to All dates.
- **B · Calendar-first** (no strip at all; one DatePicker whose popup
  carries forward-looking presets; auto-commits on the second click).
  Compare against A: is the strip worth its vertical space, and is
  confirm-on-Proceed vs auto-commit the right call?
- **C · Slider + presets hybrid** (day slider kept, but readout-only
  while dragging; the filter commits on release; compact preset buttons
  drive the thumbs). Compare against replacing the slider outright.
- **D · Tabbed presets, no slider** (Eventbrite-style: solid tab = active
  filter state, calendar behind the Custom tab, auto-commit picker).
  **C-vs-D is the slider's trial**: same presets and contract, slider vs
  no slider. Reaction round 1 settled the slider *feel* and put C ahead
  on structure but flagged the *look* — D answers with tabs.

Every variant shows a `Showing: <window> (<N> events)` state line. The
interesting answer is usually "the X of B with the Y of C" — say that.

## Honest caveats (prototype-grade, not spec)

- **Tonight is day-granular here** (today's window; state line says so).
  The 5pm cutoff from the semantics decision needs an intraday filter
  stage the implementer adds — the spec must call that out.
- RadioGroup strip selection seeds on mount; mid-session commits from
  another variant don't re-seed it. Reload or re-pick.
- Variant C preset buttons drive the slider via `setValue`, which fires
  `didCommit` (verified in framework Slider.spec) — if thumbs don't move
  in the checked-in bundle, that API assumption is the first suspect.
- The switcher bar reloads the page; a production version would swap
  reactively. The HStack tint/rounding on the bar uses app theme tokens;
  adjust freely, it ships nowhere.
- Weekend preset uses negative day offsets when today is Sat/Sun (window
  starts Fri, clamped by the future-only feed in practice).

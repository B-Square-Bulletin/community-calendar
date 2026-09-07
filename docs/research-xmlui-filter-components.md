# Research: XMLUI filter components and debounce patterns

Ticket: [B-Square-Bulletin/community-calendar#96](https://github.com/B-Square-Bulletin/community-calendar/issues/96)
(parent map: #95, better date filtering for the event display webapp).
Branch: `research/xmlui-filter-components` (throwaway — never merge).
Date: 2026-09-07.

All framework claims verified against primary sources in the sibling
`xmlui` checkout (`/Users/jogoodma/development/bsquarebulletin/xmlui`,
framework `xmlui/package.json` version **0.14.26**), plus app usage in
`xmlui/Main.xmlui` and `xmlui/components/SearchBox.xmlui`. The app runs
from the **checked-in bundle** `xmlui/xmlui/xmlui-standalone.umd.js`
(6.6 MB, tracked in git, updated by hand — e.g. commits `dee08ea44`,
`05490c9c1`), so "available" means "present in that bundle", verified
via grep below.

## 1. Candidate components for date presets

There is **no ButtonGroup / Segmented / Chip select component** in the
framework. Full component list (`xmlui/src/components/`) contains
`Button`, `RadioGroup`, `Tabs`, `Toggle`, `Select`, `Badge` — no chip,
segment, or buttongroup match for
`ButtonGroup|Segmented|ButtonRow|ToggleGroup|Chip`. Options, in
preference order:

### 1a. `RadioGroup` + `Option` in an `HStack` (recommended for presets)

- Exclusive single-select, form-compatible, keyboard/screen-reader
  support. Source: `xmlui/src/components/RadioGroup/RadioGroup.md`.
- `initialValue` sets selection; `onDidChange="(val) => ..."` receives
  the selected value directly (same shape as the existing usage).
  Source: `RadioGroup.md` "Example: didChange".
- `setValue()` / `value` API for programmatic preset changes
  (e.g. clearing the preset when a custom range is picked).
  Source: `RadioGroup.md` "Example: value and setValue".
- Already the app's idiom for single-choice filters:
  `Main.xmlui:217` (layout `list`/`multicol`/`dashboard`),
  `Main.xmlui:271` (`all`/`picks` viewMode as an `HStack` of `Option`s).
- Layout is free-form — `Option`s can sit in any container, so a
  horizontal preset strip is just `<RadioGroup><HStack><Option …/>…`.
  Source: `RadioGroup.md` key features ("Contains Option that can be
  arranged in any layout structure").

### 1b. Plain `Button` row with `variant` toggling

- `Button` supports `variant="outlined"` etc. and `onClick`. The app
  already uses full-width outlined buttons as selectors
  (`Main.xmlui:153` city picker, `Main.xmlui:296` Earlier/Later).
  Source: `xmlui/src/components/Button/Button.md`,
  `Main.xmlui:152-156,296-303`.
- More styling control than `RadioGroup` (closer to a chip look), but
  selection state must be managed by hand (`variant="{…}"` per button)
  and keyboard radio semantics are lost. Fine for 3–5 presets; prefer
  `RadioGroup` for accessibility.

### 1c. `Select` dropdown (overflow, not primary)

- Already used for the category filter (`Main.xmlui:255-269`):
  `clearable`, `onDidChange="(val) => …"`, `value` binding,
  `dropdownHeight`. Good if presets outgrow horizontal space, or as a
  compact mobile fallback. Source: `xmlui/src/components/Select/Select.tsx`
  (events: `didChange`; APIs: `setValue`, `value`, `focus`).

### 1d. `Tabs` — not recommended for presets

- `Tabs`/`TabItem` couples selection to content panels (only the active
  tab mounts by default; `keepMounted` opt-out) and `onDidChange`
  yields `(newIndex, id, label)` — tab identity, not a filter value.
  Source: `xmlui/src/components/Tabs/Tabs.md`. Overkill for a preset
  strip; use only if each preset gets its own panel.

### 1e. `Badge` — display only, not a selector

- `Badge` has `value`, `variant` (`badge`|`pill`), `colorMap` — but **no
  events and no selection API**. Source:
  `xmlui/src/components/Badge/Badge.md`. Usable to *render* an active
  filter token, never to select one.

## 2. Candidate components for a custom range

### 2a. `DatePicker mode="range"` (recommended)

- `mode="single"|"range"`; range value is a `{ from, to }` object of
  date strings in the active `dateFormat`. Eight formats supported
  (`MM/dd/yyyy` default, `yyyy-MM-dd`, …). Source:
  `xmlui/src/components/DatePicker/DatePicker.md`,
  `DatePicker.tsx` (`value`/`mode` metadata).
- **Built-in presets**: `showPresets="true"` shows Last 7 days /
  Last 30 days / This month / Last month; `presets` accepts
  comma-separated/array built-in keys, `{ value, label }` relabels, or
  fully custom `{ label, from, to }` ranges parsed with `dateFormat`.
  Supplying `presets` turns the preset list on; `showPresets="false"`
  (or `presets="false"`) forces it off. Full built-in key set (13):
  `thisWeek lastWeek thisMonth lastMonth thisQuarter lastQuarter
  thisYear lastYear last3Days last7Days last14Days last30Days last90Days`,
  plus case/space-insensitive aliases (`"last 7 days"`, `last7days`, …).
  Source: `DatePicker.tsx` (`presets`/`showPresets` metadata),
  `DatePickerReact.tsx:160-210` (`PRESET_LABELS`, `DEFAULT_PRESETS`,
  `PRESET_ALIASES`), `resolvePresets` (`DatePickerReact.tsx:584-636`).
- **Commit control**: `confirmRangeSelection` adds a Cancel/Proceed
  footer so the range commits only on explicit confirm; default
  auto-commits on the second click and closes. Source: `DatePicker.tsx`
  metadata.
- Range publishes only when **both** slots are filled (or cleared);
  single mode publishes every change. Source: `shouldPublishValue`
  (`DatePickerReact.tsx:566-574`), `emitValue` (`:1134-1144`).
- Typed input commits on blur/Enter; incomplete edits revert to the
  committed value. `min`/`max` (`startDate`/`endDate` props),
  `disabledDates` (single/array/range/before/after/dayOfWeek/predicate),
  `setValue`/`getValue` API, mobile bottom-sheet ≤640px.
  Source: `DatePickerReact.tsx` (`DateField` blur handling `:913-926`,
  `isDateUnavailable` `:1118-1126`), `DatePicker.md` (`disabledDates`).
- Note the presets are **backward-looking** ("Last N days", "This
  month") — an events app likely wants *forward* presets ("This
  weekend", "Next 7 days"). Those are expressible as custom
  `{ label, from, to }` objects, but `from`/`to` are fixed dates parsed
  at render, so rolling windows need re-computation (rebind `presets`
  or `initialValue` when the day rolls over).

### 2b. `DateInput mode="range"` (lightweight alternative)

- Keyboard-only segmented date entry, same `single`|`range` modes and
  `dateFormat` set, `clearable`, `setValue` API. `didChange` fires when
  an edited part loses focus with a valid value. No calendar popup, no
  presets. Source: `xmlui/src/components/DateInput/DateInput.md`.
- Fit only if the custom range must stay a compact text field; the
  popup calendar + presets make `DatePicker` the better default.

### 2c. Existing `Slider` range (status quo, keep or replace)

- `Main.xmlui:283-291` binds a dual-thumb `Slider` to `eventDayRange`
  day offsets; `Main.xmlui:143` derives `displayEvents` via
  `filterByDayWindow(processedEvents, sliderStart, sliderEnd)`.
- `Slider` has **two** events: `didChange` fires per step crossed while
  dragging (live readout), `didCommit` fires once on release — move
  expensive work (filtering/fetching) to `didCommit`, keep `didChange`
  for the readout. The events are additive, not exclusive. Keyboard
  auto-repeat commits per repeat, so keyboard-driven sliders may still
  need a debounce. Re-seeding via `initialValue`/`minValue`/`maxValue`
  fires **no** events (the way to drive a domain that changes at
  runtime); `setValue()` fires both events and clamps against the range
  in effect at call time. Source: `xmlui/src/components/Slider/Slider.md`,
  `Slider.tsx:44-50,101-137`.
- A day-offset slider is good for scrubbing but poor for absolute
  dates ("the 2nd Saturday of next month"); presets + `DatePicker`
  range complement rather than duplicate it.

## 3. `onDidChange` semantics per component

| Component | Fires when | Payload | Debounce needed? |
|---|---|---|---|
| `TextBox` | Every keystroke (parallel-update example in docs) | new value | **Yes** — see §4 |
| `Slider` | `didChange`: every step mid-drag; `didCommit`: on release | value or `[lo, hi]` | Use `didCommit` instead; debounce only for keyboard auto-repeat |
| `DatePicker`/`DateInput` | Calendar pick / preset / blur-Enter commit; range only when complete | string or `{ from, to }` | No (discrete commits) |
| `RadioGroup`/`Select`/`Checkbox`/`Toggle` | Once per user selection | selected value | No |
| `Tabs` | Once per tab switch | `(index, id, label)` | No |
| `ChangeListener` | Any change of `listenTo` expr | `{ prevValue, newValue }` (+`changedSources`/`changes` with `listenToSources`) | Via props, see §4 |

Sources: `TextBox.md` didChange example; `Slider.md` didCommit section;
`DatePicker.md` didChange example; `RadioGroup.md` didChange example;
`ChangeListener.md` (event-arg shape, `listenToSources` precedence).

## 4. Debounce / throttle support

Three mechanisms, all present in the checked-in bundle:

1. **Global `debounce(delayMs, func, ...args)` script function.**
   Keyed by `func.toString()` in a module-level registry — the same
   markup call site reuses its timer across invocations; each call
   resets the timer and the last args win. Source:
   `xmlui/src/components-core/utils/misc.ts:586-631`; registered as a
   reserved script identifier
   (`components-core/analyzer/rules/_reserved-identifiers.ts:124`),
   exposed to markup via app-context misc-utils.
   - **Caveat**: because the key is the function *source text*, two
     textually identical inline lambdas share one timer. Keep debounced
     lambdas distinct or centralize them.
   - Canonical app usage — `SearchBox.xmlui:16`:
     `onDidChange="(val) => { draft = val; debounce(250, (v) => { … emitEvent('search', v); … }, val); }"`,
     with a `lastSent` guard against duplicate emits. The component
     follows the confine-hot-input pattern
     ([xmlui.org howto](https://www.xmlui.org/docs/howto/confine-a-hot-input-to-its-own-component),
     cited in `SearchBox.xmlui:1-3`): raw keystrokes stay in component
     scope (`var.draft`), only the settled term crosses into App scope
     via `emitEvent('search', …)`. **Copy this pattern for any
     text-driven filter.**
2. **`ChangeListener` `debounceWaitInMs` / `throttleWaitInMs` props.**
   Debounce = fire after silence (search-as-you-type, auto-save);
   throttle = fire immediately then at most once per interval (progress,
   scroll). If both are set, **debounce wins**. `listenToSources={{…}}`
   watches several named values with per-source diffs; it takes
   precedence over `listenTo` (with a logged warning). Source:
   `xmlui/src/components/ChangeListener/ChangeListener.md`.
   - Current app usage (`Main.xmlui:53-101,133-136`) wires plain
     `ChangeListener listenTo + onDidChange` for picks/enrichments/
     settings/scroll — no debounce/throttle in use, so adding one for
     date-filter side effects has no conflicts.
3. **`Slider onDidCommit`** as the drag-gesture alternative to manual
   debouncing (see §2c). Prefer it over wrapping slider `didChange` in
   `debounce()` — except for the keyboard auto-repeat case noted above.

No framework `throttle()` script function for markup exists (only the
internal `asyncThrottle` helper in `misc.ts:558-576` and
`ChangeListener`'s prop); throttle from markup via `ChangeListener`.

## 5. Version constraints

- Framework source surveyed at **0.14.26** (`xmlui/package.json`).
- The app does **not** consume the framework from npm/CDN at runtime —
  `xmlui/index.html` + `shell.js` load the committed bundle
  `xmlui/xmlui/xmlui-standalone.umd.js` (+ `xmlui-masonry.js`,
  `xmlui-grid-layout.js`, `helpers.js`). Upgrading XMLUI = rebuilding
  and committing a new bundle.
- Verified present in the **currently checked-in bundle** (grep counts
  > 0, each feature in metadata + implementation):
  `showPresets` (2), `confirmRangeSelection` (2), Slider `didCommit`
  (2), `debounceWaitInMs` (2). So presets, confirm-footer ranges,
  slider commit events, and listener debounce/throttle are all usable
  **without a bundle rebuild**. Any *newer* framework feature found in
  `xmlui/` source after the bundle's build date (bundle mtime
  2026-08-24; last bundle commit `05490c9c1`-era) must be re-grep'd in
  the bundle before relying on it.
- `docs/local-build.md` and `.github/workflows/generate-calendar.yml`
  cover the build/deploy path; `xmlui/config.json` pins themes and
  `appGlobals` (Supabase URL/key), unaffected by filter-component
  choice.

## 6. Recommendation for #95's filter design

- **Presets**: `RadioGroup` (+ `HStack` of `Option`s, incl. an "All dates"
  / clear option) reusing the `Main.xmlui:271` viewMode idiom. Discrete
  `onDidChange(val)` — no debounce. `setValue()` lets the custom-range
  picker clear/override the preset.
- **Custom range**: `DatePicker mode="range"` with a forward-looking
  custom `presets` list (`{ label, from, to }` computed in `helpers.js`
  day-offset style, like the existing `filterByDayWindow` helpers) plus
  typed/popup custom entry; consider `confirmRangeSelection` if partial
  ranges cause flicker. Its `{ from, to }` payload needs a small
  adapter into the existing `sliderStart`/`sliderEnd` day-offset vars
  (or replace those vars with ISO-date vars).
- **Reactivity**: keep the `SearchBox` confine-hot-input +
  `debounce(250, …)` pattern as the template; use `ChangeListener`
  `debounceWaitInMs` only if a *derived* multi-source condition needs
  settling; use Slider `didCommit` if the day-offset slider survives.
- No bundle upgrade required for any of the above.

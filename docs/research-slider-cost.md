# Research: slider sluggishness and recompute cost

Ticket: Research current slider sluggishness and recompute cost (B-Square-Bulletin/community-calendar#97),
child of Map: better date filtering for the event display webapp (#95).
Branch: `research/slider-recompute-cost` (throwaway — never merge).
Method: static analysis + reasoning over primary sources only. No production fix,
no measurements taken, no Supabase/pipeline changes (per map out-of-scope).

## Chain map (primary sources)

Ingest head (`xmlui/Main.xmlui:138-143`):

```xml
<variable name="hiddenSources" value="{...}" />                                          <!-- :138 -->
<variable name="expandedEnrichments" value="{window.expandEnrichments(...)}" />           <!-- :139 -->
<variable name="combinedEvents" value="{window.combineEvents(events.value, expandedEnrichments)}" /> <!-- :140 -->
<variable name="processedEvents" value="{window.processEvents(combinedEvents, hiddenSources)}" />    <!-- :141 -->
<variable name="eventDayRange" value="{processedEvents && processedEvents.length > 100 ? window.getEventDayRange(processedEvents) : null}" /> <!-- :142 -->
<variable name="displayEvents" value="{window.filterByDayWindow(processedEvents, sliderStart, sliderEnd)}" /> <!-- :143 -->
```

Slider (`xmlui/Main.xmlui:277-292`):

```xml
<VStack when="{eventDayRange && !!events.value && viewMode === 'all'}" gap="$space-0"> <!-- :277 -->
  <HStack>
    <Text ... value="{window.formatDayOffset(sliderRange ? sliderRange[0] : eventDayRange[0])}" /> <!-- :279 -->
    <SpaceFiller />
    <Text ... value="{window.formatDayOffset(sliderRange ? sliderRange[1] : eventDayRange[1])}" /> <!-- :281 -->
  </HStack>
  <Slider
    id="dateSlider"
    initialValue="{eventDayRange}" minValue="{eventDayRange[0]}" maxValue="{eventDayRange[1]}" <!-- :285-287 -->
    step="{1}" showValues="false" <!-- :288-289 -->
    onDidChange="(val) => { sliderRange = ...; sliderStart = val[0]; sliderEnd = val[1]; displayStartIndex = 0; browseStartIndex = 0; scrollRequest = scrollRequest + 1 }" /> <!-- :290 -->
</VStack>
```

List + pager (`xmlui/Main.xmlui:297-319`):

- `Earlier` button `:297-303`, `Later` button `:312-319` (reset `displayStartIndex`/`browseStartIndex`, bump `scrollRequest`).
- Multicol list `:304`: `data="{getPagedEvents(processedEvents, filterTerm, displayStartIndex, pageSizeFor(filterTerm), categoryFilter, sliderStart, sliderEnd)}"`.
- Single-col list `:308`: same 6-argument call.
- `Later` visibility `:313`: `moreHasMore(displayEvents, displayStartIndex, pageSizeFor(filterTerm))` — the **only** consumer of `displayEvents`.
- Scroll effect (`:98-101`): `ChangeListener listenTo="{scrollRequest}" onDidChange="topAnchor.scrollIntoView()"`.

Processing stages (`xmlui/helpers.js`):

- `processEvents(combined, hidden)` `:1754-1765` — one composed call:
  `buildSearchIndex(filterHiddenSources(collapseLongRunning(sortSourcesForDisplay(filterExternalExclusions(combined))), hidden))`.
- `filterByDayWindow(events, startDay, endDay)` `:1782-1791` — returns input **by reference** when
  `startDay == null` (`:1783`); otherwise one O(n) `.filter` with `new Date(e.start_time).getTime()` per row (`:1787-1790`).
- `memoizeIngest(name, extraKey)` `:1674-1694` — single-entry cache keyed on `ccArraySig(arguments[0])`
  (`:1719-1723`: `length:firstId:lastId`) plus optional scalar key.
- Memo applications `:1695-1703` + `:1792-1793`: `filterExternalExclusions`, `sortSourcesForDisplay`,
  `collapseLongRunningEvents`, `filterHiddenSources` (extra key `JSON.stringify(hidden)`), `buildSearchIndex`,
  `filterByDayWindow` (extra key `[startDay, endDay]`).
- Explicit non-memo (`:1704-1705`): "`getPagedEvents` is not memoized: it is cheap and its scalar
  arguments (page index, filter term) legitimately change."
- Instrumentation (`:1641-1657`, applied `:1744-1746`): `instrumentIngest` wraps
  `filterExternalExclusions, sortSourcesForDisplay, collapseLongRunningEvents, filterHiddenSources,
  buildSearchIndex, getPagedEvents`, recording `window.__ccIngestStats[name] = {calls, totalMs, rows}`
  and `cc:*` performance marks. Memo stats live in `window.__ccMemoStats` (`:1672-1673`).
- Boundary combiner `combineEvents` `:1727-1742` with content-signature memo + `window.__ccRefStats`
  (`:1724`) counting engine identity churn.
- `getEventDayRange(events)` `:1553-1566` — O(n) `new Date` + `setHours(0,0,0,0)` per row. **Not**
  memoized, **not** instrumented (absent from both lists above).
- `filterEvents(events, term, category)` `:254-281` — category pre-filter (`:257`), early return when
  `!term` (`:258`, resets the `_prevTerm` narrowing cache), otherwise O(n) `_search.includes` scan
  (`:266-273`) with timing pushed to `window._filterLog` (`:275-276`).
- `getPagedEvents` exists **twice** with different arities:
  - `helpers.js:285-328` (5-arg, no date handling): `filterEvents` + `slice(index, index+size)`,
    page 50 (default) with one-item overlap (`step = size - 1`, `:289`), writes
    `window._moreHasMore/_moreNextIndex/_moreHasPrev/_morePrevIndex` (`:320-325`).
  - `Globals.xs:34-57` (6-arg `dateStart, dateEnd`): own date-window `.filter` with
    `new Date(e.start_time).getTime()` per row (`:40-43`), gated on
    `dateStart/dateEnd !== eventDayRange` endpoints (`:36`), then `window.filterEvents`
    (`:45`) + slice. **This is the overload `Main.xmlui:304,308` actually call**
    (bare `getPagedEvents`, code-behind scope — contrast the `window.`-prefixed calls on `:141/:143`).
    It has **no** memoization and **no** instrumentation.

Contrast — the debounced control (`xmlui/components/SearchBox.xmlui:16`):

```xml
onDidChange="(val) => { draft = val; debounce(250, (v) => { ... emitEvent('search', v); ... }, val); }"
```

plus `syncSearchParam`'s 500 ms `replaceState` debounce (`helpers.js:58-69`). The slider (`Main.xmlui:290`)
has **neither**: raw `onDidChange` writes straight into App scope.

Page size (`xmlui/shell.js:218-220`): `pageSizeFor(term) = term ? 10 : cardPageSize` (default 50).

Volume context: fetch up to 5000 rows (`docs/search-and-performance.md:49`), observed
5015 → 3040 through dedupe (`docs/performance-investigation.md:45`), scraper horizon ~3 months
(map #95 notes). Slider renders only when `processedEvents.length > 100` (`Main.xmlui:142`).

## Evaluations per slider gesture

1. **Event volume: one `onDidChange` per drag tick, un-coalesced.** `Main.xmlui:290` fires on every
   Slider tick (step 1 day) with no `debounce`/`throttle` — compare `SearchBox.xmlui:16`. A single
   sweep across a ~90-day range can emit dozens of ticks; each tick performs **five** reactive writes
   (`sliderRange`, `sliderStart`, `sliderEnd`, `displayStartIndex = 0`, `browseStartIndex = 0`,
   plus `scrollRequest + 1`). Every write invalidates every binding that reads it.
2. **Per-tick binding fan-out.** Each tick re-evaluates, at minimum: slider labels `:279/:281`
   (`formatDayOffset`), `displayEvents` `:143`, the visible list binding (`:304` **or** `:308` —
   only one `when` branch renders, but the engine must still check both guards), pager guards
   `:297/:313` (`moreHasPrev`/`moreHasMore`), and the category menu `:266`
   (`getActiveCategories(processedEvents)`). Engine inline-`{...}` expressions are re-parsed per
   render with no parse cache (`helpers.js:1748-1752` comment), so expression size itself is per-tick cost.
3. **`processEvents` should memo-hit during a drag — verify, don't assume.** `combinedEvents` and
   `hiddenSources` do not change while dragging, so all five memoized ingest stages *should* hit
   (`:1695-1703`) and return by reference, making downstream reference checks cheap. Confirm via
   `window.__ccMemoStats` (hits/misses) and `window.__ccIngestStats` (calls still increment, hits
   show ~0 ms — by design, `:1663-1665`). The residual per-tick cost is therefore **not** the ingest
   chain; it is the un-memoized tail described next.
4. **The tail recomputes fully on every tick:**
   - `getEventDayRange(processedEvents)` (`:142` → `:1553`): full O(n) scan with two `Date` allocations
     per row, **no cache**. Its inputs never change during a drag, yet it rescans N rows per evaluation.
   - `filterByDayWindow` (`:143` → `:1782`): O(n) scan with `new Date` per row; memo **misses by design**
     every tick because `[startDay, endDay]` is part of the key (`:1792-1793`).
   - `Globals.xs getPagedEvents` (`:304/:308` → `Globals.xs:34-57`): a **second** O(n) date scan over the
     same N rows (`:40-43`), then `filterEvents` + `slice`. Its output — not `displayEvents` — is what
     the list renders.
   - `filterEvents` inside it: when `filterTerm` is empty it returns the date-filtered base directly
     (`:258`) — no `_search` scan; when a term/category is set it adds an O(m) scan over the
     windowed rows (`:257`, `:266-273`). Its `_prevTerm` narrowing cache (`:261-262`) cannot help a
     slider drag: with no term it resets every call, and with a term the date-filtered `source` array
     is freshly allocated per tick with a shifting length, defeating the `length + first-element`
     `sameInput` check.
   - React reconciliation over the resulting page (≤ 50 cards, 10 in search mode per `shell.js:218-220`).

## Pagination / scroll resets (per tick, not per gesture)

- `displayStartIndex = 0; browseStartIndex = 0` (`Main.xmlui:290`) throws away the user's page on
  **every tick**, including mid-drag. There is no settle/commit distinction.
- `scrollRequest = scrollRequest + 1` (`:290`) fires the `:98-101` listener →
  `topAnchor.scrollIntoView()` on **every tick**, yanking the viewport to the top while the thumb is
  still moving.
- Net effect: the user cannot keep their place while narrowing the window; each intermediate value
  re-pages and re-scrolls before they have finished choosing.

## Memo hits / misses during a drag (expected; confirm with `__ccMemoStats`)

| Stage | Cache? | Expected during drag | Source |
|---|---|---|---|
| `combineEvents` | content-sig memo | HIT (sigs unchanged) | `helpers.js:1727-1742` |
| `filterExternalExclusions` | `memoizeIngest` + `window.externalExclusions` key | HIT | `:1695-1696` |
| `sortSourcesForDisplay` | `memoizeIngest` | HIT | `:1697` |
| `collapseLongRunningEvents` | `memoizeIngest` (+ inner content-key cache `:806-813`) | HIT | `:1698`, `:796-895` |
| `filterHiddenSources` | `memoizeIngest`, `JSON.stringify(hidden)` key | HIT | `:1701-1702` |
| `buildSearchIndex` | `memoizeIngest` | HIT | `:1703` |
| `filterByDayWindow` | `memoizeIngest`, `[startDay, endDay]` key | **MISS every tick** (key moves) | `:1792-1793` |
| `getEventDayRange` | none | **recompute every evaluation** | `:1553-1566`, absent from `:1695-1703`/`:1744-1746` |
| `getPagedEvents` (helpers 5-arg) | explicitly none | recompute | `:1704-1705` |
| `getPagedEvents` (Globals.xs 6-arg, the one lists call) | none | recompute | `Globals.xs:34-57` |
| `filterEvents` narrowing | single-entry `_prevTerm` | no help (resets w/o term; fresh `source` identity w/ term) | `:252-281` |

Caveats worth keeping in later design: single-entry memos thrash on back-and-forth drags;
content keys (`length:firstId:lastId`) admit documented false hits on same-shaped different-content
inputs (`helpers.js:1665-1671`, collapse comment `:800-803`); the collapse stage logs HIT/MISS +
timing to `window._pipelineLog` (`:811`, `:893`).

## Rows filtered (per tick, Bloomington-scale N ≈ low thousands post-dedupe/collapse)

- `getEventDayRange`: N rows × (`new Date` + `setHours`) — pure overhead during drag (result constant).
- `filterByDayWindow`: N rows × `new Date(...).getTime()` → M output rows; M is consumed **only** by
  the `Later` guard (`Main.xmlui:313`), not by the rendered list.
- `Globals.xs getPagedEvents` date filter: N rows × `new Date(...).getTime()` again → same M rows,
  then `slice` to ≤ 50 (10 with active search).
- So each tick pays **three full scans of N** (range + two redundant window filters) to paint ≤ 50 rows,
  plus one `filterEvents` scan only when a search term/category is active. Prior art bounds the parts:
  `filterEvents` itself is 2–3 ms with reconciliation as the real bottleneck
  (`docs/search-and-performance.md:86`); historical `dedupeEvents` full passes cost 500–750 ms
  (`docs/performance-investigation.md:44-47,99-102`) — the ingest memos exist precisely to keep those
  off the drag path, and per the table above they should.

## Verdict: volume vs recompute

- **Volume dominates the *feel*:** un-debounced `onDidChange` turns one gesture into dozens of
  full-tail evaluations, each with paging + scroll resets. Even if each tail pass were cheap, firing
  it per tick and scrolling to top per tick reads as sluggish/janky.
- **Recompute dominates the *per-tick price*:** ~3N `Date`-allocating scans per tick for ≤ 50 painted
  rows, of which one (`getEventDayRange`) is provably redundant and two (`displayEvents` vs list-internal
  filter) are mutually redundant — the list never consumes `displayEvents` rows.
- **The ingest chain is (by construction) not the drag cost** — provided the memos hit. Any diagnosis
  that profiles `processEvents` during a drag without first checking `__ccMemoStats`/`__ccIngestStats`
  will misattribute the cost.

## What an interaction contract must cover (requirements, not a design)

1. **Coalesce gesture volume.** Define trailing-debounce and/or leading-throttle (with rAF) for the
   slider commit path, using the existing `SearchBox.xmlui:16` (250 ms) and `syncSearchParam` (500 ms,
   `helpers.js:58-69`) patterns as calibration, not invention. Raw per-tick App-scope writes must end.
2. **Split live affordance from committed filter.** Thumb/label feedback (`:279/:281`) may update per
   tick; the data query (window filter + paging + scroll) must fire only on settle/commit.
3. **Freeze paging and scroll until settle.** `displayStartIndex`/`browseStartIndex = 0` and
   `scrollRequest + 1` (`:290` → `:98-101`) must not execute per tick; specify settle-time
   reset-vs-preserve and scroll-restore behavior.
4. **Single date-filter stage.** Pager visibility (`:313`) and list rows (`:304/:308`) must derive from
   the **same** filtered array. Either the lists consume `displayEvents` or `displayEvents` goes away;
   keeping both scans is a bug-shaped redundancy, and the `helpers.js` vs `Globals.xs` `getPagedEvents`
   arity split must be resolved to one owner.
5. **Hoist the range computation.** `getEventDayRange` must recompute only when the `processedEvents`
   content signature changes (same `ccArraySig` discipline as `:1719-1723`), never per slider tick.
6. **Settle-aware caching.** Single-entry `filterByDayWindow` memo (`:1792-1793`) cannot help a drag by
   construction; the contract's settle semantics determine whether that memo is useful or should be
   dropped in favor of the single-stage filter from (4).
7. **URL-sync rule.** The map leaves preset/range shareability open (#95 "Not yet specified"); whatever
   is chosen must follow the `replaceState`-not-push, debounced pattern (`helpers.js:58-69`,
   `SearchBox.xmlui:16`) so slider drags never spam history or the URL bar.
8. **Verification hooks (no new infra assumed).** Acceptance should read
   `window.__ccMemoStats` / `window.__ccIngestStats` / `window._filterLog` / `window._pipelineLog` /
   `cc:*` marks plus the `node scripts/bench_collapse_long.js` perf gate (per `AGENTS.md`), asserting:
   evaluations-per-gesture ≈ 1 commit (not N ticks), tail scans-per-commit = 1, ingest memos HIT during
   drag, paging/scroll untouched until settle.

## Open questions for the contract ticket

- Settle timing values (debounce ms? throttle + trailing commit?) and whether presets vs free-drag need
  different rules.
- Settle-time paging/scroll policy: reset to top (current end-state, minus the mid-drag yanks) or
  preserve position?
- One owner for date filtering: `window.filterByDayWindow` or `Globals.xs getPagedEvents`?
- URL-sync for date state at all, and which of the above timing rules it inherits.

## Sources (every claim above traces to one of these)

- `xmlui/Main.xmlui:98-101,138-143,266,277-292,297-319`
- `xmlui/helpers.js:58-69,254-281,285-328,1553-1566,1641-1657,1658-1705,1719-1746,1748-1765,1782-1793,1816-1839`
- `xmlui/Globals.xs:34-57`
- `xmlui/components/SearchBox.xmlui:16`
- `xmlui/shell.js:218-220`
- `docs/performance-investigation.md:44-57,99-104`
- `docs/search-and-performance.md:49-56,86`
- Map (#95) and ticket (#97) bodies for scope, horizon (~3 months), and out-of-scope boundaries.

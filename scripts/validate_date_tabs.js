#!/usr/bin/env node
// validate_date_tabs.js — static chrome check for #105 (day-preset tab strip,
// slider removed) plus #106 (Tonight + This-weekend intraday tabs).
//
// WHY: the tab strip is declarative XMLUI markup with no pure-logic seam, so
// test.html unit tests don't apply (per #103 Testing Decisions, chrome is
// browser-verified above the date-math seam). These file-content assertions
// are the fast pre-check: they fail in seconds without Chromium if any #105
// acceptance criterion regresses. Source of truth stays the
// `Date tabs (#105)` group in xmlui/test.html, which fetches served files in
// the Playwright CI step.
//
// Usage:
//   node scripts/validate_date_tabs.js
//
// Exit code 0 = all checks pass, 1 = regression detected.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..', 'xmlui');
let failures = 0;
function check(name, cond) {
  if (cond) { console.log('PASS ' + name); }
  else { failures++; console.log('FAIL ' + name); }
}
function read(p) {
  try { return fs.readFileSync(path.join(ROOT, p), 'utf8'); } catch { return null; }
}
// Body of the single date commit helper (Globals.xs code-behind): every
// preset tap plus the empty-state reset funnels through commitDatePreset,
// so commit-contract assertions below read the helper body once instead of
// repeating per-button inline sequences.
function commitBody() {
  const g = read('Globals.xs') || '';
  const at = g.indexOf('function commitDatePreset(');
  return at < 0 ? '' : g.substring(at, at + 2500);
}

const main = read('Main.xmlui');
const helpers = read('helpers.js');
const shell = read('shell.js');
const index = read('index.html');
const globals = read('Globals.xs');

// --- Tab strip present (All + the four day-granular presets of #105) ---
// Tonight/Weekend/Custom arrive in later tickets and must stay untouched here.
check('main exists', !!main);
check('tab strip carries All dates tab',
  !!main && />All dates</.test(main));
check('tab strip carries Today tab',
  !!main && />Today</.test(main));
check('tab strip carries Tomorrow tab',
  !!main && />Tomorrow</.test(main));
check('tab strip carries Next 7 days tab',
  !!main && />Next 7 days</.test(main));
check('tab strip carries This month tab',
  !!main && />This month</.test(main));
check('tab strip carries Tonight tab (#106)',
  !!main && />Tonight</.test(main));
check('tab strip carries This weekend tab (#106)',
  !!main && />This weekend</.test(main));
// Tonight/Weekend landed in #106; Custom arrives in #107 (checked below).
check('tab strip wraps without horizontal scroll',
  !!main && /id="dateTabStrip"[\s\S]{0,400}?wrapContent="true"/.test(main));

// --- Slider gone outright: no dual UI, no orphaned vars feeding the list ---
check('no Slider control in markup', !!main && !/<Slider/.test(main));
check('no dateSlider id', !!main && !/dateSlider/.test(main));
check('no sliderRange var', !!main && !/sliderRange/.test(main));
check('no sliderStart var', !!main && !/sliderStart/.test(main));
check('no sliderEnd var', !!main && !/sliderEnd/.test(main));
check('no eventDayRange var', !!main && !/eventDayRange/.test(main));
check('no getEventDayRange wiring',
  !!main && !/getEventDayRange/.test(main));
check('no formatDayOffset wiring',
  !!main && !/formatDayOffset/.test(main));
check('no day-offset base feeding the list',
  !!main && !/_dateRangeBase/.test(main));
check('no filterByDayWindow wiring',
  !!main && !/filterByDayWindow/.test(main));
check('no filterByDayRange wiring',
  !!main && !/filterByDayRange/.test(main));
check('Globals.xs getPagedEvents takes no date params',
  !!globals && /function getPagedEvents\(events, term, startIndex, pageSize, category\)/.test(globals)
  && !/dateStart|dateEnd/.test(globals));
check('helpers.js drops slider helpers',
  !!helpers && !/window\.filterByDayWindow/.test(helpers)
  && !/window\.filterByDayRange/.test(helpers)
  && !/window\.getEventDayRange/.test(helpers)
  && !/window\.formatDayOffset/.test(helpers)
  && !/window\.dayOffsetToISO/.test(helpers)
  && !/window\._dateRangeBase/.test(helpers));

// --- Single committed window feeds list AND pager ---
check('one committed window variable feeds the list',
  !!main && /name="dateFilteredEvents"/.test(main));
check('pager guard reads the same window (not a second filter)',
  !!main && /moreHasMore\(dateFilteredEvents/.test(main));
check('commit resets paging and scrolls on commit only',
  !!main && /commitDatePreset\('today'\)/.test(main)
  && /displayStartIndex = 0/.test(commitBody())
  && /scrollRequest = scrollRequest \+ 1/.test(commitBody()));

// --- URL contract: replace (Back leaves), All strips date keys only ---
check('helpers.js exposes the date-tab seam',
  !!helpers && /window\.filterByDateWindow/.test(helpers)
  && /window\.dateWindowForPreset/.test(helpers)
  && /window\.syncDateParams/.test(helpers));
check('date commit syncs with history-replace (Back skips filter states)',
  !!helpers && /window\.replaceDateUrlParams/.test(helpers)
  && /replaceDateUrlParams[\s\S]{0,1200}?replaceState/.test(helpers)
  && /syncDateParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers));
check('shell.js seeds the date preset before first paint',
  !!shell && /initialDatePreset/.test(shell));
check('date-windows engine loads before shell boots',
  !!index && index.includes('date-windows.js'));

// --- Intraday tabs (#106): same commit/URL/boot contract as day presets ---
check('tonight commits via the engine with paging reset, scroll, and URL sync',
  !!main && /commitDatePreset\('tonight'\)/.test(main)
  && /dateWindowForPreset/.test(commitBody())
  && /displayStartIndex = 0/.test(commitBody())
  && /syncDateParams/.test(commitBody()));
check('weekend commits via the engine with paging reset, scroll, and URL sync',
  !!main && /commitDatePreset\('weekend'\)/.test(main)
  && /dateWindowForPreset/.test(commitBody())
  && /displayStartIndex = 0/.test(commitBody())
  && /syncDateParams/.test(commitBody()));
check('intraday tabs show pressed state when active',
  !!main && /datePreset === 'tonight' \? 'solid' : 'outlined'/.test(main)
  && /datePreset === 'weekend' \? 'solid' : 'outlined'/.test(main));
check('helpers.js date-tab presets derive from the engine canonical list (single source)',
  !!helpers && /window\.DATE_TAB_PRESETS[\s\S]{0,300}?window\.DATE_PRESETS/.test(helpers)
  && /DATE_TAB_PRESETS/.test(helpers));
check('shell.js boot seed derives the honored set from the engine list plus its alias map',
  !!shell && /window\.DATE_PRESETS/.test(shell) && /window\.DATE_PRESET_ALIASES/.test(shell)
  && /HONORED/.test(shell));
check('this month commits and boots as ?date=thismonth (#103 contract)',
  !!main && /commitDatePreset\('thismonth'\)/.test(main)
  && /datePreset === 'thismonth' \? 'solid' : 'outlined'/.test(main)
  && !!helpers && /DATE_PRESET_ALIASES/.test(helpers)
  && !!shell && /DATE_PRESET_ALIASES/.test(shell));

// --- Composition: date + search + category; counts reflect the window ---
check('category counts computed after date filtering',
  !!main && /getActiveCategories\(dateFilteredEvents\)/.test(main));
check('picks view ignores the window',
  !!main && (() => {
    const picksBlock = (main.match(/viewMode === 'picks'[\s\S]*?(?=<\/VStack>)/g) || []).join('\n');
    return !/dateWindow|datePreset|dateFilteredEvents/.test(picksBlock);
  })());

// --- Custom range picker (#107): stock range control behind the Custom tab ---
check('tab strip carries the Custom tab (#107)',
  !!main && />Custom</.test(main));
check('custom tab shows pressed state when active',
  !!main && /datePreset === 'custom' \? 'solid' : 'outlined'/.test(main));
check('custom range picker present in range mode with explicit confirm',
  !!main && /<DatePicker[\s\S]{0,600}?mode="range"/.test(main)
  && /<DatePicker[\s\S]{0,1200}?confirmRangeSelection="true"/.test(main));
check('custom picker uses date-only format plus the city timezone',
  !!main && /<DatePicker[\s\S]{0,1200}?dateFormat="yyyy-MM-dd"/.test(main)
  && /<DatePicker[\s\S]{0,1200}?timeZone=/.test(main));
check('custom picker disables past dates with today as the minimum',
  !!main && /<DatePicker[\s\S]{0,1600}?disabledDates=/.test(main)
  && /<DatePicker[\s\S]{0,1600}?startDate=/.test(main));
check('custom picker offers only forward presets (no built-in backward keys)',
  !!main && /<DatePicker[\s\S]{0,1600}?presets=/.test(main)
  && !/last7Days|last30Days|thisMonth|lastMonth/.test(main));
check('custom confirm commits once via the engine with paging reset, scroll, and canonical link',
  !!main && /dateWindowForCustom\(/.test(main)
  && /datePreset = 'custom'[\s\S]{0,500}?displayStartIndex = 0/.test(main)
  && /datePreset = 'custom'[\s\S]{0,600}?syncCustomParams/.test(main));
check('horizon overrun renders the truncation label below the tabs (single copy in the engine)',
  !!main && /dateTruncationLabel/.test(main)
  && /window\.dateTruncationText\(w\)/.test(main)
  && (() => {
    const eng = read('date-windows.js') || '';
    return /Showing through/.test(eng) && /calendar currently ends there/.test(eng);
  })());
check('helpers.js exposes the custom seam',
  !!helpers && /window\.dateWindowForCustom/.test(helpers)
  && /window\.syncCustomParams/.test(helpers)
  && /window\.customForwardPresets/.test(helpers)
  && /window\.todayDateOnly/.test(helpers));
check('helpers.js custom seam commits with history-replace and canonical from/to only',
  !!helpers && /syncCustomParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers)
  && /replaceDateUrlParams[\s\S]{0,1200}?replaceState/.test(helpers));
check('shell.js boot seed honors the custom from/to pair with clamp rewrite',
  !!shell && /from/.test(shell) && /initialDatePreset = 'custom'/.test(shell));

// --- Hardening (#108): empty, truncation, embed, Back ---
check('tab strip carries a heading for the empty-reset focus target',
  !!main && /id="dateTabHeading"/.test(main));
check('empty window reads No events {label} with a one-tap Next 7 reset',
  !!main && /No events /.test(main)
  && /window\.dateWindowLabel\(datePreset\)/.test(main)
  && />Show next 7 days</.test(main));
check('reset commits Next 7 with paging reset, URL sync, and heading focus but no scroll',
  !!main && (() => {
    const at = main.indexOf('Show next 7 days');
    if (at < 0) return false;
    const handler = main.substring(Math.max(0, at - 900), at);
    return /commitDatePreset\('next7'/.test(handler)
      && /focusDateTabHeading/.test(handler)
      && !/scrollRequest/.test(handler)
      && /displayStartIndex = 0/.test(commitBody())
      && /syncDateParams/.test(commitBody());
  })());
check('helpers.js exposes the hardening seam',
  !!helpers && /window\.dateWindowLabel/.test(helpers)
  && /window\.dateTruncationText/.test(helpers)
  && /window\.focusDateTabHeading/.test(helpers));
check('preset commits surface the truncation label at the horizon',
  !!main && /commitDatePreset\('today'\)/.test(main)
  && /dateTruncationText/.test(commitBody())
  && /horizonEnd/.test(helpers) && /getToDate/.test(helpers));
check('shell.js boot seed restores the truncation label at the horizon',
  !!shell && /initialDateTruncationLabel/.test(shell)
  && /horizonEnd: window\.toDate/.test(shell));
check('tab strip shows identically in the embed (no embed gate)',
  !!main && (() => {
    const at = main.indexOf('id="dateTabStrip"');
    if (at < 0) return false;
    return !/window\.embed/.test(main.substring(Math.max(0, at - 600), at));
  })());
check('city stays a push while date stays a replace (Back leaves)',
  !!shell && /selectCity[\s\S]{0,300}?pushState/.test(shell)
  && /replaceDateUrlParams[\s\S]{0,1200}?replaceState/.test(helpers)
  && /syncDateParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers)
  && /syncCustomParams[\s\S]{0,400}?replaceDateUrlParams/.test(helpers));
check('date sync preserves embed; All clears only date keys',
  !!helpers && (() => {
    const r = helpers.indexOf('window.replaceDateUrlParams');
    const d = helpers.indexOf('window.syncDateParams');
    const c = helpers.indexOf('window.syncCustomParams');
    if (r < 0 || d < 0 || c < 0) return false;
    const rb = helpers.substring(r, r + 1200);
    const db = helpers.substring(d, d + 400);
    const cb = helpers.substring(c, c + 400);
    return /replaceDateUrlParams/.test(db) && /replaceDateUrlParams/.test(cb)
      && !/delete\('embed'\)/.test(rb)
      && /delete\('date'\)/.test(rb) && /delete\('from'\)/.test(rb) && /delete\('to'\)/.test(rb)
      && !/delete\('(city|search|category|embed|mode|images|cards)'\)/.test(rb);
  })());

// --- Single commit path (prio-50 dedup): one helper serves every preset
// tap plus the empty-state reset. The per-button inline commit sequences
// (dateWindowForPreset + assignments + paging reset + scroll + sync) must
// not reappear in markup; the code-behind helper owns them.
check('code-behind exposes one shared date commit helper',
  !!globals && /function commitDatePreset\(/.test(globals));
check('every preset tab routes through the shared commit helper',
  !!main && ['all', 'today', 'tonight', 'tomorrow', 'weekend', 'next7', 'thismonth'].every(function(k) {
    return main.includes("commitDatePreset('" + k + "'");
  }));
check('no inline engine commits remain in markup (single path only)',
  !!main && !/dateWindowForPreset\('/.test(main));
check('no inline preset assignments remain in markup (helper owns the commit)',
  !!main && ['all', 'today', 'tonight', 'tomorrow', 'weekend', 'next7', 'thismonth'].every(function(k) {
    // The Custom confirm keeps its own from/to path (syncCustomParams);
    // unifying it rides prio-70. Only the seven preset keys must be gone.
    return !main.includes("datePreset = '" + k + "'");
  }));

// --- Single window-resolution + truncation path (prio-70 dedup): preset,
// custom-confirm, and boot share one resolver plus dateTruncationText and a
// single copy constant in the engine. No behavior change: the behavioral
// harness (validate_date_hardening.js) proves identical windows + labels.
check('engine owns the single truncation copy plus a window formatter',
  (() => {
    const eng = read('date-windows.js') || '';
    return /TRUNCATION/.test(eng)
      && /truncationLabelForWindow/.test(eng)
      && /calendar currently ends there/.test(eng);
  })());
check('helpers preset+custom resolvers share one opts builder',
  (() => {
    const at = (helpers || '').indexOf('window.dateWindowOpts');
    if (at < 0) return false;
    const pb = (helpers || '').indexOf('window.dateWindowForPreset');
    const cb = (helpers || '').indexOf('window.dateWindowForCustom');
    if (pb < 0 || cb < 0) return false;
    const tail = helpers.substring(at, at + 300);
    if (!/getCityTimezone/.test(tail) || !/getToDate/.test(tail)) return false;
    return /dateWindowOpts\(\)/.test(helpers.substring(pb, pb + 900))
      && /dateWindowOpts\(\)/.test(helpers.substring(cb, cb + 900));
  })());
check('helpers truncation text delegates to the engine formatter (one copy)',
  !!helpers && /window\.dateTruncationText/.test(helpers)
  && /truncationLabelForWindow/.test(helpers));
check('custom confirm routes truncation through dateTruncationText (no inline copy)',
  !!main && (() => {
    const at = main.indexOf('<DatePicker');
    if (at < 0) return false;
    const handler = main.substring(at, at + 2200);
    return /dateTruncationText/.test(handler)
      && !/Showing through/.test(handler);
  })());
check('shell boot seed resolves the preset-only path via decodeDateParams (one resolver)',
  !!shell && !/resolveDatePreset\(key/.test(shell)
  && /decodeDateParams\(\{ date: key/.test(shell));
check('shell boot seed routes truncation through the shared formatter (no hand-rolled copy)',
  !!shell && /truncationLabelForWindow|dateTruncationText/.test(shell)
  && !/Showing through '/.test(shell));

// --- Committed window as one object (prio-90 Data Clumps): custom resolve/
// sync and the date filter take the window shape; call sites pass objects,
// not loose positional bounds. Helpers keep the legacy positional overloads
// so behavioral harnesses (hardening/custom) stay green — the parity pins
// there prove no behavior change.
check('date list filters through the window-object form',
  !!main && /filterByDateWindow\(processedEvents,\s*\{start:\s*dateWindowStart,\s*end:\s*dateWindowEnd\}/.test(main));
check('custom confirm resolves and syncs through the window-object form',
  !!main && (() => {
    const at = main.indexOf('<DatePicker');
    if (at < 0) return false;
    const handler = main.substring(at, at + 2200);
    return /dateWindowForCustom\(val\)/.test(handler)
      && /syncCustomParams\(w\)/.test(handler)
      && !/dateWindowForCustom\(val && val\.from/.test(handler)
      && !/syncCustomParams\(w\.from/.test(handler);
  })());
check('helpers window seams accept the object form (with positional fallback)',
  !!helpers && /window\.dateWindowForCustom = function\(rangeOrFrom/.test(helpers)
  && /window\.syncCustomParams = function\(rangeOrFrom/.test(helpers)
  && /function filterByDateWindow\(events, windowOrStartISO/.test(helpers));

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);

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
  !!helpers && /syncDateParams[\s\S]{0,800}?replaceState/.test(helpers));
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
check('helpers.js date-tab presets include the intraday keys',
  !!helpers && /'tonight'/.test(helpers) && /'weekend'/.test(helpers));
check('shell.js boot seed honors the intraday evergreen keys',
  !!shell && /HONORED[^}]*tonight/.test(shell) && /HONORED[^}]*weekend/.test(shell));
check('this month commits and boots as ?date=thismonth (#103 contract)',
  !!main && /commitDatePreset\('thismonth'\)/.test(main)
  && /datePreset === 'thismonth' \? 'solid' : 'outlined'/.test(main)
  && !!helpers && /'thismonth'/.test(helpers)
  && !!shell && /HONORED[^}]*thismonth/.test(shell));

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
check('horizon overrun renders the truncation label below the tabs',
  !!main && /Showing through/.test(main) && /calendar currently ends there/.test(main));
check('helpers.js exposes the custom seam',
  !!helpers && /window\.dateWindowForCustom/.test(helpers)
  && /window\.syncCustomParams/.test(helpers)
  && /window\.customForwardPresets/.test(helpers)
  && /window\.todayDateOnly/.test(helpers));
check('helpers.js custom seam commits with history-replace and canonical from/to only',
  !!helpers && /syncCustomParams[\s\S]{0,800}?replaceState/.test(helpers));
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
  && /syncDateParams[\s\S]{0,900}?replaceState/.test(helpers)
  && /syncCustomParams[\s\S]{0,900}?replaceState/.test(helpers));
check('date sync preserves embed; All clears only date keys',
  !!helpers && (() => {
    const d = helpers.indexOf('window.syncDateParams');
    const c = helpers.indexOf('window.syncCustomParams');
    if (d < 0 || c < 0) return false;
    const db = helpers.substring(d, d + 900);
    const cb = helpers.substring(c, c + 900);
    return !/delete\('embed'\)/.test(db) && !/delete\('embed'\)/.test(cb)
      && /delete\('date'\)/.test(db) && /delete\('from'\)/.test(db) && /delete\('to'\)/.test(db)
      && !/delete\('(city|search|category|embed|mode|images|cards)'\)/.test(db);
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

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);

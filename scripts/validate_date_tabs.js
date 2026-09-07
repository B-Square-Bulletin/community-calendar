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
check('tab strip does not carry the later-ticket Custom tab',
  !!main && !/>Custom</.test(main));
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
  !!main && /datePreset = 'today'[\s\S]{0,300}?displayStartIndex = 0/.test(main)
  && /scrollRequest = scrollRequest \+ 1/.test(main));

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
  !!main && /dateWindowForPreset\('tonight'\)/.test(main)
  && /datePreset = 'tonight'[\s\S]{0,300}?displayStartIndex = 0/.test(main)
  && /datePreset = 'tonight'[\s\S]{0,400}?syncDateParams/.test(main));
check('weekend commits via the engine with paging reset, scroll, and URL sync',
  !!main && /dateWindowForPreset\('weekend'\)/.test(main)
  && /datePreset = 'weekend'[\s\S]{0,300}?displayStartIndex = 0/.test(main)
  && /datePreset = 'weekend'[\s\S]{0,400}?syncDateParams/.test(main));
check('intraday tabs show pressed state when active',
  !!main && /datePreset === 'tonight' \? 'solid' : 'outlined'/.test(main)
  && /datePreset === 'weekend' \? 'solid' : 'outlined'/.test(main));
check('helpers.js date-tab presets include the intraday keys',
  !!helpers && /'tonight'/.test(helpers) && /'weekend'/.test(helpers));
check('shell.js boot seed honors the intraday evergreen keys',
  !!shell && /HONORED[^}]*tonight/.test(shell) && /HONORED[^}]*weekend/.test(shell));

// --- Composition: date + search + category; counts reflect the window ---
check('category counts computed after date filtering',
  !!main && /getActiveCategories\(dateFilteredEvents\)/.test(main));
check('picks view ignores the window',
  !!main && (() => {
    const picksBlock = (main.match(/viewMode === 'picks'[\s\S]*?(?=<\/VStack>)/g) || []).join('\n');
    return !/dateWindow|datePreset|dateFilteredEvents/.test(picksBlock);
  })());

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);

#!/usr/bin/env node
// validate_date_hardening.js — seam harness for #108 (empty, truncation,
// embed, Back hardening).
//
// WHY: the #108 helpers are pure (window label, truncation copy, focus move)
// or thin URL-contract wrappers, so like the #107 seam harness they run under
// bare node with a stubbed clock, city timezone, and document. Expected
// values are hand-computed literals (PST, UTC-8), never the engine's own
// output, so these tests can disagree with the code. Markup-side coverage
// lives in the `Date tabs (#108)` group in xmlui/test.html with its bare-node
// mirror in scripts/validate_date_tabs.js.
//
// Usage:
//   node scripts/validate_date_hardening.js
//
// Exit code 0 = all checks pass, 1 = regression detected.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..', 'xmlui');

// Stub browser globals before loading the shipped scripts.
global.window = {
  _categories: [],
  _sourcePriority: { aggregators: [] },
  cityFilter: 'davis',
  _cities: { davis: { timezone: 'America/Los_Angeles' } },
  location: new URL('https://example.com/?city=davis'),
  history: {
    replaceState(o, t, u) { global.window.location = new URL(u); },
    pushState(o, t, u) { global.window.location = new URL(u); },
  },
};
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };

vm.runInThisContext(fs.readFileSync(path.join(ROOT, 'date-windows.js'), 'utf8'), { filename: 'date-windows.js' });
vm.runInThisContext(fs.readFileSync(path.join(ROOT, 'helpers.js'), 'utf8'), { filename: 'helpers.js' });

// Stub the clock to Wed 2026-02-11 (04:00 PST) for every dated assertion.
const RealDate = Date;
const NOW = new RealDate('2026-02-11T12:00:00.000Z').getTime();
global.Date = class extends RealDate {
  constructor(...a) { super(...(a.length ? a : [NOW])); }
  static now() { return NOW; }
};
// Prefetch horizon: PST midnight Mar 1.
window.getToDate = () => '2026-03-01T08:00:00.000Z';

let failures = 0;
function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) { console.log('PASS ' + name); }
  else {
    failures++;
    console.log(`FAIL ${name} — got ${JSON.stringify(actual)} want ${JSON.stringify(expected)}`);
  }
}

// --- Empty-state window labels (#108): `No events {label}.` ---
check('empty label for All reads found',
  window.dateWindowLabel('all'), 'found');
check('empty labels for day presets',
  ['today', 'tomorrow'].map((p) => window.dateWindowLabel(p)), ['today', 'tomorrow']);
check('empty label for Tonight',
  window.dateWindowLabel('tonight'), 'tonight');
check('empty label for This weekend',
  window.dateWindowLabel('weekend'), 'this weekend');
check('empty label for Next 7 days',
  window.dateWindowLabel('next7'), 'in the next 7 days');
check('empty label for This month',
  window.dateWindowLabel('thismonth'), 'this month');
check('empty label for legacy month key matches This month',
  window.dateWindowLabel('month'), 'this month');
check('empty label for Custom',
  window.dateWindowLabel('custom'), 'in this date range');
check('empty label fails open on unknown keys',
  window.dateWindowLabel('bogus'), 'found');

// --- Truncation copy (#108): preset windows truncate at the horizon ---
const month = window.dateWindowForPreset('thismonth');
check('this-month window truncates at the horizon only when it overruns',
  [month.end, month.truncated],
  ['2026-03-01T08:00:00.000Z', false]);
window.getToDate = () => '2026-02-15T08:00:00.000Z';
const monthCut = window.dateWindowForPreset('thismonth');
check('this-month window truncates mid-month when the horizon is nearer',
  [monthCut.end, monthCut.truncated],
  ['2026-02-15T08:00:00.000Z', true]);
check('truncation copy names the inclusive last day',
  window.dateTruncationText(monthCut),
  'Showing through 2026-02-14 — the calendar currently ends there.');
window.getToDate = () => '2026-03-01T08:00:00.000Z';
check('no truncation copy without an overrun',
  window.dateTruncationText(month), null);
check('no truncation copy for All',
  window.dateTruncationText({ start: null, end: null, truncated: false }), null);

// --- Focus move (#108): reset lands on the tab-strip heading, no scroll ---
let focusedWith = null;
let tabIndexSet = null;
global.document = {
  getElementById(id) {
    if (id !== 'dateTabHeading') return null;
    return {
      focus(opts) { focusedWith = opts; },
      hasAttribute() { return false; },
      setAttribute(k, v) { tabIndexSet = [k, v]; },
    };
  },
};
check('reset focuses the tab-strip heading without scrolling',
  window.focusDateTabHeading(), true);
check('focus carries preventScroll',
  [focusedWith, tabIndexSet],
  [{ preventScroll: true }, ['tabindex', '-1']]);
global.document.getElementById = () => null;
check('focus fails loud (false) with no heading and no strip',
  window.focusDateTabHeading(), false);
global.document.getElementById = (id) => id === 'dateTabStrip' ? {
  focus(opts) { focusedWith = opts; },
  hasAttribute() { return true; },
  setAttribute(k, v) { tabIndexSet = [k, v]; },
} : null;
focusedWith = null;
check('focus falls back to the strip when the heading id is dropped',
  window.focusDateTabHeading(), true);
delete global.document;

// --- URL contract (#108): embed + date round-trip, All strips date keys only ---
global.Date = RealDate;
window.location = new URL('https://example.com/?city=davis&embed=true&search=x&category=y&mode=list&images=preview&cards=25');
window.syncDateParams({ preset: 'today' });
let u = new URL(window.location);
check('preset commit preserves embed and every sibling',
  [u.searchParams.get('date'), u.searchParams.get('embed'), u.searchParams.get('city'),
    u.searchParams.get('search'), u.searchParams.get('category'), u.searchParams.get('mode'),
    u.searchParams.get('images'), u.searchParams.get('cards')],
  ['today', 'true', 'davis', 'x', 'y', 'list', 'preview', '25']);
window.syncDateParams({ preset: 'all' });
u = new URL(window.location);
check('All strips only date keys and preserves city, search, category, display params',
  [u.searchParams.get('date'), u.searchParams.get('from'), u.searchParams.get('to'),
    u.searchParams.get('city'), u.searchParams.get('search'), u.searchParams.get('category'),
    u.searchParams.get('mode'), u.searchParams.get('images'), u.searchParams.get('embed'),
    u.searchParams.get('cards')],
  [null, null, null, 'davis', 'x', 'y', 'list', 'preview', 'true', '25']);
window.syncCustomParams('2026-02-12', '2026-02-14');
u = new URL(window.location);
check('custom commit preserves embed alongside the exact dates',
  [u.searchParams.get('from'), u.searchParams.get('to'), u.searchParams.get('date'),
    u.searchParams.get('embed'), u.searchParams.get('city')],
  ['2026-02-12', '2026-02-14', null, 'true', 'davis']);

// --- Invalid-link fallbacks (#108): unknown keys and malformed pairs -> All ---
check('unknown preset key falls back to All',
  window.decodeDateParams({ date: 'bogus' }, { timeZone: 'America/Los_Angeles' }).preset, 'all');
check('malformed custom pair falls back to All',
  window.decodeDateParams({ from: '2026-02-30', to: '2026-03-01' }, { timeZone: 'America/Los_Angeles' }).preset, 'all');
check('partial custom pair falls back to All',
  window.decodeDateParams({ from: '2026-02-12' }, { timeZone: 'America/Los_Angeles' }).preset, 'all');
check('canonical thismonth key decodes to the month-remainder window',
  window.decodeDateParams({ date: 'thismonth' }, { timeZone: 'America/Los_Angeles' }).preset, 'thismonth');
check('legacy month key decodes to the canonical thismonth window',
  window.decodeDateParams({ date: 'month' }, { timeZone: 'America/Los_Angeles' }).preset, 'thismonth');

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);

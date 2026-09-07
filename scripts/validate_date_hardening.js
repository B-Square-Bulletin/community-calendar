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
check('invalid pair is ignored and the valid preset wins',
  window.decodeDateParams({ date: 'today', from: 'bogus', to: '2026-02-14' }, { timeZone: 'America/Los_Angeles' }).preset, 'today');
check('partial pair is ignored and the valid preset wins',
  window.decodeDateParams({ date: 'today', from: '2026-02-12' }, { timeZone: 'America/Los_Angeles' }).preset, 'today');
check('valid pair still wins over the preset key',
  window.decodeDateParams({ date: 'today', from: '2026-02-12', to: '2026-02-14' }, { timeZone: 'America/Los_Angeles' }).preset, 'custom');
check('inverted URL pair is ignored (All when no preset)',
  window.decodeDateParams({ from: '2026-09-10', to: '2026-09-05' }, { timeZone: 'America/Los_Angeles' }).preset, 'all');
check('inverted URL pair defers to the valid preset',
  window.decodeDateParams({ date: 'today', from: '2026-09-10', to: '2026-09-05' }, { timeZone: 'America/Los_Angeles' }).preset, 'today');
check('picker path still coerces an inverted pair to the single from-day',
  window.resolveCustomRange('2026-09-10', '2026-09-05', { timeZone: 'America/Los_Angeles' }).to, '2026-09-10');
check('canonical thismonth key decodes to the month-remainder window',
  window.decodeDateParams({ date: 'thismonth' }, { timeZone: 'America/Los_Angeles' }).preset, 'thismonth');
check('legacy month key decodes to the canonical thismonth window',
  window.decodeDateParams({ date: 'month' }, { timeZone: 'America/Los_Angeles' }).preset, 'thismonth');

// --- Tonight start-time-only exclusions (prio-40): the engine reports
// startTimeOnly for Tonight but the filter matched plain start_time, leaking
// flagged all-day events and continuations into Tonight. Hand-computed PST
// literals (Wed 2026-02-11, UTC-8), never the engine's own output. ---
const TONIGHT_START = '2026-02-12T01:00:00.000Z'; // 17:00 PST
const TONIGHT_END = '2026-02-12T08:00:00.000Z';   // midnight PST
const TONIGHT_OPTS = { startTimeOnly: true, timeZone: 'America/Los_Angeles' };
const tonightIds = (list) => window.filterByDateWindow(list, TONIGHT_START, TONIGHT_END, TONIGHT_OPTS).map((e) => e.id);
check('Tonight keeps 17:00 and 23:59, drops 16:59 and next-midnight',
  tonightIds([
    { id: 'early', start_time: '2026-02-12T00:59:00.000Z' },
    { id: 'doors', start_time: '2026-02-12T01:00:00.000Z' },
    { id: 'headliner', start_time: '2026-02-12T07:59:00.000Z' },
    { id: 'midnight', start_time: '2026-02-12T08:00:00.000Z' },
  ]),
  ['doors', 'headliner']);
check('Tonight drops flagged all-day starts landing in-window',
  tonightIds([
    { id: 'flagged', start_time: '2026-02-12T03:00:00.000Z', all_day: true },
    { id: 'xcity', start_time: '2026-02-12T05:00:00.000Z', all_day: true },
    { id: 'doors', start_time: '2026-02-12T01:00:00.000Z' },
  ]),
  ['doors']);
check('Tonight keeps the multi-day starter (end ignored), drops the continuation',
  tonightIds([
    { id: 'marathon-start', start_time: '2026-02-12T03:00:00.000Z', end_time: '2026-02-14T05:00:00.000Z' },
    { id: 'marathon-cont', start_time: '2026-02-11T03:00:00.000Z', end_time: '2026-02-12T05:00:00.000Z' },
  ]),
  ['marathon-start']);
check('startTimeOnly drops a midnight-anchored start even when range-inclusive',
  window.filterByDateWindow(
    [{ id: 'unknown-time', start_time: '2026-02-12T00:00:00.000Z' }],
    '2026-02-12T00:00:00.000Z', '2026-02-12T08:00:00.000Z',
    { startTimeOnly: true, timeZone: 'UTC' }).map((e) => e.id),
  []);
check('without the flag the same window keeps unflagged-shape starts (no behavior change)',
  window.filterByDateWindow(
    [{ id: 'show', start_time: '2026-02-12T03:00:00.000Z', all_day: true }],
    TONIGHT_START, TONIGHT_END).map((e) => e.id),
  ['show']);

// --- Single-path parity (prio-70 dedup): the shared opts builder, the
// engine-owned truncation copy, and the decode-based boot resolver must
// render byte-identical windows and labels to the code they replaced. ---
check('helpers truncation delegates to the engine formatter byte-identically',
  window.dateTruncationText(monthCut),
  window.truncationLabelForWindow(monthCut, 'America/Los_Angeles'));
check('engine formatter names the inclusive last day (hand-computed PST)',
  window.truncationLabelForWindow(monthCut, 'America/Los_Angeles'),
  'Showing through 2026-02-14 — the calendar currently ends there.');
check('engine formatter is null without an overrun',
  [window.truncationLabelForWindow(month, 'America/Los_Angeles'),
   window.truncationLabelForWindow({ start: null, end: null, truncated: false }, 'America/Los_Angeles')],
  [null, null]);
check('single copy constant owns the truncation wording',
  [window.TRUNCATION_LABEL_PREFIX, window.TRUNCATION_LABEL_SUFFIX],
  ['Showing through ', ' — the calendar currently ends there.']);
check('boot-equivalent decode of a preset-only key matches the direct resolve',
  (() => {
    const via = window.decodeDateParams({ date: 'thismonth' },
      { timeZone: 'America/Los_Angeles', horizonEnd: '2026-02-15T08:00:00.000Z' });
    const direct = window.resolveDatePreset('thismonth',
      { timeZone: 'America/Los_Angeles', horizonEnd: '2026-02-15T08:00:00.000Z' });
    return [via.start, via.end, via.preset];
  })(),
  (() => {
    const direct = window.resolveDatePreset('thismonth',
      { timeZone: 'America/Los_Angeles', horizonEnd: '2026-02-15T08:00:00.000Z' });
    return [direct.start, direct.end, 'thismonth'];
  })());
check('helpers preset+custom resolvers share one opts builder',
  [typeof window.dateWindowOpts, JSON.stringify(Object.keys(window.dateWindowOpts()).sort())],
  ['function', JSON.stringify(['horizonEnd', 'timeZone'])]);

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);

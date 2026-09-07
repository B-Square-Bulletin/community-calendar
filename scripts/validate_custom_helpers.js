#!/usr/bin/env node
// validate_custom_helpers.js — seam harness for #107 (Custom range picker).
//
// WHY: dateWindowForCustom / customForwardPresets / syncCustomParams are pure
// helpers with no browser dependency, so unlike the declarative markup they
// can run under bare node with a stubbed clock and city timezone. Expected
// values are hand-computed literals (PST, UTC-8), never the engine's own
// output, so these tests can disagree with the code. Fast mirror of the
// `Date tabs (#107)` group in xmlui/test.html, which covers the markup side.
//
// Usage:
//   node scripts/validate_custom_helpers.js
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
  location: new URL('https://example.com/?city=davis&search=x&date=today'),
  history: {
    replaceState(o, t, u) { global.window.location = new URL(u); },
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

let w = window.dateWindowForCustom('2026-02-12', '2026-02-14');
check('custom basic window',
  [w.start, w.end, w.from, w.to, w.truncated, w.clamped],
  ['2026-02-12T08:00:00.000Z', '2026-02-15T08:00:00.000Z', '2026-02-12', '2026-02-14', false, false]);
check('custom partial input ignored',
  window.dateWindowForCustom('2026-02-12', null), null);
check('custom invalid input ignored',
  window.dateWindowForCustom('2026-02-30', '2026-03-01'), null);
check('custom empty input ignored',
  window.dateWindowForCustom(null, null), null);
w = window.dateWindowForCustom('2026-02-14', '2026-02-12');
check('custom inverted range coerces to single day',
  [w.start, w.end, w.to],
  ['2026-02-14T08:00:00.000Z', '2026-02-15T08:00:00.000Z', '2026-02-14']);
w = window.dateWindowForCustom('2026-01-01', '2026-02-20');
check('custom past start clamps to today',
  [w.start, w.from, w.clamped],
  ['2026-02-11T08:00:00.000Z', '2026-02-11', true]);
window.getToDate = () => '2027-03-01T08:00:00.000Z';
w = window.dateWindowForCustom('2026-02-12', '2027-02-12');
check('custom range caps at 180 days',
  [w.end, w.to], ['2026-08-11T07:00:00.000Z', '2026-08-10']);
window.getToDate = () => '2026-03-01T08:00:00.000Z';
w = window.dateWindowForCustom('2026-02-12', '2026-05-12');
check('custom end past the horizon truncates',
  [w.end, w.truncated], ['2026-03-01T08:00:00.000Z', true]);

const presets = window.customForwardPresets();
check('forward preset labels',
  presets.map((x) => x.label), ['Next 7 days', 'Next 30 days', 'This month']);
check('next-7 preset', [presets[0].from, presets[0].to], ['2026-02-11', '2026-02-17']);
check('next-30 preset', [presets[1].from, presets[1].to], ['2026-02-11', '2026-03-12']);
check('month-remainder preset', [presets[2].from, presets[2].to], ['2026-02-11', '2026-02-28']);

global.Date = RealDate;
check('picker timezone is the city zone',
  window.customPickerTimezone(), 'America/Los_Angeles');
check('today is date-only yyyy-MM-dd',
  /^\d{4}-\d{2}-\d{2}$/.test(window.todayDateOnly()), true);
check('past dates disabled before today',
  window.customDisabledDates(), [{ before: window.todayDateOnly() }]);

window.syncCustomParams('2026-02-12', '2026-02-14');
const u = new URL(window.location);
check('canonical custom link carries from/to only with siblings preserved',
  [u.searchParams.get('from'), u.searchParams.get('to'), u.searchParams.get('date'),
    u.searchParams.get('city'), u.searchParams.get('search')],
  ['2026-02-12', '2026-02-14', null, 'davis', 'x']);

console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECKS FAILED`);
process.exit(failures === 0 ? 0 : 1);

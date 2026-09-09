// tests/js/validate-custom-helpers.test.js — vitest migration of
// scripts/validate_custom_helpers.js (seam harness for #107: Custom range picker).
//
// WHY: dateWindowForCustom / customForwardPresets / syncCustomParams are pure
// helpers with no browser dependency. Expected values are hand-computed
// literals (PST, UTC-8), never the engine's own output, so these tests can
// disagree with the code.
'use strict';
import { describe, it, expect } from 'vitest';
import { loadShipped } from './load-shipped.js';

loadShipped({ url: 'https://example.com/?city=davis&search=x&date=today' });

// Stub the clock to Wed 2026-02-11 (04:00 PST) for every dated assertion.
const RealDate = Date;
const NOW = new RealDate('2026-02-11T12:00:00.000Z').getTime();
global.Date = class extends RealDate {
  constructor(...a) { super(...(a.length ? a : [NOW])); }
  static now() { return NOW; }
};
// Prefetch horizon: PST midnight Mar 1.
window.getToDate = () => '2026-03-01T08:00:00.000Z';

describe('custom window', () => {
  it('custom basic window', () => {
    const w = window.dateWindowForCustom('2026-02-12', '2026-02-14');
    expect([w.start, w.end, w.from, w.to, w.truncated, w.clamped]).toEqual(
      ['2026-02-12T08:00:00.000Z', '2026-02-15T08:00:00.000Z', '2026-02-12', '2026-02-14', false, false]);
  });
  it('custom partial input ignored', () => {
    expect(window.dateWindowForCustom('2026-02-12', null)).toEqual(null);
  });
  it('custom invalid input ignored', () => {
    expect(window.dateWindowForCustom('2026-02-30', '2026-03-01')).toEqual(null);
  });
  it('custom empty input ignored', () => {
    expect(window.dateWindowForCustom(null, null)).toEqual(null);
  });
  it('custom inverted range coerces to single day', () => {
    const w = window.dateWindowForCustom('2026-02-14', '2026-02-12');
    expect([w.start, w.end, w.to]).toEqual(
      ['2026-02-14T08:00:00.000Z', '2026-02-15T08:00:00.000Z', '2026-02-14']);
  });
  it('custom past start clamps to today', () => {
    const w = window.dateWindowForCustom('2026-01-01', '2026-02-20');
    expect([w.start, w.from, w.clamped]).toEqual(
      ['2026-02-11T08:00:00.000Z', '2026-02-11', true]);
  });
  it('custom range caps at 180 days', () => {
    window.getToDate = () => '2027-03-01T08:00:00.000Z';
    const w = window.dateWindowForCustom('2026-02-12', '2027-02-12');
    expect([w.end, w.to]).toEqual(['2026-08-11T07:00:00.000Z', '2026-08-10']);
    window.getToDate = () => '2026-03-01T08:00:00.000Z';
  });
  it('custom end past the horizon truncates', () => {
    const w = window.dateWindowForCustom('2026-02-12', '2026-05-12');
    expect([w.end, w.truncated]).toEqual(['2026-03-01T08:00:00.000Z', true]);
  });
});

describe('forward presets', () => {
  it('forward preset labels', () => {
    expect(window.customForwardPresets().map((x) => x.label)).toEqual(
      ['Next 7 days', 'Next 30 days', 'This month']);
  });
  it('next-7 preset', () => {
    const presets = window.customForwardPresets();
    expect([presets[0].from, presets[0].to]).toEqual(['2026-02-11', '2026-02-17']);
  });
  it('next-30 preset', () => {
    const presets = window.customForwardPresets();
    expect([presets[1].from, presets[1].to]).toEqual(['2026-02-11', '2026-03-12']);
  });
  it('month-remainder preset', () => {
    const presets = window.customForwardPresets();
    expect([presets[2].from, presets[2].to]).toEqual(['2026-02-11', '2026-02-28']);
  });
});

describe('picker seams', () => {
  it('picker timezone is the city zone', () => {
    global.Date = RealDate;
    expect(window.customPickerTimezone()).toEqual('America/Los_Angeles');
  });
  it('picker timezone falls back to UTC for an unknown city', () => {
    window.cityFilter = 'unknown-city';
    expect(window.customPickerTimezone()).toEqual('UTC');
    window.cityFilter = 'davis';
  });
  it('today is date-only yyyy-MM-dd', () => {
    expect(/^\d{4}-\d{2}-\d{2}$/.test(window.todayDateOnly())).toEqual(true);
  });
  it('past dates disabled before today', () => {
    expect(window.customDisabledDates()).toEqual([{ before: window.todayDateOnly() }]);
  });
  it('canonical custom link carries from/to only with siblings preserved', () => {
    window.syncCustomParams('2026-02-12', '2026-02-14');
    const u = new URL(window.location);
    expect([u.searchParams.get('from'), u.searchParams.get('to'), u.searchParams.get('date'),
      u.searchParams.get('city'), u.searchParams.get('search')]).toEqual(
      ['2026-02-12', '2026-02-14', null, 'davis', 'x']);
  });
});

// tests/js/validate-date-hardening.test.js — vitest migration of
// scripts/validate_date_hardening.js (seam harness for #108: empty,
// truncation, embed, Back hardening).
//
// WHY: same hand-computed literals (PST, UTC-8), never the engine's own
// output, so these tests can disagree with the code. Loads shipped sources
// via ./load-shipped instead of duplicating vm/file reads.
'use strict';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { loadShipped, readShipped } from './load-shipped.js';

loadShipped();

// Stub the clock to Wed 2026-02-11 (04:00 PST) for every dated assertion.
const RealDate = Date;
const NOW = new RealDate('2026-02-11T12:00:00.000Z').getTime();
global.Date = class extends RealDate {
  constructor(...a) {
    super(...(a.length ? a : [NOW]));
  }
  static now() {
    return NOW;
  }
};
// Prefetch horizon: PST midnight Mar 1.
global.window.getToDate = () => '2026-03-01T08:00:00.000Z';

// Precompute the truncation windows in original order (Mar 1 horizon, then
// Feb 15 horizon, then restore Mar 1) so later describes see the same values.
const month = global.window.dateWindowForPreset('thismonth');
global.window.getToDate = () => '2026-02-15T08:00:00.000Z';
const monthCut = global.window.dateWindowForPreset('thismonth');
global.window.getToDate = () => '2026-03-01T08:00:00.000Z';

// The original restores RealDate before the URL-contract section; every
// section from there on runs under the real clock except the one
// committed-window check that re-stubs locally.
global.Date = RealDate;

afterEach(() => {
  // Keep document stub leakage out of neighboring files; focus-move tests
  // re-set global.document per-check below.
  if (global.document) delete global.document;
});

describe('empty labels', () => {
  it('empty label for All reads found', () => {
    expect(window.dateWindowLabel('all')).toEqual('found');
  });
  it('empty labels for day presets', () => {
    expect(['today', 'tomorrow'].map((p) => window.dateWindowLabel(p))).toEqual([
      'today',
      'tomorrow',
    ]);
  });
  it('empty label for Tonight', () => {
    expect(window.dateWindowLabel('tonight')).toEqual('tonight');
  });
  it('empty label for This weekend', () => {
    expect(window.dateWindowLabel('weekend')).toEqual('this weekend');
  });
  it('empty label for Next 7 days', () => {
    expect(window.dateWindowLabel('next7')).toEqual('in the next 7 days');
  });
  it('empty label for This month', () => {
    expect(window.dateWindowLabel('thismonth')).toEqual('this month');
  });
  it('empty label for the retired month key fails open to All', () => {
    expect(window.dateWindowLabel('month')).toEqual('found');
  });
  it('empty label for Custom', () => {
    expect(window.dateWindowLabel('custom')).toEqual('in this date range');
  });
  it('empty label fails open on unknown keys', () => {
    expect(window.dateWindowLabel('bogus')).toEqual('found');
  });
});

describe('truncation copy', () => {
  it('this-month window truncates at the horizon only when it overruns', () => {
    expect([month.end, month.truncated]).toEqual(['2026-03-01T08:00:00.000Z', false]);
  });
  it('this-month window truncates mid-month when the horizon is nearer', () => {
    expect([monthCut.end, monthCut.truncated]).toEqual(['2026-02-15T08:00:00.000Z', true]);
  });
  it('truncation copy names the inclusive last day', () => {
    expect(window.dateTruncationText(monthCut)).toEqual(
      'Showing through 2026-02-14 — the calendar currently ends there.'
    );
  });
  it('no truncation copy without an overrun', () => {
    expect(window.dateTruncationText(month)).toEqual(null);
  });
  it('no truncation copy for All', () => {
    expect(window.dateTruncationText({ start: null, end: null, truncated: false })).toEqual(null);
  });
});

describe('focus move', () => {
  // XMLUI renders a component `id` as data-xmlui-id, never a DOM id, so the
  // focus seam must query that attribute (proven end-to-end in the Playwright
  // a11y spec). A stub keyed on getElementById would pass while the real app
  // silently fails to move focus.
  const focusable = () => ({
    focus(opts) {
      global.focusedWith = opts;
    },
    hasAttribute() {
      return false;
    },
    setAttribute(k, v) {
      global.tabIndexSet = [k, v];
    },
  });
  it('reset focuses the tab-strip heading without scrolling', () => {
    global.document = {
      querySelector(sel) {
        return sel === '[data-xmlui-id="dateTabHeading"]' ? focusable() : null;
      },
    };
    expect(window.focusDateTabHeading()).toEqual(true);
  });
  it('focus carries preventScroll', () => {
    global.document = {
      querySelector(sel) {
        return sel === '[data-xmlui-id="dateTabHeading"]' ? focusable() : null;
      },
    };
    window.focusDateTabHeading();
    expect([global.focusedWith, global.tabIndexSet]).toEqual([
      { preventScroll: true },
      ['tabindex', '-1'],
    ]);
  });
  it('focus fails loud (false) with no heading and no strip', () => {
    global.document = { querySelector: () => null };
    expect(window.focusDateTabHeading()).toEqual(false);
  });
  it('focus falls back to the strip when the heading id is dropped', () => {
    global.document = {
      querySelector: (sel) =>
        sel === '[data-xmlui-id="dateTabStrip"]'
          ? {
              focus(opts) {
                global.focusedWith = opts;
              },
              hasAttribute() {
                return true;
              },
              setAttribute(k, v) {
                global.tabIndexSet = [k, v];
              },
            }
          : null,
    };
    global.focusedWith = null;
    expect(window.focusDateTabHeading()).toEqual(true);
    delete global.document;
  });
});

describe('Escape returns focus to the Custom tab (#109)', () => {
  it('returnFocusToCustomTab focuses the Custom tab without scrolling', () => {
    global.document = {
      querySelector(sel) {
        return sel === '[data-xmlui-id="customDateTab"]'
          ? {
              focus(opts) {
                global.customFocusedWith = opts;
              },
            }
          : null;
      },
    };
    expect(window.returnFocusToCustomTab()).toEqual(true);
    expect(global.customFocusedWith).toEqual({ preventScroll: true });
  });
  it('returnFocusToCustomTab fails loud (false) when the tab is absent', () => {
    global.document = { querySelector: () => null };
    expect(window.returnFocusToCustomTab()).toEqual(false);
  });
});

describe('URL contract', () => {
  beforeEach(() => {
    global.window.location = new URL(
      'https://example.com/?city=davis&embed=true&search=x&category=y&mode=list&images=preview&cards=25'
    );
  });
  it('preset commit preserves embed and every sibling', () => {
    window.syncDateParams({ preset: 'today' });
    const u = new URL(window.location);
    expect([
      u.searchParams.get('date'),
      u.searchParams.get('embed'),
      u.searchParams.get('city'),
      u.searchParams.get('search'),
      u.searchParams.get('category'),
      u.searchParams.get('mode'),
      u.searchParams.get('images'),
      u.searchParams.get('cards'),
    ]).toEqual(['today', 'true', 'davis', 'x', 'y', 'list', 'preview', '25']);
  });
  it('All strips only date keys and preserves city, search, category, display params', () => {
    window.syncDateParams({ preset: 'today' });
    window.syncDateParams({ preset: 'all' });
    const u = new URL(window.location);
    expect([
      u.searchParams.get('date'),
      u.searchParams.get('from'),
      u.searchParams.get('to'),
      u.searchParams.get('city'),
      u.searchParams.get('search'),
      u.searchParams.get('category'),
      u.searchParams.get('mode'),
      u.searchParams.get('images'),
      u.searchParams.get('embed'),
      u.searchParams.get('cards'),
    ]).toEqual([null, null, null, 'davis', 'x', 'y', 'list', 'preview', 'true', '25']);
  });
  it('custom commit preserves embed alongside the exact dates', () => {
    window.syncDateParams({ preset: 'today' });
    window.syncCustomParams('2026-02-12', '2026-02-14');
    const u = new URL(window.location);
    expect([
      u.searchParams.get('from'),
      u.searchParams.get('to'),
      u.searchParams.get('date'),
      u.searchParams.get('embed'),
      u.searchParams.get('city'),
    ]).toEqual(['2026-02-12', '2026-02-14', null, 'true', 'davis']);
  });
});

describe('invalid-link fallbacks', () => {
  it('unknown preset key falls back to All', () => {
    expect(
      window.decodeDateParams({ date: 'bogus' }, { timeZone: 'America/Los_Angeles' }).preset
    ).toEqual('all');
  });
  it('malformed custom pair falls back to All', () => {
    expect(
      window.decodeDateParams(
        { from: '2026-02-30', to: '2026-03-01' },
        { timeZone: 'America/Los_Angeles' }
      ).preset
    ).toEqual('all');
  });
  it('partial custom pair falls back to All', () => {
    expect(
      window.decodeDateParams({ from: '2026-02-12' }, { timeZone: 'America/Los_Angeles' }).preset
    ).toEqual('all');
  });
  it('invalid pair is ignored and the valid preset wins', () => {
    expect(
      window.decodeDateParams(
        { date: 'today', from: 'bogus', to: '2026-02-14' },
        { timeZone: 'America/Los_Angeles' }
      ).preset
    ).toEqual('today');
  });
  it('partial pair is ignored and the valid preset wins', () => {
    expect(
      window.decodeDateParams(
        { date: 'today', from: '2026-02-12' },
        { timeZone: 'America/Los_Angeles' }
      ).preset
    ).toEqual('today');
  });
  it('valid pair still wins over the preset key', () => {
    expect(
      window.decodeDateParams(
        { date: 'today', from: '2026-02-12', to: '2026-02-14' },
        { timeZone: 'America/Los_Angeles' }
      ).preset
    ).toEqual('custom');
  });
  it('inverted URL pair is ignored (All when no preset)', () => {
    expect(
      window.decodeDateParams(
        { from: '2026-09-10', to: '2026-09-05' },
        { timeZone: 'America/Los_Angeles' }
      ).preset
    ).toEqual('all');
  });
  it('inverted URL pair defers to the valid preset', () => {
    expect(
      window.decodeDateParams(
        { date: 'today', from: '2026-09-10', to: '2026-09-05' },
        { timeZone: 'America/Los_Angeles' }
      ).preset
    ).toEqual('today');
  });
  it('picker path still coerces an inverted pair to the single from-day', () => {
    expect(
      window.resolveCustomRange('2026-09-10', '2026-09-05', { timeZone: 'America/Los_Angeles' }).to
    ).toEqual('2026-09-10');
  });
  it('canonical thismonth key decodes to the month-remainder window', () => {
    expect(
      window.decodeDateParams({ date: 'thismonth' }, { timeZone: 'America/Los_Angeles' }).preset
    ).toEqual('thismonth');
  });
  it('retired month key falls back to All (unknown = All per #103)', () => {
    expect(
      window.decodeDateParams({ date: 'month' }, { timeZone: 'America/Los_Angeles' }).preset
    ).toEqual('all');
  });
});

describe('Tonight exclusions', () => {
  const TONIGHT_START = '2026-02-12T01:00:00.000Z'; // 17:00 PST
  const TONIGHT_END = '2026-02-12T08:00:00.000Z'; // midnight PST
  const TONIGHT_OPTS = { startTimeOnly: true, timeZone: 'America/Los_Angeles' };
  const tonightIds = (list) =>
    window.filterByDateWindow(list, TONIGHT_START, TONIGHT_END, TONIGHT_OPTS).map((e) => e.id);
  it('Tonight keeps 17:00 and 23:59, drops 16:59 and next-midnight', () => {
    expect(
      tonightIds([
        { id: 'early', start_time: '2026-02-12T00:59:00.000Z' },
        { id: 'doors', start_time: '2026-02-12T01:00:00.000Z' },
        { id: 'headliner', start_time: '2026-02-12T07:59:00.000Z' },
        { id: 'midnight', start_time: '2026-02-12T08:00:00.000Z' },
      ])
    ).toEqual(['doors', 'headliner']);
  });
  it('Tonight drops flagged all-day starts landing in-window', () => {
    expect(
      tonightIds([
        { id: 'flagged', start_time: '2026-02-12T03:00:00.000Z', all_day: true },
        { id: 'xcity', start_time: '2026-02-12T05:00:00.000Z', all_day: true },
        { id: 'doors', start_time: '2026-02-12T01:00:00.000Z' },
      ])
    ).toEqual(['doors']);
  });
  it('Tonight keeps the multi-day starter (end ignored), drops the continuation', () => {
    expect(
      tonightIds([
        {
          id: 'marathon-start',
          start_time: '2026-02-12T03:00:00.000Z',
          end_time: '2026-02-14T05:00:00.000Z',
        },
        {
          id: 'marathon-cont',
          start_time: '2026-02-11T03:00:00.000Z',
          end_time: '2026-02-12T05:00:00.000Z',
        },
      ])
    ).toEqual(['marathon-start']);
  });
  it('startTimeOnly drops a midnight-anchored start even when range-inclusive', () => {
    expect(
      window
        .filterByDateWindow(
          [{ id: 'unknown-time', start_time: '2026-02-12T00:00:00.000Z' }],
          '2026-02-12T00:00:00.000Z',
          '2026-02-12T08:00:00.000Z',
          { startTimeOnly: true, timeZone: 'UTC' }
        )
        .map((e) => e.id)
    ).toEqual([]);
  });
  it('without the flag the same window keeps unflagged-shape starts (no behavior change)', () => {
    expect(
      window
        .filterByDateWindow(
          [{ id: 'show', start_time: '2026-02-12T03:00:00.000Z', all_day: true }],
          TONIGHT_START,
          TONIGHT_END
        )
        .map((e) => e.id)
    ).toEqual(['show']);
  });
});

describe('single-path parity', () => {
  it('helpers truncation delegates to the engine formatter byte-identically', () => {
    expect(window.dateTruncationText(monthCut)).toEqual(
      window.truncationLabelForWindow(monthCut, 'America/Los_Angeles')
    );
  });
  it('engine formatter names the inclusive last day (hand-computed PST)', () => {
    expect(window.truncationLabelForWindow(monthCut, 'America/Los_Angeles')).toEqual(
      'Showing through 2026-02-14 — the calendar currently ends there.'
    );
  });
  it('engine formatter is null without an overrun', () => {
    expect([
      window.truncationLabelForWindow(month, 'America/Los_Angeles'),
      window.truncationLabelForWindow(
        { start: null, end: null, truncated: false },
        'America/Los_Angeles'
      ),
    ]).toEqual([null, null]);
  });
  it('single copy constant owns the truncation wording', () => {
    expect([window.TRUNCATION_LABEL_PREFIX, window.TRUNCATION_LABEL_SUFFIX]).toEqual([
      'Showing through ',
      ' — the calendar currently ends there.',
    ]);
  });
  it('boot-equivalent decode of a preset-only key matches the direct resolve', () => {
    expect(
      (() => {
        const via = window.decodeDateParams(
          { date: 'thismonth' },
          { timeZone: 'America/Los_Angeles', horizonEnd: '2026-02-15T08:00:00.000Z' }
        );
        return [via.start, via.end, via.preset];
      })()
    ).toEqual(
      (() => {
        const direct = window.resolveDatePreset('thismonth', {
          timeZone: 'America/Los_Angeles',
          horizonEnd: '2026-02-15T08:00:00.000Z',
        });
        return [direct.start, direct.end, 'thismonth'];
      })()
    );
  });
  it('helpers preset+custom resolvers share one opts builder', () => {
    expect([
      typeof window.dateWindowOpts,
      JSON.stringify(Object.keys(window.dateWindowOpts()).sort()),
    ]).toEqual(['function', JSON.stringify(['horizonEnd', 'timeZone'])]);
  });
});

describe('preset keys', () => {
  it('engine owns the canonical preset list', () => {
    expect(window.DATE_PRESETS).toEqual([
      'all',
      'today',
      'tonight',
      'tomorrow',
      'weekend',
      'next7',
      'thismonth',
    ]);
  });
  it('engine exposes no alias map (unknown keys fall to All per #103)', () => {
    expect(window.DATE_PRESET_ALIASES).toEqual(undefined);
  });
  it('tab-strip list derives from the engine canonical list (same copy, not a fork)', () => {
    expect(window.DATE_TAB_PRESETS).toEqual(window.DATE_PRESETS);
  });
  it('tab-strip list is a copy (mutating it leaves the engine list intact)', () => {
    expect(
      (() => {
        window.DATE_TAB_PRESETS.push('bogus');
        const intact = window.DATE_PRESETS.indexOf('bogus') < 0;
        window.DATE_TAB_PRESETS.pop();
        return intact;
      })()
    ).toEqual(true);
  });
});

describe('committed window', () => {
  it('custom resolve accepts the {from, to} window shape', () => {
    expect(
      (() => {
        const StubDate = RealDate;
        const nowMs = new StubDate('2026-02-11T12:00:00.000Z').getTime();
        global.Date = class extends StubDate {
          constructor(...a) {
            super(...(a.length ? a : [nowMs]));
          }
          static now() {
            return nowMs;
          }
        };
        window.getToDate = () => '2026-03-01T08:00:00.000Z';
        const w = window.dateWindowForCustom({ from: '2026-02-12', to: '2026-02-14' });
        global.Date = RealDate;
        return [w.start, w.end, w.from, w.to];
      })()
    ).toEqual(['2026-02-12T08:00:00.000Z', '2026-02-15T08:00:00.000Z', '2026-02-12', '2026-02-14']);
  });
  it('custom resolve object form matches the positional form', () => {
    expect(
      (() => {
        const a = window.dateWindowForCustom({ from: '2026-02-12', to: '2026-02-14' });
        const b = window.dateWindowForCustom('2026-02-12', '2026-02-14');
        return [a.start === b.start, a.end === b.end, a.from === b.from, a.to === b.to];
      })()
    ).toEqual([true, true, true, true]);
  });
  it('custom resolve ignores a null window object', () => {
    expect(window.dateWindowForCustom(null)).toEqual(null);
  });
  it('custom sync accepts the committed window object', () => {
    expect(
      (() => {
        window.location = new URL('https://example.com/?city=davis');
        window.syncCustomParams({ from: '2026-02-12', to: '2026-02-14' });
        const u = new URL(window.location);
        return [u.searchParams.get('from'), u.searchParams.get('to'), u.searchParams.get('date')];
      })()
    ).toEqual(['2026-02-12', '2026-02-14', null]);
  });
  it('date filter accepts the {start, end} window shape with parity', () => {
    expect(
      (() => {
        const list = [
          { id: 1, start_time: '2026-02-11T10:00:00.000Z' },
          { id: 2, start_time: '2026-02-12T10:00:00.000Z' },
        ];
        const viaObj = window
          .filterByDateWindow(list, {
            start: '2026-02-11T08:00:00.000Z',
            end: '2026-02-12T08:00:00.000Z',
          })
          .map((e) => e.id);
        const viaPos = window
          .filterByDateWindow(list, '2026-02-11T08:00:00.000Z', '2026-02-12T08:00:00.000Z')
          .map((e) => e.id);
        return [viaObj, viaPos];
      })()
    ).toEqual([[1], [1]]);
  });
  it('date filter object All passes through by reference', () => {
    expect(
      (() => {
        const list = [{ id: 1, start_time: '2026-02-11T10:00:00.000Z' }];
        return window.filterByDateWindow(list, { start: null, end: null }) === list;
      })()
    ).toEqual(true);
  });
});

describe('naming', () => {
  const dateSources = {
    'date-windows.js': readShipped('date-windows.js'),
    'helpers.js': readShipped('helpers.js'),
    'shell.js': readShipped('shell.js'),
    'Globals.xs': readShipped('Globals.xs'),
    'Main.xmlui': readShipped('Main.xmlui'),
  };
  function hasDateSingleLetter(src) {
    return (
      /(?:var|const|let)\s+[wt]\s*=\s*window\.(?:dateWindowFor|resolveDate|resolveCustom|decodeDate)/.test(
        src
      ) ||
      /function\s+(?:truncationLabelForWindow|dateTruncationText)\s*\(\s*w\s*[,)]/.test(src) ||
      /function\s*\(\s*w\s*\)/.test(src) ||
      /var\s+[ft]\s*=\s*parseDateOnly/.test(src) ||
      /var\s+t\s*=\s*(?:cityToday\(\)|new Date\(e\.start_time\)|new Date\(Date\.UTC\(y, mo - 1, d\)|new Date\(value\))/.test(
        src
      ) ||
      /var\s+t1\s*=\s*addDays/.test(src) ||
      /var\s+tomorrowT\s*=\s*addDays/.test(src) ||
      /var\s+c\s*=\s*cityParts/.test(src) ||
      /const\s+w\s*=\s*window\.dateWindowForCustom/.test(src)
    );
  }
  it('no single-letter window/date locals on the date path', () => {
    expect(
      Object.entries(dateSources).map(([name, src]) => [name, !hasDateSingleLetter(src)])
    ).toEqual([
      ['date-windows.js', true],
      ['helpers.js', true],
      ['shell.js', true],
      ['Globals.xs', true],
      ['Main.xmlui', true],
    ]);
  });
});

// tests/js/commit-for.test.js — behavior pins for the one date-commit seam
// (#286). The engine decorates an already-resolved window into the state every
// path applies, so tabs, the Custom confirm, and the boot seed cannot drift.
//
// Loads the shipped engine via ./load-shipped, and feeds hand-built resolved
// windows (never the engine's own resolver output) so the expected values are
// an independent source of truth.
'use strict';
import { describe, it, expect } from 'vitest';
import { loadShipped } from './load-shipped.js';

loadShipped();

const PST = 'America/Los_Angeles';

// A resolved window as decodeDateParams/dateWindowForPreset/dateWindowForCustom
// hand it over.
function windowRange(over) {
  return Object.assign(
    { preset: 'today', start: '2026-02-11T08:00:00.000Z', end: '2026-02-12T08:00:00.000Z' },
    over
  );
}

describe('commitFor', () => {
  it('a preset commit carries the resolved window, closes Custom, and syncs an evergreen ?date= key', () => {
    expect(global.window.commitFor(windowRange({}), PST)).toEqual({
      preset: 'today',
      start: '2026-02-11T08:00:00.000Z',
      end: '2026-02-12T08:00:00.000Z',
      customOpen: false,
      truncationLabel: null,
      urlParams: { date: 'today', from: null, to: null },
      rewritten: false,
    });
  });

  it('a Custom commit carries its exact dates, opens the flag, and drops the preset key', () => {
    expect(
      global.window.commitFor(
        windowRange({
          preset: 'custom',
          from: '2026-02-12',
          to: '2026-02-14',
          start: '2026-02-12T08:00:00.000Z',
          end: '2026-02-15T08:00:00.000Z',
        }),
        PST
      )
    ).toEqual({
      preset: 'custom',
      start: '2026-02-12T08:00:00.000Z',
      end: '2026-02-15T08:00:00.000Z',
      customOpen: true,
      truncationLabel: null,
      urlParams: { date: null, from: '2026-02-12', to: '2026-02-14' },
      rewritten: false,
    });
  });

  it('a window cut at the horizon carries the shared truncation label', () => {
    expect(
      global.window.commitFor(
        windowRange({ truncated: true, end: '2026-03-01T08:00:00.000Z' }),
        PST
      ).truncationLabel
    ).toEqual('Showing through 2026-02-28 — the calendar currently ends there.');
  });

  it('a clamped Custom commit reports the rewrite from either resolver flag', () => {
    const clamped = (flag) =>
      global.window.commitFor(
        windowRange({
          preset: 'custom',
          from: '2026-02-11',
          to: '2026-02-14',
          start: '2026-02-11T08:00:00.000Z',
          end: '2026-02-15T08:00:00.000Z',
          [flag]: true,
        }),
        PST
      );
    // decodeDateParams reports `rewritten`; dateWindowForCustom reports
    // `clamped`. Both mean the URL moved, so both must surface as rewritten.
    expect([clamped('rewritten').rewritten, clamped('clamped').rewritten]).toEqual([true, true]);
    expect(clamped('clamped').urlParams).toEqual({
      date: null,
      from: '2026-02-11',
      to: '2026-02-14',
    });
  });

  it('All strips every date key and closes Custom', () => {
    expect(global.window.commitFor({ preset: 'all', start: null, end: null }, PST)).toEqual({
      preset: 'all',
      start: null,
      end: null,
      customOpen: false,
      truncationLabel: null,
      urlParams: { date: null, from: null, to: null },
      rewritten: false,
    });
  });

  it('an unknown preset fails open to All with no bounds and no ?date= key', () => {
    const commit = global.window.commitFor(windowRange({ preset: 'month' }), PST);
    expect([commit.preset, commit.start, commit.end, commit.urlParams.date]).toEqual([
      'all',
      null,
      null,
      null,
    ]);
  });

  it('a Custom window without a valid date pair fails open to All', () => {
    const commit = global.window.commitFor(
      windowRange({ preset: 'custom', from: '2026-02-12' }),
      PST
    );
    expect([commit.preset, commit.customOpen, commit.start]).toEqual(['all', false, null]);
  });
});

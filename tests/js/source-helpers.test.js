// tests/js/source-helpers.test.js — the one source-derivation seam (#169 review item 11).
//
// WHY: helpers.js, Card, and Recurring all need the same source-name parsing,
// the aggregator/location ordering, and the active city's timezone. Before this
// they each carried their own copy (Card re-implemented uniqueSourceNames /
// eventSourceNames / normalizeVenueToken / sourceMatchesLocation / orderSourceNames;
// Recurring re-implemented getCityTimezone), so the copies could drift. SourceHelpers
// is the single owner; these tests pin both its behaviour and that the three
// consumers read it rather than forking it again.
'use strict';
import { describe, it, expect } from 'vitest';
import { loadShipped, readShipped } from './load-shipped.js';

loadShipped();

describe('SourceHelpers owns the source derivation once', () => {
  it('splits, trims, and dedupes a legacy comma-joined source string', () => {
    expect(window.SourceHelpers.uniqueSourceNames('WFIU, Visit Bloomington , WFIU')).toEqual([
      'WFIU',
      'Visit Bloomington',
    ]);
  });

  it('prefers the view structured names over the comma string', () => {
    // A human source name can contain a comma; splitting the compatibility
    // string would fabricate names ("Taste" + "Inc."), so source_names wins.
    expect(
      window.SourceHelpers.eventSourceNames({
        source: 'Taste, Inc., WFIU',
        source_names: ['Taste, Inc.', 'WFIU'],
      })
    ).toEqual(['Taste, Inc.', 'WFIU']);
  });

  it('falls back to the comma string only when there are no structured names', () => {
    expect(window.SourceHelpers.eventSourceNames({ source: 'WFIU, WFIU, VB' })).toEqual([
      'WFIU',
      'VB',
    ]);
  });

  it('orders aggregators last and promotes a location-matching source', () => {
    const prev = window._sourcePriority;
    window._sourcePriority = { aggregators: ['Aggregator'] };
    try {
      expect(
        window.SourceHelpers.orderSourceNames(['Alpha', 'Aggregator', 'Zeta'], 'Zeta Hall')
      ).toEqual(['Zeta', 'Alpha', 'Aggregator']);
    } finally {
      window._sourcePriority = prev;
    }
  });

  it('reads the active city timezone', () => {
    // loadShipped defaults cityFilter to davis / America/Los_Angeles.
    expect(window.SourceHelpers.cityTimezone()).toBe('America/Los_Angeles');
  });
});

describe('Card, Recurring, and helpers read the one derivation', () => {
  it('Card.group orders raw rows through SourceHelpers.orderSourceNames', () => {
    const real = window.SourceHelpers.orderSourceNames;
    let calls = 0;
    window.SourceHelpers.orderSourceNames = function () {
      calls += 1;
      return real.apply(this, arguments);
    };
    try {
      window.Card.group([
        { id: 1, source: 'Alpha, Zeta', source_names: undefined, location: 'Zeta Hall' },
      ]);
    } finally {
      window.SourceHelpers.orderSourceNames = real;
    }
    expect(calls).toBe(1);
  });

  it('helpers sortSourcesForDisplay orders through SourceHelpers.orderSourceNames', () => {
    const real = window.SourceHelpers.orderSourceNames;
    let calls = 0;
    window.SourceHelpers.orderSourceNames = function () {
      calls += 1;
      return real.apply(this, arguments);
    };
    try {
      window.sortSourcesForDisplay([{ id: 1, source: 'Alpha, Zeta', location: 'Zeta Hall' }]);
    } finally {
      window.SourceHelpers.orderSourceNames = real;
    }
    expect(calls).toBe(1);
  });

  it('Recurring.collapse reads the timezone through SourceHelpers.cityTimezone', () => {
    const real = window.SourceHelpers.cityTimezone;
    let calls = 0;
    window.SourceHelpers.cityTimezone = function () {
      calls += 1;
      return real.apply(this, arguments);
    };
    try {
      window.Recurring.collapse(
        [{ id: 1, title: 'x', location: 'y', start_time: '2026-09-19T18:00:00Z' }],
        { now: '2026-09-19T00:00:00Z' }
      );
    } finally {
      window.SourceHelpers.cityTimezone = real;
    }
    expect(calls).toBe(1);
  });

  it('keeps no forked copy of the derivation in Card or Recurring', () => {
    const card = readShipped('card.js');
    const recurring = readShipped('recurring.js');
    expect(card).not.toMatch(/function uniqueSourceNames/);
    expect(card).not.toMatch(/function eventSourceNames/);
    expect(card).not.toMatch(/function normalizeVenueToken/);
    expect(card).not.toMatch(/function sourceMatchesLocation/);
    expect(card).not.toMatch(/function orderSourceNames/);
    expect(card).toMatch(/window\.SourceHelpers\.orderSourceNames/);
    expect(recurring).not.toMatch(/function cityTimezone/);
    expect(recurring).toMatch(/window\.SourceHelpers\.cityTimezone/);
  });
});

// tests/js/recurring-collapse.test.js — the Recurring module's public seam
// (#169/#172).
//
// WHY: Recurring owns the long-running-series weekly collapse — first
// occurrence per week, the five-occurrence minimum, and the `isRecurring` mark
// — as one pure function with an injected clock. It runs exactly once per
// pipeline, at the composition point in processEvents (after exclusions and
// source ordering, before hidden-source filtering and the search index); the
// `dedupeEvents` grouping path no longer collapses. Tests assert through the
// public interface with hand-computed literals, so they can disagree with the
// implementation instead of pinning it.
//
// The rule computes each series' time-of-day in the city timezone but anchors
// weeks to browser-local midnight (a pre-existing mixed-zone quirk, out of
// scope here). Point the harness city at the machine's own zone and build
// occurrences in that same local zone, so both halves are deterministic on any
// machine. The injected `now` is the only clock the rule-level cases use.
'use strict';
import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadShipped } from './load-shipped.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
loadShipped({ cityFilter: 'local', cities: { local: { timezone: LOCAL_TZ } } });

const DAY = 24 * 60 * 60 * 1000;
// Fixed local clock for the rule-level cases. The module must read `now` from
// its options, never from the wall clock, so these never go flaky. June 1
// avoids any DST transition inside the 4-week test window (the rule's
// pre-existing local-midnight week math loses an hour across a transition).
const NOW = new Date(2026, 5, 1, 12, 0, 0); // Mon 2026-06-01, local

// One occurrence `offsetDays` local days from `now`, at the series' shared
// local 18:00 time-of-day.
function occurrence(now, offsetDays, overrides = {}) {
  const d = new Date(now.getTime());
  d.setDate(d.getDate() + offsetDays);
  d.setHours(18, 0, 0, 0);
  return Object.assign(
    {
      id: 1,
      title: 'Weekly Sing',
      location: 'Hall',
      source: 'Venue',
      start_time: d.toISOString(),
    },
    overrides
  );
}

let emitSeq = 0;
beforeEach(() => {
  window.__ccEmitSig = 'recurring-' + ++emitSeq;
  window.clearDedupeCache();
  window.externalExclusions = null;
});

describe('Recurring.collapse is a pure rule over (events, now)', () => {
  it('returns empty for missing or empty input', () => {
    expect(window.Recurring.collapse(null, { now: NOW })).toEqual([]);
    expect(window.Recurring.collapse([], { now: NOW })).toEqual([]);
  });

  it('leaves a series below the five-occurrence minimum untouched', () => {
    const rows = [
      occurrence(NOW, 0, { id: 1 }),
      occurrence(NOW, 7, { id: 2 }),
      occurrence(NOW, 14, { id: 3 }),
      occurrence(NOW, 21, { id: 4 }),
    ];
    const out = window.Recurring.collapse(rows, { now: NOW });
    expect(out).toEqual(rows);
    // Pass-through rows are the caller's own objects, not clones.
    expect(out[0]).toBe(rows[0]);
    expect(out.some((e) => e.isRecurring)).toBe(false);
  });

  it('collapses a series at the five-occurrence minimum to one per week', () => {
    const rows = [0, 7, 14, 21, 28].map((offset) => occurrence(NOW, offset, { id: 10 + offset }));
    const out = window.Recurring.collapse(rows, { now: NOW });
    expect(out).toHaveLength(5);
    expect(out.every((e) => e.isRecurring === true)).toBe(true);
    // The first occurrence of each week survives; distinct weeks keep all five.
    expect(out.map((e) => e.id)).toEqual([10, 17, 24, 31, 38]);
  });

  it('keeps only the first occurrence of a week', () => {
    // Week 0 has two occurrences (offset 0 then offset 3); weeks 1..4 follow.
    const rows = [0, 3, 7, 14, 21, 28].map((offset) =>
      occurrence(NOW, offset, { id: 10 + offset })
    );
    const out = window.Recurring.collapse(rows, { now: NOW });
    expect(out.map((e) => e.id)).toEqual([10, 17, 24, 31, 38]);
    expect(out.every((e) => e.isRecurring === true)).toBe(true);
  });

  it('anchors weeks on the injected clock, not the wall clock', () => {
    const rows = [0, 3, 7, 14, 21, 28].map((offset) =>
      occurrence(NOW, offset, { id: 10 + offset })
    );
    // Shift "today" three days later: offset 0 falls into the previous week,
    // offset 3 and offset 7 now share week 0, so offset 7 is suppressed
    // instead of offset 3. A wall-clock reading could not produce this.
    const shifted = new Date(NOW.getTime() + 3 * DAY);
    const out = window.Recurring.collapse(rows, { now: shifted });
    expect(out.map((e) => e.id)).toEqual([10, 13, 24, 31, 38]);
  });
});

describe('Recurring runs once at the processEvents composition point', () => {
  // Real-now series: five weekly rows one week apart, so every week survives
  // and the rotation is independent of the machine's timezone.
  function seriesRows(base, firstId = 100) {
    return [0, 7, 14, 21, 28].map((offset, i) => occurrence(base, offset, { id: firstId + i }));
  }

  it('dedupeEvents groups but no longer collapses', () => {
    const rows = seriesRows(new Date());
    const out = window.dedupeEvents(rows);
    expect(out).toHaveLength(5);
    expect(out.some((e) => e.isRecurring)).toBe(false);
  });

  it('processEvents collapses and marks the series', () => {
    const rows = seriesRows(new Date());
    const out = window.processEvents(rows, []);
    expect(out.length).toBeGreaterThan(0);
    expect(out.length).toBeLessThanOrEqual(rows.length);
    // Every survivor of a recognized series carries the mark. A DST-straddling
    // run can merge two weekly buckets, so the count is not pinned; the mark is.
    expect(out.every((e) => e.isRecurring === true)).toBe(true);
  });

  it('invokes Recurring.collapse exactly once on the enrichment path', () => {
    const base = new Date();
    const rows = seriesRows(base);
    const virtual = occurrence(base, 7, {
      id: 'enrichment-9-2026-03-09T18:00:00.000Z',
      source: 'Picks: Curator',
      rrule: 'FREQ=WEEKLY',
      _enrichment_id: 9,
      _enrichment_event_id: 101,
      _enrichment_is_original_occurrence: true,
    });
    const real = window.Recurring.collapse;
    let calls = 0;
    window.Recurring.collapse = function (events, opts) {
      calls += 1;
      return real.call(this, events, opts);
    };
    try {
      window.processEvents(window.combineEvents(rows, [virtual]), []);
    } finally {
      window.Recurring.collapse = real;
    }
    expect(calls).toBe(1);
  });

  it('pins the stage order: exclusions and source ordering, then collapse, then hidden filter and search index', () => {
    const order = [];
    const names = [
      'filterExternalExclusions',
      'sortSourcesForDisplay',
      'filterHiddenSources',
      'buildSearchIndex',
    ];
    const originals = {};
    names.forEach((name) => {
      originals[name] = window[name];
      window[name] = function () {
        order.push(name);
        return originals[name].apply(this, arguments);
      };
    });
    const realCollapse = window.Recurring.collapse;
    window.Recurring.collapse = function () {
      order.push('collapse');
      return realCollapse.apply(this, arguments);
    };
    try {
      window.processEvents(seriesRows(new Date()), []);
    } finally {
      window.Recurring.collapse = realCollapse;
      names.forEach((name) => {
        window[name] = originals[name];
      });
    }
    expect(order).toEqual([
      'filterExternalExclusions',
      'sortSourcesForDisplay',
      'collapse',
      'filterHiddenSources',
      'buildSearchIndex',
    ]);
  });

  it('runs before hidden-source filtering, so hiding a source still counts its series', () => {
    const base = new Date();
    // Hide four of the five weekly rows. If collapse ran after the hidden
    // filter, the lone survivor would be below the five-occurrence minimum
    // and stay unmarked. Collapsing first marks it. The visible row is the
    // series' first occurrence, so it always survives its own week.
    const rows = seriesRows(base).map((e, i) =>
      Object.assign({}, e, { source: i === 0 ? 'Visible' : 'Hidden' })
    );
    const out = window.processEvents(rows, ['Hidden']);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe(rows[0].id);
    expect(out[0].isRecurring).toBe(true);
  });
});

describe('intended delta: the enrichment path follows the plain path for an excluded survivor', () => {
  it('keeps the non-excluded week in both paths when the collapse survivor is excluded', () => {
    const base = new Date();
    window.externalExclusions = { excludedSources: ['Excluded'] };
    // Five excluded weekly occurrences make the series long-running. The
    // non-excluded row shares week 0's title/location/time-of-day but is
    // later that week, so the collapse's week-0 survivor is the excluded row.
    const excluded = [0, 7, 14, 21, 28].map((offset, i) =>
      occurrence(base, offset, { id: 500 + i, source: 'Excluded' })
    );
    const kept = occurrence(base, 3, { id: 600, source: 'Kept' });
    const rows = excluded.concat([kept]).sort((a, b) => a.start_time.localeCompare(b.start_time));

    const plain = window.processEvents(window.combineEvents(rows, []), []);
    expect(plain.filter((e) => e.source === 'Kept')).toHaveLength(1);
    expect(plain.some((e) => e.source === 'Excluded')).toBe(false);

    // The old double-collapse dropped the whole week on this path: the first
    // pass kept the excluded survivor (suppressing the kept row), exclusions
    // then removed it, and the second pass had nothing left.
    const virtual = occurrence(base, 7, {
      id: 'enrichment-9-2026-03-09T18:00:00.000Z',
      source: 'Picks: Curator',
      rrule: 'FREQ=WEEKLY',
      _enrichment_id: 9,
      _enrichment_event_id: 501,
      _enrichment_is_original_occurrence: true,
    });
    const enriched = window.processEvents(window.combineEvents(rows, [virtual]), []);
    expect(enriched.filter((e) => e.source === 'Kept')).toHaveLength(1);
    expect(enriched.some((e) => e.source === 'Excluded')).toBe(false);
  });
});

describe('the sources dialog calls the one collapse explicitly', () => {
  it('applies Card grouping and one collapse in a named step the counts read', () => {
    const src = readFileSync(
      join(__dirname, '..', '..', 'xmlui', 'components', 'SourcesDialog.xmlui'),
      'utf8'
    );
    const matches = src.match(/window\.Recurring\.collapse\(\s*window\.Card\.groupMemo\(/g) || [];
    // One named step owns the rule; both count bindings read it, so the
    // collapse runs once, not per binding. Grouping no longer comes from the
    // legacy dedupeEvents (#169/#176).
    expect(matches).toHaveLength(1);
    expect(src).not.toContain('dedupeEvents');
  });
});

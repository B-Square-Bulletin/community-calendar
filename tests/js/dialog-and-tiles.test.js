// tests/js/dialog-and-tiles.test.js — the sources dialog and the dashboard
// tiles read the same cards as the list (#169/#176).
//
// WHY: the sources dialog counted a legacy grouping pass and the tiles did no
// client grouping or collapse at all, so either could disagree with the
// calendar's row count. Both now apply the list's rule — Card.group over the
// view's stored rows, then Recurring's weekly collapse — before the dialog's
// hidden-source filter and the tile's category/search filter. The dialog keeps
// its own inputs (its city filter, the uncommitted `localHidden` preview, no
// date window), so its counts are not expected to equal the list's; only the
// rule is shared.
//
// The dialog/tile wiring lives in markup the vm harness does not load, so its
// call sites are pinned by source-text checks; the rule's behavior is exercised
// through the same pure helpers the markup composes.
'use strict';
import { describe, it, expect, beforeEach } from 'vitest';
import { loadShipped, readShipped } from './load-shipped.js';

// Match the rule-level tests: point the harness city at the machine's own zone
// and build occurrences in that zone, so the collapse's time-of-day and week
// math are deterministic on any machine.
const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
loadShipped({ cityFilter: 'local', cities: { local: { timezone: LOCAL_TZ } } });

const DAY = 24 * 60 * 60 * 1000;

// One stored view row (the client's real input shape).
function viewRow(overrides = {}) {
  return Object.assign(
    {
      id: 1,
      title: 'Gala',
      location: 'Hall',
      category: 'Music',
      start_time: '2026-06-01T18:00:00.000Z',
      source: 'Alpha',
      source_names: ['Alpha'],
      source_urls: { Alpha: 'https://alpha.example/e' },
      description: '',
      duplicate_group: null,
      merged_ids: null,
    },
    overrides
  );
}

// One occurrence of a weekly series `offsetDays` days from `base`, at a shared
// local 18:00 time-of-day (the series key the collapse reads).
function occurrence(base, offsetDays, overrides = {}) {
  const d = new Date(base.getTime());
  d.setDate(d.getDate() + offsetDays);
  d.setHours(18, 0, 0, 0);
  return viewRow({ id: 100 + offsetDays, start_time: d.toISOString(), ...overrides });
}

let emitSeq = 0;
beforeEach(() => {
  window.__ccEmitSig = 'dialog-tiles-' + ++emitSeq;
  window.clearDedupeCache();
});

describe('the sources dialog groups and collapses through the shared rule', () => {
  const dialog = () => readShipped('components/SourcesDialog.xmlui');

  it('applies Card.groupMemo and Recurring.collapse in one named step', () => {
    const src = dialog();
    // The named step is where grouping and the one weekly collapse happen;
    // every count binding reads it, so the rule cannot drift per binding.
    expect(src).toMatch(/window\.Recurring\.collapse\(\s*window\.Card\.groupMemo\(currentEvents/);
  });

  it("keeps the dialog's own inputs while sharing the rule", () => {
    const src = dialog();
    expect(src).toContain('filterHiddenSources(groupedEvents, localHidden)');
    expect(src).toContain('getVisibleSourceCounts(groupedEvents, localHidden)');
    // Its own city filter and uncommitted hidden preview stay; no date window.
    expect(src).toMatch(/e\.city === \$props\.city/);
    expect(src).toContain('localHidden');
  });

  it('hides every card a source fully carries when that source is hidden', () => {
    const rows = [
      // A grouped card carried by two sources: still visible while either is.
      viewRow({
        id: 1,
        duplicate_group: 'g1',
        merged_ids: [1, 2],
        source_names: ['Alpha', 'Beta'],
      }),
      viewRow({ id: 3, source_names: ['Alpha'] }),
      viewRow({ id: 4, source_names: ['Beta'] }),
    ];
    const cards = window.Card.group(rows);
    expect(cards).toHaveLength(3);

    const withoutAlpha = window.filterHiddenSources(cards, ['Alpha']);
    expect(withoutAlpha.map((c) => c.id)).toEqual([1, 4]);

    // Every card is fully carried by the hidden sources once both are hidden.
    expect(window.filterHiddenSources(cards, ['Alpha', 'Beta'])).toHaveLength(0);
  });

  it('collapses a long-running series before hidden-source filtering counts it', () => {
    const base = new Date();
    // Six occurrences over five weeks; the first week carries two.
    const rows = [0, 3, 7, 14, 21, 28].map((offset, i) =>
      occurrence(base, offset, { id: 100 + i, source_names: ['Alpha'] })
    );
    const cards = window.Card.group(rows);
    expect(cards).toHaveLength(6);

    const collapsed = window.Recurring.collapse(cards);
    // A DST-straddling run can merge two weekly buckets, so the survivor count
    // is bounded, not pinned; the mark and the drop are.
    expect(collapsed.length).toBeLessThan(cards.length);
    expect(collapsed.every((e) => e.isRecurring)).toBe(true);

    const counts = window.getVisibleSourceCounts(collapsed, []);
    const alpha = counts.find((r) => r.source === 'Alpha');
    expect(alpha.total).toBeGreaterThan(0);
    expect(alpha.total).toBeLessThan(6);
  });
});

describe('dashboard tiles group and collapse before category/search filtering', () => {
  const tile = () => readShipped('components/FeedTile.xmlui');

  it('runs its rows through filterTileEvents and documents the fetch truncation caveat', () => {
    const src = tile();
    expect(src).toContain('window.filterTileEvents(tileEvents.value');
    // The tile fetch is `limit=200`; a series straddling the cutoff can still
    // tally differently than the list's full fetch. The caveat must be stated
    // where the query lives.
    expect(src).toMatch(/limit=200/);
    expect(src).toMatch(/truncation/i);
  });

  it('collapses a long-running series in the tile pipeline', () => {
    const base = new Date();
    const series = [0, 3, 7, 14, 21, 28].map((offset, i) =>
      occurrence(base, offset, { id: 100 + i })
    );
    const single = viewRow({
      id: 900,
      title: 'One-off',
      start_time: new Date(base.getTime() + 2 * DAY).toISOString(),
    });
    const out = window.filterTileEvents(series.concat([single]), '', '');
    // Without collapse the series alone would contribute six rows; the one-off
    // (a distinct, short series) always survives untouched.
    expect(out.length).toBeLessThan(7);
    expect(out.some((e) => e.id === 900)).toBe(true);
    expect(out.filter((e) => e.isRecurring).length).toBe(out.length - 1);
  });

  it('filters the collapsed cards, not the raw member rows', () => {
    // The card's category comes from the representative row; a filter on a
    // collapsed-away member's category must not resurrect that member.
    const rows = [
      viewRow({
        id: 1,
        duplicate_group: 'g1',
        merged_ids: [1, 2],
        source_names: ['Alpha'],
        category: 'Music',
      }),
      viewRow({
        id: 2,
        duplicate_group: 'g1',
        merged_ids: [1, 2],
        source_names: ['Beta'],
        category: 'Theater',
      }),
    ];
    expect(window.filterTileEvents(rows, 'Music', '')).toHaveLength(1);
    expect(window.filterTileEvents(rows, 'Theater', '')).toHaveLength(0);

    // A search term on a same-week occurrence the collapse drops does not
    // survive: the pipeline collapses first, then searches.
    const base = new Date();
    const withTerm = [0, 1, 7, 14, 21, 28].map((offset, i) =>
      occurrence(base, offset, { id: 100 + i, description: offset === 1 ? 'HiddenTerm' : '' })
    );
    expect(window.filterTileEvents(withTerm, '', 'hiddenterm')).toHaveLength(0);
  });

  it('folds a member row onto its card before searching', () => {
    const rows = [
      viewRow({
        id: 1,
        duplicate_group: 'g1',
        merged_ids: [1, 2],
        source_names: ['Alpha'],
        description: '',
      }),
      viewRow({
        id: 2,
        duplicate_group: 'g1',
        merged_ids: [1, 2],
        source_names: ['Beta'],
        description: 'Bluegrass night',
      }),
    ];
    const out = window.filterTileEvents(rows, '', 'bluegrass');
    expect(out).toHaveLength(1);
    expect(out[0].duplicate_group).toBe('g1');
  });
});

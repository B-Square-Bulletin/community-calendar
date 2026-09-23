// tests/js/validate-dedupe-groups.test.js — client consumer seam for #153:
// the calendar, dashboard, and picks collapse the route's *stored* duplicate
// decision instead of recomputing a title+time fallback.
//
// WHY: the confidence route already decided Merge/Group/Separate at build time
// and the view carries one row per group with `merged_ids`. A client that
// re-groups by title would re-collapse two Separate rows the route deliberately
// kept apart (identical title at incompatible locations), and a client that
// ignores `merged_ids` would let a pick light up only the representative. These
// tests pin the public client behavior: group by `(start_time, duplicate_group)`,
// treat NULL as separate, seed `mergedIds` from the view, and hash the border
// color from the group id.
'use strict';
import { describe, it, expect, beforeEach } from 'vitest';
import { loadShipped, readShipped } from './load-shipped.js';

loadShipped({ url: 'https://example.com/?city=bloomington' });

// A view-shaped row: one row per group, with the route's stored decision.
function row(overrides = {}) {
  return Object.assign(
    {
      id: 1,
      title: 'Concert',
      start_time: '2026-09-19T18:00:00+00:00',
      source: 'WFIU',
      source_urls: { WFIU: 'https://wfiu.example/1' },
      duplicate_group: null,
      merged_ids: [1],
      city: 'bloomington',
    },
    overrides
  );
}

beforeEach(() => {
  window.clearDedupeCache();
});

describe('dedupeEvents groups by the stored duplicate_group', () => {
  it('collapses one stored group to one card with every member id and source', () => {
    const out = window.dedupeEvents([
      row({
        id: 1,
        source: 'WFIU',
        source_urls: { WFIU: 'https://wfiu.example/1' },
        duplicate_group: 'cr1:g',
        merged_ids: [1, 2],
      }),
      row({
        id: 2,
        title: 'Concert (Live)',
        source: 'Visit Bloomington',
        source_urls: { 'Visit Bloomington': 'https://vb.example/2' },
        duplicate_group: 'cr1:g',
        merged_ids: [1, 2],
      }),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].mergedIds.slice().sort()).toEqual([1, 2]);
    expect(out[0].source.split(', ').sort()).toEqual(['Visit Bloomington', 'WFIU']);
    expect(out[0].source_urls).toEqual({
      WFIU: 'https://wfiu.example/1',
      'Visit Bloomington': 'https://vb.example/2',
    });
  });

  it('keeps NULL groups separate even when title and instant match', () => {
    const out = window.dedupeEvents([
      row({ id: 1, duplicate_group: null, merged_ids: [1] }),
      row({ id: 2, duplicate_group: null, merged_ids: [2] }),
    ]);
    expect(out).toHaveLength(2);
  });

  it('keeps two different stored groups separate even when title and instant match', () => {
    const out = window.dedupeEvents([
      row({ id: 1, duplicate_group: 'cr1:a', merged_ids: [1] }),
      row({ id: 2, duplicate_group: 'cr1:b', merged_ids: [2] }),
    ]);
    expect(out).toHaveLength(2);
  });

  it('seeds mergedIds from the view merged_ids column so one pick lights every member', () => {
    const out = window.dedupeEvents([
      row({ id: 7, duplicate_group: 'cr1:g', merged_ids: [7, 8, 9] }),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].mergedIds).toEqual([7, 8, 9]);
    expect(window.isEventPicked(out[0].mergedIds, [{ event_id: 8 }])).toBe(true);
  });

  it('does not collapse groups that only share a title at different instants', () => {
    const out = window.dedupeEvents([
      row({
        id: 1,
        start_time: '2026-09-19T18:00:00+00:00',
        duplicate_group: 'cr1:a',
        merged_ids: [1],
      }),
      row({
        id: 2,
        start_time: '2026-09-19T20:00:00+00:00',
        duplicate_group: 'cr1:b',
        merged_ids: [2],
      }),
    ]);
    expect(out).toHaveLength(2);
  });
});

describe('clusterBorder derives its colour from the group id', () => {
  it('renders no border for a NULL group', () => {
    expect(window.clusterBorder(null, false)).toEqual('none');
  });
  it('renders no border while a filter term is active', () => {
    expect(window.clusterBorder('cr1:abc', true)).toEqual('none');
  });
  it('pins a group id to a stable colour', () => {
    expect(window.clusterBorder('cr1:abc', false)).toEqual('3px solid #d4a04a');
  });
  it('is deterministic for the same group id', () => {
    expect(window.clusterBorder('cr1:g', false)).toEqual(window.clusterBorder('cr1:g', false));
  });
});

describe('eventMergedIds reads the stored membership', () => {
  it('prefers camelCase mergedIds when present', () => {
    expect(window.eventMergedIds({ id: 1, mergedIds: [1, 2] })).toEqual([1, 2]);
  });
  it('reads the view merged_ids column', () => {
    expect(window.eventMergedIds({ id: 1, merged_ids: [1, 2, 3] })).toEqual([1, 2, 3]);
  });
  it('falls back to the single id', () => {
    expect(window.eventMergedIds({ id: 5 })).toEqual([5]);
  });
});

describe('dedupePicks shows one representation per stored group', () => {
  it('collapses two picks on members of one group to one', () => {
    const picks = [
      { id: 10, event_id: 1, events: row({ id: 1, duplicate_group: 'cr1:g', merged_ids: [1, 2] }) },
      { id: 11, event_id: 2, events: row({ id: 2, duplicate_group: 'cr1:g', merged_ids: [1, 2] }) },
    ];
    expect(window.dedupePicks(picks)).toHaveLength(1);
  });
  it('keeps picks on NULL groups separate', () => {
    const picks = [
      { id: 10, event_id: 1, events: row({ id: 1, duplicate_group: null, merged_ids: [1] }) },
      { id: 11, event_id: 2, events: row({ id: 2, duplicate_group: null, merged_ids: [2] }) },
    ];
    expect(window.dedupePicks(picks)).toHaveLength(2);
  });
  it('prefers the group representative when members are both picked', () => {
    const picks = [
      {
        id: 10,
        event_id: 1,
        events: row({
          id: 1,
          source_uid: 'member',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        }),
      },
      {
        id: 11,
        event_id: 2,
        events: row({
          id: 2,
          source_uid: 'rep',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        }),
      },
    ];
    expect(window.dedupePicks(picks).map((p) => p.id)).toEqual([11]);
  });
});

describe('consumers read the stored decision from the view', () => {
  it('the calendar projection selects duplicate_group and merged_ids from the view', () => {
    const shell = readShipped('shell.js');
    expect(shell).toContain('/rest/v1/deduplicated_events');
    expect(shell).toMatch(/select=[^']*\bduplicate_group\b/);
    expect(shell).toMatch(/select=[^']*\bmerged_ids\b/);
  });

  it('the dashboard tile queries the same view, not the raw events table', () => {
    const tile = readShipped('components/FeedTile.xmlui');
    expect(tile).toContain('/rest/v1/deduplicated_events');
    expect(tile).not.toContain('/rest/v1/events?');
    expect(tile).toMatch(/select=[^&']*\bduplicate_group\b/);
    expect(tile).toMatch(/select=[^&']*\bmerged_ids\b/);
  });

  it('the event card borders on duplicate_group and picks through the membership helper', () => {
    const card = readShipped('components/EventCard.xmlui');
    expect(card).toContain('window.clusterBorder($props.event.duplicate_group');
    expect(card).toContain('window.eventMergedIds($props.event)');
  });

  it('the saved-picks list collapses stored groups', () => {
    const main = readShipped('Main.xmlui');
    expect(main).toContain('window.dedupePicks(picks.value');
  });
});

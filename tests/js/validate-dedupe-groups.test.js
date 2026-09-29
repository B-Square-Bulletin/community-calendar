// tests/js/validate-dedupe-groups.test.js — client consumer seam for #153/#173:
// the calendar, dashboard, and picks collapse the route's *stored* duplicate
// decision instead of recomputing a title+time fallback.
//
// WHY: the confidence route already decided Merge/Group/Separate at build time
// and the view carries one row per group with `merged_ids`. That stored
// decision is now read through the one Card module (#171/#173), so a client
// that re-groups by title would re-collapse two Separate rows the route
// deliberately kept apart (identical title at incompatible locations), and a
// client that ignores `merged_ids` would let a pick light up only the
// representative. These tests pin the public client behavior: group by
// `(start_time, duplicate_group)`, treat NULL as separate, read `merged_ids`
// through `Card.members`, and hash the border color from the group id.
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

describe('Card.group groups by the stored duplicate_group', () => {
  it('collapses one stored group to one card with every member id and source', () => {
    const out = window.Card.group([
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
    expect(window.Card.members(out[0]).slice().sort()).toEqual([1, 2]);
    expect(out[0].source.split(', ').sort()).toEqual(['Visit Bloomington', 'WFIU']);
    expect(out[0].source_urls).toEqual({
      WFIU: 'https://wfiu.example/1',
      'Visit Bloomington': 'https://vb.example/2',
    });
  });

  it('keeps NULL groups separate even when title and instant match', () => {
    const out = window.Card.group([
      row({ id: 1, duplicate_group: null, merged_ids: [1] }),
      row({ id: 2, duplicate_group: null, merged_ids: [2] }),
    ]);
    expect(out).toHaveLength(2);
  });

  it('keeps two different stored groups separate even when title and instant match', () => {
    const out = window.Card.group([
      row({ id: 1, duplicate_group: 'cr1:a', merged_ids: [1] }),
      row({ id: 2, duplicate_group: 'cr1:b', merged_ids: [2] }),
    ]);
    expect(out).toHaveLength(2);
  });

  it('seeds merged_ids from the view column so one pick lights every member', () => {
    const out = window.Card.group([
      row({ id: 7, duplicate_group: 'cr1:g', merged_ids: [7, 8, 9] }),
    ]);
    expect(out).toHaveLength(1);
    expect(window.Card.members(out[0])).toEqual([7, 8, 9]);
    expect(window.Card.isPicked(out[0], [{ event_id: 8 }])).toBe(true);
  });

  it('does not collapse groups that only share a title at different instants', () => {
    const out = window.Card.group([
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

// The route keeps source names structured: a human source name may contain a
// comma, so the client must fold the view's ordered `source_names` array rather
// than re-splitting the compatibility `source` string. Splitting "Taste, Inc."
// would fabricate two sources and let the client disagree with the view's
// representative ordering (spec amendment L402).
describe('Card.group folds structured source_names', () => {
  it('does not split a comma-containing source name', () => {
    const out = window.Card.group([
      row({
        id: 1,
        source: 'Taste, Inc.',
        source_names: ['Taste, Inc.'],
        source_urls: { 'Taste, Inc.': 'https://taste.example/1' },
      }),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('Taste, Inc.');
    expect(out[0].source_names).toEqual(['Taste, Inc.']);
  });

  it("preserves the view's representative order instead of re-sorting", () => {
    const out = window.Card.group([
      row({
        id: 1,
        source: 'Zeta, Alpha',
        source_names: ['Zeta', 'Alpha'],
        source_urls: { Zeta: 'https://z.example', Alpha: 'https://a.example' },
      }),
    ]);
    expect(out[0].source_names).toEqual(['Zeta', 'Alpha']);
    expect(out[0].source).toBe('Zeta, Alpha');
  });

  it('keeps a comma-containing name intact through the card path', () => {
    const out = window.Card.group([
      row({
        id: 1,
        source: 'Taste, Inc.',
        source_names: ['Taste, Inc.'],
        source_urls: { 'Taste, Inc.': 'https://taste.example/1' },
      }),
    ]);
    const links = window.formatSourceLinks(
      out[0].source,
      out[0].source_urls,
      [],
      out[0].source_names
    );
    expect(links).toBe('Source: [Taste, Inc.](https://taste.example/1)');
  });

  it('falls back to splitting source for raw rows without source_names', () => {
    const out = window.Card.group([row({ id: 1, source: 'WFIU, Visit Bloomington' })]);
    expect(out[0].source.split(', ').sort()).toEqual(['Visit Bloomington', 'WFIU']);
  });
});

describe('Card.group attaches recurring enrichments by explicit event linkage', () => {
  it('carries the enrichment rrule onto its linked route row', () => {
    const out = window.Card.group([
      row({
        id: 7,
        start_time: '2026-09-20T01:00:00+00:00',
        duplicate_group: 'cr2:group',
        merged_ids: [7, 8],
      }),
      {
        id: 'enrichment-12-2026-09-19T18:00:00.000Z',
        _enrichment_id: 12,
        _enrichment_event_id: 8,
        title: 'Concert',
        start_time: '2026-09-19T18:00:00.000Z',
        source: 'Picks: curator',
        rrule: 'FREQ=WEEKLY;BYDAY=SA',
        _enrichment_is_original_occurrence: true,
      },
    ]);

    expect(out).toHaveLength(1);
    expect(out[0].rrule).toBe('FREQ=WEEKLY;BYDAY=SA');
    expect(out[0].source).toContain('Picks: curator');
    expect(window.Card.members(out[0])).toEqual([7, 8]);
  });

  it('does not attach an enrichment to a different occurrence time', () => {
    const out = window.Card.group([
      row({
        id: 7,
        start_time: '2026-09-20T01:00:00+00:00',
        duplicate_group: 'cr2:group',
        merged_ids: [7, 8],
      }),
      {
        id: 'enrichment-12-2026-09-26T18:00:00.000Z',
        _enrichment_id: 12,
        _enrichment_event_id: 8,
        title: 'Concert',
        start_time: '2026-09-26T18:00:00.000Z',
        source: 'Picks: curator',
        rrule: 'FREQ=WEEKLY;BYDAY=SA',
        _enrichment_is_original_occurrence: false,
      },
    ]);

    expect(out).toHaveLength(2);
  });

  it('invalidates the combine cache when the enrichment event link changes', () => {
    const routeRow = row({ id: 17, duplicate_group: 'cr2:linked', merged_ids: [17, 18] });
    const linkedOccurrence = {
      id: 'enrichment-22-2026-09-19T18:00:00.000Z',
      _enrichment_id: 22,
      _enrichment_is_original_occurrence: true,
      title: 'Concert',
      start_time: '2026-09-19T18:00:00.000Z',
      source: 'Picks: curator',
      rrule: 'FREQ=WEEKLY;BYDAY=SA',
    };

    // combineEvents folds the linked enrichment through Card, so a changed
    // link must miss the combine cache and re-fold.
    const attached = window.combineEvents(
      [routeRow],
      [{ ...linkedOccurrence, _enrichment_event_id: 18 }]
    );
    const detached = window.combineEvents(
      [routeRow],
      [{ ...linkedOccurrence, _enrichment_event_id: 19 }]
    );

    expect(attached).toHaveLength(1);
    expect(detached).toHaveLength(2);
  });

  it('links enrichments in the main calendar processing path', () => {
    const routeRow = row({ id: 37, duplicate_group: 'cr2:production', merged_ids: [37, 38] });
    const originalOccurrence = {
      id: 'enrichment-42-2026-09-19T18:00:00.000Z',
      _enrichment_id: 42,
      _enrichment_event_id: 38,
      _enrichment_is_original_occurrence: true,
      title: 'Concert',
      start_time: '2026-09-19T18:00:00.000Z',
      source: 'Picks: curator',
      rrule: 'FREQ=WEEKLY;BYDAY=SA',
    };

    const out = window.processEvents(window.combineEvents([routeRow], [originalOccurrence]), []);

    expect(out).toHaveLength(1);
    expect(out[0].rrule).toBe('FREQ=WEEKLY;BYDAY=SA');
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

describe('Card.members reads the stored membership', () => {
  it('reads the view merged_ids column', () => {
    expect(window.Card.members({ id: 1, merged_ids: [1, 2, 3] })).toEqual([1, 2, 3]);
  });
  it('falls back to the single id', () => {
    expect(window.Card.members({ id: 5 })).toEqual([5]);
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
  it('falls back to the smallest member event id when the representative is not picked', () => {
    // A pick stored before the route, or a representative that changed between
    // builds, can leave the route's representative out of the picked set. The
    // collapse stays deterministic: one entry per group, smallest member event
    // id wins. The normal UI always picks the card's representative id. The
    // my-picks ICS feed ranks on the same key (ADR 0013).
    const picks = [
      {
        id: 11,
        event_id: 2,
        events: row({
          id: 2,
          source_uid: 'member-b',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        }),
      },
      {
        id: 10,
        event_id: 1,
        events: row({
          id: 1,
          source_uid: 'member-a',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        }),
      },
    ];
    expect(window.dedupePicks(picks).map((p) => p.id)).toEqual([10]);
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
    expect(tile).toMatch(/select=[^&']*\btranscript\b/);
  });

  it('the calendar and dashboard projections select structured source_names', () => {
    // A consumer that only reads the comma-joined `source` must split it to get
    // names back; selecting `source_names` lets the card render the view's
    // ordered names without recovering them from ambiguous text (L402).
    expect(readShipped('shell.js')).toMatch(/select=[^']*\bsource_names\b/);
    expect(readShipped('components/FeedTile.xmlui')).toMatch(/select=[^&']*\bsource_names\b/);
  });

  it('the event card and pick editor pass structured source_names to the renderer', () => {
    expect(readShipped('components/EventCard.xmlui')).toContain('$props.event.source_names');
    expect(readShipped('components/PickEditor.xmlui')).toContain('$props.event.source_names');
  });

  it('no longer carries the retired cluster_id field (#155)', () => {
    // cluster_id was the legacy per-timeslot similarity index. The route's
    // duplicate_group is the only grouping authority, so a projection that
    // still selected cluster_id would keep a competing field alive.
    const shell = readShipped('shell.js');
    expect(shell).not.toMatch(/\bcluster_id\b/);
  });

  it('the event card borders on duplicate_group and picks through the Card module', () => {
    const card = readShipped('components/EventCard.xmlui');
    expect(card).toContain('window.clusterBorder($props.event.duplicate_group');
    expect(card).toContain('window.Card.isPicked($props.event');
    // A future occurrence is its own virtual card: no membership, so the
    // bookmark is hidden rather than rendered as a save that fails the FK.
    expect(card).toContain('!$props.event.isVirtual');
  });

  it('the saved-picks list collapses stored groups through Card.uniquePicks', () => {
    // The picks list is the last consumer of the legacy dedupePicks seam. Card
    // is now the one membership authority, so the list must read Card.uniquePicks
    // and the legacy seam must not linger as a second list authority.
    const main = readShipped('Main.xmlui');
    expect(main).toContain('window.Card.uniquePicks(picks.value');
    expect(main).not.toContain('window.dedupePicks');
  });

  it('the saved-picks list hands each item over as a whole pick object', () => {
    // uniquePicks ranks on fields the pick's fetched event carries (the route
    // representative and the member event id), so the list must pass the whole
    // pick to PickItem — a bare id would lose the ranking inputs.
    expect(readShipped('Main.xmlui')).toContain('<PickItem pick="{$item}"');
  });

  it('removing a saved Group runs the one write plan for its members', () => {
    const item = readShipped('components/PickItem.xmlui');
    const globals = readShipped('Globals.xs');
    expect(item).toContain('removePick($props.pick)');
    expect(globals).toContain('window.Card.cardForPick(pick, processedCards)');
    expect(globals).toContain("'/rest/v1/events?select=id&duplicate_group=eq.'");
  });
});

// Spec amendment L402, extended beyond the card path: every client site that
// derives source names must prefer the view's structured `source_names`.
// Splitting "Taste, Inc." fabricates two sources, so hide/count/sort would
// disagree with the view for comma-containing human source names.
describe('structured source_names outside the card path', () => {
  it('filterHiddenSources matches a comma-containing name exactly', () => {
    const events = [row({ id: 1, source: 'Taste, Inc.', source_names: ['Taste, Inc.'] })];
    expect(window.filterHiddenSources(events, ['Taste, Inc.'])).toHaveLength(0);
    expect(window.filterHiddenSources(events, ['Taste'])).toHaveLength(1);
  });

  it('getSourceCounts counts a comma-containing name once', () => {
    const counts = window.getSourceCounts([
      row({ id: 1, source: 'Taste, Inc.', source_names: ['Taste, Inc.'] }),
    ]);
    expect(counts).toEqual([{ source: 'Taste, Inc.', count: 1 }]);
  });

  it('sortSourcesForDisplay leaves a structured row in view order', () => {
    const out = window.sortSourcesForDisplay([
      row({ id: 1, source: 'Taste, Inc.', source_names: ['Taste, Inc.'] }),
    ]);
    expect(out[0].source).toBe('Taste, Inc.');
  });

  it('filterExternalExclusions excludes a comma-containing name exactly', () => {
    const events = [row({ id: 1, source: 'Taste, Inc.', source_names: ['Taste, Inc.'] })];
    const previous = window.externalExclusions;
    try {
      window.externalExclusions = { excludedSources: ['Taste, Inc.'] };
      expect(window.filterExternalExclusions(events)).toHaveLength(0);
      window.externalExclusions = { excludedSources: ['Taste'] };
      expect(window.filterExternalExclusions(events)).toHaveLength(1);
    } finally {
      window.externalExclusions = previous;
    }
  });
});

// #173: the calendar's grouping reads the one Card module. The processed card
// therefore carries the view's `merged_ids` (never the retired camelCase alias)
// and any member pick lights it; a future occurrence stays its own virtual,
// unpickable card.
describe('the calendar composition reads Card membership', () => {
  function linkedOccurrence(overrides = {}) {
    return Object.assign(
      {
        id: 'enrichment-42-2026-09-19T18:00:00.000Z',
        _enrichment_id: 42,
        _enrichment_event_id: 38,
        _enrichment_is_original_occurrence: true,
        title: 'Concert',
        start_time: '2026-09-19T18:00:00.000Z',
        source: 'Picks: curator',
        rrule: 'FREQ=WEEKLY',
      },
      overrides
    );
  }

  it('groups the enrichment path through Card, emitting merged_ids only', () => {
    const routeRow = row({ id: 37, duplicate_group: 'cr2:g', merged_ids: [37, 38] });
    const out = window.processEvents(window.combineEvents([routeRow], [linkedOccurrence()]), []);

    expect(out).toHaveLength(1);
    expect(out[0].merged_ids).toEqual([37, 38]);
    expect(out[0].mergedIds).toBeUndefined();
    expect(window.Card.isPicked(out[0], [{ event_id: 38 }])).toBe(true);
  });

  it('marks a future occurrence as its own unpickable virtual card', () => {
    const routeRow = row({ id: 37, duplicate_group: 'cr2:g', merged_ids: [37, 38] });
    const future = linkedOccurrence({
      id: 'enrichment-42-2026-09-26T18:00:00.000Z',
      start_time: '2026-09-26T18:00:00.000Z',
      _enrichment_is_original_occurrence: false,
    });
    const out = window.processEvents(window.combineEvents([routeRow], [future]), []);

    const virtual = out.find((e) => e.isVirtual);
    expect(virtual).toBeTruthy();
    expect(window.Card.isPicked(virtual, [{ event_id: 38 }])).toBe(false);
  });
});

// tests/js/card-membership.test.js — the Card module's public seam (#169/#171).
//
// WHY: Card is the one client authority on "what is on one card": grouping the
// view's stored route decision, the member event ids behind a card, whether a
// card is picked, the representative pick per stored group, and the delete plan
// a pick/unpick executes. The load-bearing job is enrichment folding — a virtual
// occurrence whose original-occurrence flag is set attaches to its linked
// group's card, every other virtual occurrence stays its own marked card, and
// synthetic enrichment ids never enter membership. Tests assert through the
// public interface with hand-computed literals so they can disagree with the
// implementation, never against internals.
'use strict';
import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadShipped } from './load-shipped.js';
// The my-picks ICS feed's collapse is the client's twin (ADR-0013): both rank
// a stored group's representative the same way, so the feed and the picks list
// cannot choose different members. Vitest/esbuild strips the TS types.
import { dedupePickedEvents } from '../../supabase/functions/my-picks/dedupe.ts';

loadShipped({ url: 'https://example.com/?city=bloomington' });

const __dirname = dirname(fileURLToPath(import.meta.url));

// A view-shaped row: one row per stored group, carrying the route's decision.
function row(overrides = {}) {
  return Object.assign(
    {
      id: 1,
      title: 'Concert',
      start_time: '2026-09-19T18:00:00+00:00',
      source: 'WFIU',
      source_names: ['WFIU'],
      source_urls: { WFIU: 'https://wfiu.example/1' },
      duplicate_group: null,
      merged_ids: [1],
      city: 'bloomington',
    },
    overrides
  );
}

function virtual(overrides = {}) {
  return Object.assign(
    {
      id: 'enrichment-77-2026-09-19T18:00:00.000Z',
      title: 'Concert',
      start_time: '2026-09-19T18:00:00.000Z',
      end_time: null,
      location: null,
      description: null,
      url: null,
      source: 'Picks: Curator',
      rrule: 'FREQ=WEEKLY;BYDAY=SA',
      _enrichment_id: 77,
      _enrichment_event_id: 8,
      _enrichment_is_original_occurrence: true,
    },
    overrides
  );
}

beforeEach(() => {
  window.Card.resetMemo();
});

describe('Card.group groups by the stored route decision', () => {
  it('collapses one stored group to one card with every member id and source', () => {
    const cards = window.Card.group([
      row({
        id: 1,
        source: 'WFIU, Visit Bloomington',
        source_names: ['WFIU', 'Visit Bloomington'],
        source_urls: {
          WFIU: 'https://wfiu.example/1',
          'Visit Bloomington': 'https://vb.example/2',
        },
        duplicate_group: 'cr1:g',
        merged_ids: [1, 2],
      }),
    ]);
    expect(cards).toHaveLength(1);
    expect(window.Card.members(cards[0])).toEqual([1, 2]);
    expect(cards[0].source_names).toEqual(['WFIU', 'Visit Bloomington']);
    expect(cards[0].source_urls).toEqual({
      WFIU: 'https://wfiu.example/1',
      'Visit Bloomington': 'https://vb.example/2',
    });
  });

  it('merges two rows of one stored group into one card with a unioned membership', () => {
    const cards = window.Card.group([
      row({ id: 1, source: 'WFIU', duplicate_group: 'cr1:g', merged_ids: [1, 2] }),
      row({
        id: 2,
        source: 'Visit Bloomington',
        source_names: ['Visit Bloomington'],
        source_urls: { 'Visit Bloomington': 'https://vb.example/2' },
        duplicate_group: 'cr1:g',
        merged_ids: [1, 2],
      }),
    ]);
    expect(cards).toHaveLength(1);
    expect(window.Card.members(cards[0]).sort()).toEqual([1, 2]);
    expect(cards[0].source.split(', ').sort()).toEqual(['Visit Bloomington', 'WFIU']);
    // Every member's link survives the fold, not just the first row's.
    expect(cards[0].source_urls).toEqual({
      WFIU: 'https://wfiu.example/1',
      'Visit Bloomington': 'https://vb.example/2',
    });
  });

  it('keeps a NULL duplicate_group as one row is one card', () => {
    const cards = window.Card.group([
      row({ id: 1, duplicate_group: null, merged_ids: [1] }),
      row({ id: 2, duplicate_group: null, merged_ids: [2] }),
    ]);
    expect(cards).toHaveLength(2);
    expect(cards.map((c) => c.id).sort()).toEqual([1, 2]);
  });

  it('keeps two different stored groups separate even at the same instant', () => {
    const cards = window.Card.group([
      row({ id: 1, duplicate_group: 'cr1:a', merged_ids: [1] }),
      row({ id: 2, duplicate_group: 'cr1:b', merged_ids: [2] }),
    ]);
    expect(cards).toHaveLength(2);
  });

  it('does not mutate its input rows (pure)', () => {
    const events = [
      row({ id: 1, url: null, location: null, duplicate_group: 'cr1:g', merged_ids: [1, 2] }),
      row({ id: 2, url: 'https://vb.example/2', location: 'Hall', duplicate_group: 'cr1:g' }),
    ];
    const snapshot = JSON.stringify(events);
    window.Card.group(events);
    expect(JSON.stringify(events)).toEqual(snapshot);
  });

  it('does not collapse groups that only share a title at different instants', () => {
    const cards = window.Card.group([
      row({ id: 1, start_time: '2026-09-19T18:00:00+00:00', duplicate_group: 'cr1:a' }),
      row({ id: 2, start_time: '2026-09-19T20:00:00+00:00', duplicate_group: 'cr1:b' }),
    ]);
    expect(cards).toHaveLength(2);
  });
});

describe('Card.group enrichment folding', () => {
  it("folds an enrichment's original occurrence onto its linked group's card", () => {
    const cards = window.Card.group([
      row({
        id: 7,
        start_time: '2026-09-19T18:00:00+00:00',
        duplicate_group: 'cr2:group',
        merged_ids: [7, 8],
      }),
      virtual({ _enrichment_event_id: 8, _enrichment_is_original_occurrence: true }),
    ]);
    expect(cards).toHaveLength(1);
    expect(cards[0].rrule).toBe('FREQ=WEEKLY;BYDAY=SA');
    expect(window.Card.members(cards[0])).toEqual([7, 8]);
    expect(cards[0].isVirtual).not.toBe(true);
  });

  it('keeps a future occurrence as its own virtual card with no membership', () => {
    const cards = window.Card.group([
      row({
        id: 7,
        start_time: '2026-09-19T18:00:00+00:00',
        duplicate_group: 'cr2:group',
        merged_ids: [7, 8],
      }),
      virtual({ _enrichment_event_id: 8, _enrichment_is_original_occurrence: false }),
    ]);
    expect(cards).toHaveLength(2);
    const future = cards.find((c) => c.isVirtual);
    expect(future).toBeTruthy();
    expect(window.Card.members(future)).toEqual([]);
  });

  it('never lets a synthetic enrichment id enter membership', () => {
    const cards = window.Card.group([virtual({ _enrichment_is_original_occurrence: false })]);
    expect(cards).toHaveLength(1);
    expect(window.Card.members(cards[0])).toEqual([]);
  });

  it('keeps an original occurrence virtual when its linked event is not in the fetch', () => {
    // Folding keys on the stored event linkage, not on a time match; a link
    // that resolves to no stored row (out of the mirror/window) cannot fold.
    const cards = window.Card.group([
      row({
        id: 7,
        start_time: '2026-09-20T01:00:00+00:00',
        duplicate_group: 'cr2:group',
        merged_ids: [7, 8],
      }),
      virtual({ _enrichment_event_id: 999, _enrichment_is_original_occurrence: true }),
    ]);
    expect(cards).toHaveLength(2);
    const orphan = cards.find((c) => c.isVirtual);
    expect(window.Card.members(orphan)).toEqual([]);
  });
});

describe('Card.group ordering contract', () => {
  it('orders grouped rows before Separate rows at equal instants, by group id', () => {
    const T = '2026-09-19T18:00:00+00:00';
    const cards = window.Card.group([
      row({ id: 10, title: 'Separate', start_time: T, duplicate_group: null, merged_ids: [10] }),
      row({
        id: 20,
        title: 'Group Two',
        start_time: T,
        duplicate_group: 'cr2:z',
        merged_ids: [20],
      }),
      row({
        id: 30,
        title: 'Group One',
        start_time: T,
        duplicate_group: 'cr1:a',
        merged_ids: [30],
      }),
    ]);
    expect(cards.map((c) => c.duplicate_group)).toEqual(['cr1:a', 'cr2:z', null]);
    expect(cards.map((c) => c.id)).toEqual([30, 20, 10]);
  });
});

describe('Card.group legacy raw-row fallback (inert on view rows)', () => {
  it('splits the comma-joined source when source_names is absent', () => {
    const cards = window.Card.group([
      row({ id: 1, source: 'WFIU, Visit Bloomington', source_names: undefined }),
    ]);
    expect(cards[0].source_names.sort()).toEqual(['Visit Bloomington', 'WFIU']);
  });

  it('sorts aggregators last and promotes a location-matching source', () => {
    const prev = window._sourcePriority;
    window._sourcePriority = { aggregators: [] };
    try {
      const cards = window.Card.group([
        row({
          id: 1,
          source: 'Alpha, Zeta',
          source_names: undefined,
          location: 'Zeta Hall',
        }),
      ]);
      // Alphabetical first, then the source named in the location moves to front.
      expect(cards[0].source_names).toEqual(['Zeta', 'Alpha']);
    } finally {
      window._sourcePriority = prev;
    }
  });
});

describe('Card.members', () => {
  it('reads the view merged_ids', () => {
    expect(window.Card.members({ id: 1, merged_ids: [1, 2, 3] })).toEqual([1, 2, 3]);
  });
  it('falls back to the single row id (a NULL group)', () => {
    expect(window.Card.members({ id: 5 })).toEqual([5]);
  });
  it('returns nothing for a virtual card', () => {
    expect(window.Card.members({ id: 'enrichment-1-x', isVirtual: true, merged_ids: [1] })).toEqual(
      []
    );
  });
});

describe('Card.isPicked', () => {
  it('is true when any member is picked', () => {
    expect(window.Card.isPicked({ id: 1, merged_ids: [1, 2] }, [{ event_id: 2 }])).toBe(true);
  });
  it('is false when no member is picked', () => {
    expect(window.Card.isPicked({ id: 1, merged_ids: [1, 2] }, [{ event_id: 9 }])).toBe(false);
  });
  it('is false for a virtual card even if an id matches', () => {
    expect(
      window.Card.isPicked({ id: 1, merged_ids: [1], isVirtual: true }, [{ event_id: 1 }])
    ).toBe(false);
  });
  it('is false with no picks', () => {
    expect(window.Card.isPicked({ id: 1, merged_ids: [1] }, null)).toBe(false);
  });
});

describe('Card.uniquePicks', () => {
  const pick = (id, eventId, ev) => ({ id, event_id: eventId, events: ev });

  it('keeps one entry per stored group, returning the whole pick object', () => {
    const picks = [
      pick(10, 1, row({ id: 1, duplicate_group: 'cr1:g', merged_ids: [1, 2] })),
      pick(11, 2, row({ id: 2, duplicate_group: 'cr1:g', merged_ids: [1, 2] })),
    ];
    const out = window.Card.uniquePicks(picks);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe(10);
    expect(out[0].events).toBe(picks[0].events);
  });

  it('keeps picks on NULL groups separate', () => {
    const picks = [
      pick(10, 1, row({ id: 1, duplicate_group: null, merged_ids: [1] })),
      pick(11, 2, row({ id: 2, duplicate_group: null, merged_ids: [2] })),
    ];
    expect(window.Card.uniquePicks(picks)).toHaveLength(2);
  });

  it('prefers the group representative when members are both picked', () => {
    const picks = [
      pick(
        10,
        1,
        row({
          id: 1,
          source_uid: 'member',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        })
      ),
      pick(
        11,
        2,
        row({
          id: 2,
          source_uid: 'rep',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        })
      ),
    ];
    expect(window.Card.uniquePicks(picks).map((p) => p.id)).toEqual([11]);
  });

  it('falls back to the smallest member event id when the representative is not picked', () => {
    const picks = [
      pick(
        11,
        2,
        row({
          id: 2,
          source_uid: 'member-b',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        })
      ),
      pick(
        10,
        1,
        row({
          id: 1,
          source_uid: 'member-a',
          duplicate_group_representative: 'rep',
          duplicate_group: 'cr1:g',
          merged_ids: [1, 2],
        })
      ),
    ];
    expect(window.Card.uniquePicks(picks).map((p) => p.id)).toEqual([10]);
  });

  it('ranks exactly as the my-picks ICS feed does (ADR-0013)', () => {
    // The same three situations the feed's dedupePickedEvents covers: group
    // members collapse, the representative wins, and the smallest event id
    // breaks a tie when no representative is picked. Both implementations run
    // over the same events and must select the same member.
    const events = [
      {
        id: 5,
        source_uid: 'member-b',
        duplicate_group_representative: 'rep',
        duplicate_group: 'cr1:g',
      },
      {
        id: 3,
        source_uid: 'member-a',
        duplicate_group_representative: 'rep',
        duplicate_group: 'cr1:g',
      },
      { id: 8, source_uid: 'rep', duplicate_group_representative: 'rep', duplicate_group: 'cr2:h' },
      {
        id: 9,
        source_uid: 'other',
        duplicate_group_representative: 'rep',
        duplicate_group: 'cr2:h',
      },
    ];
    const picks = events.map((ev) => pick(100 + ev.id, ev.id, ev));
    const clientIds = window.Card.uniquePicks(picks)
      .map((p) => p.event_id)
      .sort((a, b) => a - b);
    const feedIds = dedupePickedEvents(events)
      .map((e) => e.id)
      .sort((a, b) => a - b);
    expect(clientIds).toEqual(feedIds);
    expect(clientIds).toEqual([3, 8]);
  });
});

describe('Card.pickPlan and Card.cardForPick', () => {
  it('the delete plan carries the single member-id list', () => {
    expect(window.Card.pickPlan({ id: 1, merged_ids: [1, 2, 3] })).toEqual({
      memberEventIds: [1, 2, 3],
    });
  });

  it('resolves a pick to its card by member id', () => {
    const cards = window.Card.group([
      row({ id: 1, duplicate_group: 'cr1:g', merged_ids: [1, 2] }),
      row({ id: 9, duplicate_group: null, merged_ids: [9] }),
    ]);
    const hit = window.Card.cardForPick({ id: 10, event_id: 2 }, cards);
    expect(hit && hit.id).toBe(1);
  });

  it('returns null when the pick is outside the mirror', () => {
    const cards = window.Card.group([row({ id: 1, merged_ids: [1] })]);
    expect(window.Card.cardForPick({ id: 10, event_id: 404 }, cards)).toBe(null);
  });
});

describe('Card.normalizePick', () => {
  it('normalizes a joined pick row (events object)', () => {
    expect(
      window.Card.normalizePick({
        id: 10,
        event_id: 2,
        events: {
          id: 2,
          duplicate_group: 'cr1:g',
          source_uid: 'rep',
          duplicate_group_representative: 'rep',
        },
      })
    ).toEqual({
      id: 10,
      eventId: 2,
      duplicateGroup: 'cr1:g',
      sourceUid: 'rep',
      isRepresentative: true,
    });
  });

  it('normalizes a flat pick row', () => {
    expect(
      window.Card.normalizePick({
        id: 11,
        event_id: 3,
        duplicate_group: null,
        source_uid: 'member',
        duplicate_group_representative: 'rep',
      })
    ).toEqual({
      id: 11,
      eventId: 3,
      duplicateGroup: null,
      sourceUid: 'member',
      isRepresentative: false,
    });
  });
});

describe('Card.groupMemo', () => {
  it('reuses the result within one emission and recomputes on a new emission', () => {
    window.__ccEmitSig = 'emit-1';
    const events = [row({ id: 1 }), row({ id: 2, start_time: '2026-09-19T20:00:00+00:00' })];
    const first = window.Card.groupMemo(events);
    const second = window.Card.groupMemo(events);
    expect(second).toBe(first);
    window.__ccEmitSig = 'emit-2';
    const third = window.Card.groupMemo(events);
    expect(third).not.toBe(first);
  });

  it('accepts a caller-supplied signature (the strong eventsSignature)', () => {
    window.__ccEmitSig = 'emit-1';
    const a = [row({ id: 1 })];
    const b = [row({ id: 2 })];
    const sigA = window.eventsSignature(a);
    const sigB = window.eventsSignature(b);
    const first = window.Card.groupMemo(a, sigA);
    // A different payload with the same length/endpoint ids would fool the
    // composite default; the strong signature catches it.
    const second = window.Card.groupMemo(b, sigB);
    expect(second).not.toBe(first);
    expect(second[0].id).toBe(2);
  });

  it('resetMemo clears the cached result (vm harness hook)', () => {
    window.__ccEmitSig = 'emit-1';
    const events = [row({ id: 1 })];
    const first = window.Card.groupMemo(events);
    window.Card.resetMemo();
    const second = window.Card.groupMemo(events);
    expect(second).not.toBe(first);
    expect(second).toEqual(first);
  });
});

describe('enrichment fixture pins the single-pass fold -> group output', () => {
  it('folds the original occurrence, keeps the future occurrences virtual, and leaves the series uncollapsed', () => {
    const fixture = JSON.parse(
      readFileSync(
        join(__dirname, '..', 'fixtures', 'enrichment_fold', 'bloomington_enrichment_fold.json'),
        'utf8'
      )
    );
    const cards = window.Card.group(fixture.events.concat(fixture.virtual));

    // Fold -> group, before the weekly collapse (Recurring's job, #169 item 03):
    // 1 Group card + 2 future virtual cards + Farmers Market + 5 exhibition rows.
    expect(cards).toHaveLength(9);

    const sing = cards.filter((c) => c.title === 'Weekly Community Sing' && !c.isVirtual);
    expect(sing).toHaveLength(1);
    expect(window.Card.members(sing[0])).toEqual([1001, 1002]);
    expect(sing[0].rrule).toBe('FREQ=WEEKLY;COUNT=3');

    const future = cards
      .filter((c) => c.isVirtual)
      .map((c) => ({ start: c.start_time, members: window.Card.members(c) }))
      .sort((a, b) => a.start.localeCompare(b.start));
    expect(future).toEqual([
      { start: '2026-10-07T23:00:00.000Z', members: [] },
      { start: '2026-10-14T23:00:00.000Z', members: [] },
    ]);

    expect(window.Card.members(cards.find((c) => c.title === 'Farmers Market'))).toEqual([1003]);

    const exhibition = cards.filter((c) => c.title === 'Autumn Exhibition');
    expect(exhibition).toHaveLength(5);
    expect(exhibition.map((c) => window.Card.members(c)[0]).sort((a, b) => a - b)).toEqual([
      1100, 1101, 1102, 1103, 1104,
    ]);
  });
});

describe('plain-path equivalence over the production view payload', () => {
  it('is near pass-through: one card per stored view row with its membership intact', () => {
    const gz = readFileSync(
      join(__dirname, '..', 'fixtures', 'deduplicated_events_bloomington.json.gz')
    );
    const rows = JSON.parse(gunzipSync(gz).toString('utf8'));
    expect(rows.length).toBeGreaterThan(1000);

    const cards = window.Card.group(rows);
    // The view already returns one row per stored group, so the plain path
    // adds and drops nothing: card count equals row count.
    expect(cards).toHaveLength(rows.length);

    const byId = new Map(cards.map((c) => [c.id, c]));
    expect(byId.size).toBe(rows.length);
    for (const r of rows) {
      const card = byId.get(r.id);
      expect(card).toBeTruthy();
      expect(window.Card.members(card)).toEqual(r.merged_ids);
    }
  });
});

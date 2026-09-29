// tests/js/pick-write-authority.test.js — the one write authority for pick and
// unpick (#169/#175).
//
// WHY: togglePick and removePick used to run four different removal paths with
// different keys (a pick-by-id loop, a chunked enrichment delete, and a group
// picks join keyed on pick ids). They are now one authority whose delete plan
// comes from Card, so every removal issues the same two user-scoped deletes:
// the user's picks by member event id, and the curator's enrichments by member
// event id. Unpicking therefore also clears the curator's enrichment for the
// group (intended, story 6). The code-behind is not loaded by the vm harness
// (it needs the XMLUI Actions engine), so these checks pin the call sites the
// glue must keep. The plan itself is covered at the Card seam
// (tests/js/card-membership.test.js).
'use strict';
import { describe, it, expect } from 'vitest';
import { readShipped } from './load-shipped.js';

const globals = () => readShipped('Globals.xs');
const occurrences = (haystack, needle) => haystack.split(needle).length - 1;

describe('one write authority issues the two scoped deletes', () => {
  it("deletes the user's picks by member id and user id", () => {
    expect(globals()).toContain("'/rest/v1/picks?event_id=in.('");
    expect(globals()).toContain('&user_id=eq.');
  });

  it("deletes the curator's enrichments by member id and curator id", () => {
    expect(globals()).toContain("'/rest/v1/event_enrichments?event_id=in.('");
    expect(globals()).toContain('&curator_id=eq.');
  });

  it('is the only place either delete is issued (both write paths route through it)', () => {
    const src = globals();
    expect(occurrences(src, "'/rest/v1/picks?event_id=in.('")).toBe(1);
    expect(occurrences(src, "'/rest/v1/event_enrichments?event_id=in.('")).toBe(1);
  });

  it('reads the member list from Card.pickPlan', () => {
    expect(globals()).toContain('window.Card.pickPlan(card).memberEventIds');
  });
});

describe('removePick resolves membership from the mirror, then the DB', () => {
  it('prefers the mirrored card list', () => {
    const src = globals();
    expect(src).toContain('window.Card.cardForPick(pick, processedCards)');
    // A virtual mirror card has no membership; the guard sends it to the DB
    // fallback instead of a silent no-op removal.
    expect(src).toContain('window.Card.members(card).length');
  });

  it("falls back to one group GET, then the pick's own event id", () => {
    const src = globals();
    expect(src).toContain("'/rest/v1/events?select=id&duplicate_group=eq.'");
    expect(src).toContain('encodeURIComponent(normalized.duplicateGroup)');
    // A group with no rows (orphan) and a NULL-group pick both fall back to the
    // pick's own event id, so the pick is still cleared.
    expect(src).toContain('members.length ? members : [normalized.eventId]');
    expect(src).toContain('normalized.eventId != null ? [normalized.eventId] : []');
  });
});

describe('the pick path keeps its outside-the-module pieces', () => {
  it('keeps the existing-pick probe in togglePick', () => {
    expect(globals()).toContain("'/rest/v1/picks?select=id&user_id=eq.'");
  });

  it('posts the one-click pick with the event id unchanged', () => {
    expect(globals()).toContain('event_id: event.id');
  });
});

describe('a picks change never re-ingests the event list', () => {
  it('refetches picks and enrichments only, not events', () => {
    const main = readShipped('Main.xmlui');
    expect(main).toContain('listenTo="{picksCounter}"');
    expect(main).toContain('onDidChange="picks.refetch(); enrichments.refetch()"');
    expect(main).not.toMatch(/listenTo="\{picksCounter\}"\s+onDidChange="[^"]*refetchEvents/);
  });

  it('mirrors the window-scoped card list for removePick', () => {
    const main = readShipped('Main.xmlui');
    expect(main).toContain('global.processedCards="{null}"');
    expect(main).toContain('processedCards = dateFilteredEvents');
  });
});

describe('the picks list hands removePick the whole pick', () => {
  it('passes the pick object so the DB fallback has event_id + duplicate_group', () => {
    expect(readShipped('components/PickItem.xmlui')).toContain('removePick($props.pick)');
  });
});

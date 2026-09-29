// tests/js/legacy-membership-retired.test.js — the contract step of the Card
// refactor (#169/#177).
//
// WHY: Card became the one client membership authority across items 02-07.
// With every consumer migrated, the legacy membership surface had to be removed
// outright — `dedupeEvents`, `eventMergedIds`, and `dedupePicks` — and the dead
// `window.togglePick` in shell.js (a second toggle keyed on a bare event id,
// referenced by no markup) retired, so no second membership surface can linger
// and silently disagree with Card. The live pick/unpick glue still belongs to
// Globals.xs + EventCard; the vm harness cannot load code-behind, so its routing
// is pinned by the call-site checks in pick-write-authority.test.js.
'use strict';
import { describe, it, expect } from 'vitest';
import { loadShipped, readShipped } from './load-shipped.js';

loadShipped();

describe('the legacy membership surface is retired', () => {
  it('no longer exposes dedupeEvents, eventMergedIds, or dedupePicks on window', () => {
    // helpers.js attaches these to window; a second membership reader would
    // let the calendar and the picks list disagree with Card.
    expect(window.dedupeEvents).toBeUndefined();
    expect(window.eventMergedIds).toBeUndefined();
    expect(window.dedupePicks).toBeUndefined();
  });

  it('no longer exposes the legacy isEventPicked pick-state reader', () => {
    // isEventPicked keyed on an id list and was exercised only by its own
    // test.html block; Card.isPicked is the one pick-state reader now, so a
    // surviving window.isEventPicked would be a second place to disagree.
    expect(window.isEventPicked).toBeUndefined();
  });

  it('removed the dead shell toggle while keeping the live Globals.xs one', () => {
    // shell.js's window.togglePick was referenced by no markup; EventCard still
    // wires its bookmark to the Globals.xs code-behind togglePick.
    expect(readShipped('shell.js')).not.toContain('window.togglePick');
    expect(readShipped('Globals.xs')).toContain('function togglePick(event)');
    expect(readShipped('components/EventCard.xmlui')).toContain('togglePick($props.event)');
  });
});

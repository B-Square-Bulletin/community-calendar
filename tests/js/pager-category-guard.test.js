'use strict';
// tests/js/pager-category-guard.test.js — regression pin for issue #146.
//
// The Earlier/Later guards must read the SAME list the rendered list reads:
// date window (filtered upstream) + search + category. When the guard reads
// the un-categorized list it claims a next page the filtered slice does not
// have, and "Later" pages a small category into an empty list. These tests
// drive the shipped helpers.js predicate through the vm loader with the exact
// shape from the issue: 245 rows total, 4 in the selected category.
//
// The end-to-end proof that the binding is wired to this predicate lives in
// tests/js/pager-category-guard.browser.spec.js.
import { describe, it, expect } from 'vitest';
import { loadShipped } from './load-shipped.js';

// loadShipped runs the shipped sources once via vm.runInThisContext; a second
// call re-declares their top-level consts, so the window shim is loaded once
// and shared by every test below.
loadShipped();
const win = global.window;

const SMALL = 'Comedy / Improv';
const LARGE = 'Music / Concerts';
const PAGE_SIZE = 50;

function event(id, category) {
  return {
    id,
    title: 'Event ' + id,
    start_time: '2026-09-20T12:00:00Z',
    category,
    source: 'Test Source',
  };
}

function dataset() {
  const rows = [];
  for (let i = 0; i < 4; i++) rows.push(event('small-' + i, SMALL));
  for (let i = 0; i < 241; i++) rows.push(event('large-' + i, LARGE));
  return rows;
}

describe('pager guards read the filtered list (#146)', () => {
  const events = dataset();

  it('hides Later when the selected category fits one page', () => {
    expect(win.moreHasMore(events, '', 0, PAGE_SIZE, SMALL)).toBe(false);
  });

  it('shows Later when the selected category spans multiple pages', () => {
    expect(win.moreHasMore(events, '', 0, PAGE_SIZE, LARGE)).toBe(true);
  });

  it('shows Later on a mid page of the filtered list', () => {
    expect(win.moreHasMore(events, '', 49, PAGE_SIZE, LARGE)).toBe(true);
  });

  it('hides Later once the filtered list is exhausted', () => {
    // 241 rows, step 49: last page starts at 196 (196 + 50 >= 241).
    expect(win.moreHasMore(events, '', 196, PAGE_SIZE, LARGE)).toBe(false);
  });

  it('hides Earlier on the first page even when un-filtered rows precede it', () => {
    expect(win.moreHasPrev(events, '', 0, SMALL)).toBe(false);
  });

  it('shows Earlier on a later page of the filtered list', () => {
    expect(win.moreHasPrev(events, '', 49, LARGE)).toBe(true);
  });

  it('keeps Earlier available to recover from a stale page past the filtered list', () => {
    // A filtered-input shrink can leave the index past the end; Earlier must
    // stay reachable so the user is not stranded on an empty page.
    expect(win.moreHasPrev(events, '', 49, SMALL)).toBe(true);
  });
});

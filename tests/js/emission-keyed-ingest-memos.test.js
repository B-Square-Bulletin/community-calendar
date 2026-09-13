// tests/js/emission-keyed-ingest-memos.test.js — issue #86 regression guard.
//
// The issue-82 ingest memos key on ccArraySig (length + first/last id) so a
// repeat evaluation within one emission reuses the previous array BY REFERENCE
// (the property that keeps the #77 recompute spike away). That key is blind
// to the middle of the payload: a fresh emission whose rows differ only
// mid-array (same length, same endpoint ids) HITs and hands back the previous
// array, so the XMLUI binding that consumes it sees unchanged data and never
// repaints.
//
// shell.js publishes window.__ccEmitSig (the full-payload eventsSignature plus
// an emit sequence) at every emit. These tests pin the contract at the public
// window seams: a new emission invalidates the memo chain exactly once, while
// repeat calls within one emission still reuse.
'use strict';
import { describe, it, expect, beforeEach } from 'vitest';
import { loadShipped } from './load-shipped.js';

loadShipped();

// Identical length (3) and endpoint ids (1 … 3); only the middle title differs.
// This is a payload that eventsSignature distinguishes but ccArraySig cannot.
const STALE = [
  { id: 1, title: 'Alpha', start_time: '2026-01-01T10:00:00Z' },
  { id: 2, title: 'Beta OLD', start_time: '2026-01-02T10:00:00Z' },
  { id: 3, title: 'Gamma', start_time: '2026-01-03T10:00:00Z' },
];
const FRESH = [
  { id: 1, title: 'Alpha', start_time: '2026-01-01T10:00:00Z' },
  { id: 2, title: 'Beta NEW', start_time: '2026-01-02T10:00:00Z' },
  { id: 3, title: 'Gamma', start_time: '2026-01-03T10:00:00Z' },
];

let emitSeq = 0;
const nextEmit = () => 'emit-' + ++emitSeq;

beforeEach(() => {
  window.__ccEmitSig = nextEmit();
});

describe('combineEvents', () => {
  it('recomputes when an emission changes only mid-array', () => {
    const first = window.combineEvents(STALE, []);
    window.__ccEmitSig = nextEmit();
    const second = window.combineEvents(FRESH, []);
    expect(second).not.toBe(first);
    expect(second[1].title).toBe('Beta NEW');
  });

  it('reuses the combined array within a single emission', () => {
    const first = window.combineEvents(STALE, []);
    const second = window.combineEvents(STALE, []);
    expect(second).toBe(first);
  });
});

describe('collapseLongRunningEvents', () => {
  it('recomputes when an emission changes only mid-array', () => {
    const first = window.collapseLongRunningEvents(STALE);
    window.__ccEmitSig = nextEmit();
    const second = window.collapseLongRunningEvents(FRESH);
    expect(second).not.toBe(first);
    expect(second.some((e) => e.title === 'Beta NEW')).toBe(true);
  });

  it('reuses the collapsed array within a single emission', () => {
    const first = window.collapseLongRunningEvents(STALE);
    const second = window.collapseLongRunningEvents(STALE);
    expect(second).toBe(first);
  });
});

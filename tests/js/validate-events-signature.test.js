// tests/js/validate-events-signature.test.js — vitest mirror of the
// eventsSignature / shouldSkipFreshEmit groups in xmlui/test.html (upstream
// #85). Loads the shipped helpers.js so the issue-82 coalescing identity is
// covered by `make test-node`, not only the Playwright browser gate.
'use strict';
import { describe, it, expect } from 'vitest';
import { loadShipped } from './load-shipped.js';

loadShipped();

const stale = [
  { id: 1, title: 'Early', start_time: '2026-01-01T10:00:00Z' },
  { id: 2, title: 'Middle OLD', start_time: '2026-01-02T10:00:00Z' },
  { id: 3, title: 'Late', start_time: '2026-01-03T10:00:00Z' },
];
const fresh = [
  { id: 1, title: 'Early', start_time: '2026-01-01T10:00:00Z' },
  { id: 2, title: 'Middle NEW', start_time: '2026-01-02T10:00:00Z' },
  { id: 3, title: 'Late', start_time: '2026-01-03T10:00:00Z' },
];

describe('eventsSignature', () => {
  it('is exported', () => {
    expect(typeof window.eventsSignature).toBe('function');
  });
  it('distinguishes payloads that differ only between the endpoint ids', () => {
    expect(window.eventsSignature(stale)).not.toEqual(window.eventsSignature(fresh));
  });
  it('is stable for identical content across distinct references', () => {
    expect(window.eventsSignature(stale)).toEqual(
      window.eventsSignature(JSON.parse(JSON.stringify(stale)))
    );
  });
  it('catches an in-place field edit with identical ids', () => {
    const edited = JSON.parse(JSON.stringify(stale));
    edited[1].start_time = '2026-01-02T11:00:00Z';
    expect(window.eventsSignature(stale)).not.toEqual(window.eventsSignature(edited));
  });
  it('returns the 0/na sentinels for empty and non-array input', () => {
    expect(window.eventsSignature([])).toEqual('0');
    expect(window.eventsSignature(null)).toEqual('na');
    expect(window.eventsSignature(undefined)).toEqual('na');
  });
  it('treats a reordering as a change', () => {
    expect(window.eventsSignature(stale)).not.toEqual(
      window.eventsSignature([stale[1], stale[0], stale[2]])
    );
  });
});

describe('shouldSkipFreshEmit', () => {
  const emit = () => {};
  const state = (lastSig) => ({
    currentEmit: emit,
    lastEmitFn: emit,
    city: 'davis',
    lastEmitCity: 'davis',
    lastEmitSig: lastSig,
  });

  it('does not skip a fresh payload that differs only in the middle', () => {
    expect(window.shouldSkipFreshEmit(state(window.eventsSignature(stale)), fresh)).toBe(false);
  });
  it('skips a truly identical payload for the same subscriber and city', () => {
    const copy = JSON.parse(JSON.stringify(stale));
    expect(window.shouldSkipFreshEmit(state(window.eventsSignature(stale)), copy)).toBe(true);
  });
  it('does not skip when no subscriber is current', () => {
    const s = { ...state(window.eventsSignature(stale)), currentEmit: null };
    expect(window.shouldSkipFreshEmit(s, stale)).toBe(false);
  });
  it('does not skip for a different city', () => {
    const s = { ...state(window.eventsSignature(stale)), lastEmitCity: 'santarosa' };
    expect(window.shouldSkipFreshEmit(s, stale)).toBe(false);
  });
});

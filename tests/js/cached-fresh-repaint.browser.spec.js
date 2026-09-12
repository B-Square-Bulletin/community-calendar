// tests/js/cached-fresh-repaint.browser.spec.js — Playwright integration guard
// for the cached→fresh replacement path (Main.xmlui PushSource + eventsEpoch).
//
// WHY: the pure vitest/test.html groups pin eventsSignature and
// shouldSkipFreshEmit, but they cannot prove the runtime contract that a cached
// IndexedDB paint is replaced by a later fresh emission. This spec boots the
// real index.html hermetically (REST intercepted, no live data), seeds
// IndexedDB with a cached payload, holds the network fetch open until the
// cached paint is observed, then releases a fresh payload and asserts the
// rendered list replaces the cached row.
//
// SCOPE / KNOWN GAP: the passing case changes an endpoint id, which also
// changes the ingest memos' ccArraySig key (length + first/last id). This spec
// therefore does not isolate the eventsEpoch nudge — it also passes with
// eventsEpoch threaded out of the getPagedEvents bindings. A change confined
// to the middle (same length + same endpoint ids) is the case eventsSignature
// was added for, but it cannot pass yet: combineEvents and the downstream
// memoizeIngest wrappers still key on ccArraySig (the same weak key the
// retired rowsSig used), so every stage HITs and serves the stale paint even
// after cc-events-emit-fresh fires. That gap is documented in the fixme below
// and belongs upstream (see docs/adr/0010 §4); un-skip it once the ingest memos
// key on content (or the emission signature is threaded into their keys).
import { test, expect } from '@playwright/test';

const CITY = 'bloomington';

function at(offsetDays) {
  return new Date(Date.now() + offsetDays * 86400000).toISOString();
}

function event(id, title, offsetDays) {
  return { id, title, start_time: at(offsetDays), source: 'Test Source' };
}

const CACHED = [
  event(1, 'Cached Alpha', 1),
  event(2, 'Cached Beta', 2),
  event(3, 'Cached Gamma', 3),
];

// Endpoint id 3 → 4 changes ccArraySig, so the memos miss and the fresh rows
// propagate to the DOM.
const FRESH = [event(1, 'Cached Alpha', 1), event(2, 'Fresh Beta', 2), event(4, 'Fresh Gamma', 3)];

// Same length (3) and same endpoint ids (1 … 3): a mid-only change. This is
// the payload shape the upstream #85 fix targets end-to-end.
const FRESH_MID = [
  event(1, 'Cached Alpha', 1),
  event(2, 'Fresh Beta', 2),
  event(3, 'Cached Gamma', 3),
];

async function seedEventsCache(page, city, rows) {
  await page.evaluate(
    ({ city, rows }) =>
      new Promise((resolve, reject) => {
        const req = indexedDB.open('cc-events-cache', 1);
        req.onupgradeneeded = () => req.result.createObjectStore('payloads');
        req.onsuccess = () => {
          const db = req.result;
          const tx = db.transaction('payloads', 'readwrite');
          tx.objectStore('payloads').put({ at: Date.now(), rows }, 'events:' + city);
          tx.oncomplete = () => resolve();
          tx.onerror = () => reject(tx.error);
        };
        req.onerror = () => reject(req.error);
      }),
    { city, rows }
  );
}

// Boot the app with `cached` seeded, hold the events fetch open until the
// cached paint is observed (so the cached emit is never skipped by a boot-fast
// network response), and return a release function that lets `fresh` through.
async function bootCachedThenFresh(page, cached, fresh) {
  let releaseFresh;
  const freshGate = new Promise((resolve) => {
    releaseFresh = resolve;
  });
  await page.route('**/rest/v1/**', async (route) => {
    if (route.request().url().includes('/deduplicated_events')) {
      await freshGate;
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fresh),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  await page.route('**/auth/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  );

  // Seed from a same-origin page first: async init scripts are not awaited
  // before a page's own scripts, and shell.js reads IndexedDB at boot.
  await page.goto('/xmlui/test.html');
  await seedEventsCache(page, CITY, cached);
  await page.goto('/xmlui/index.html?city=' + CITY);
  await expect(page.getByText('Cached Beta', { exact: true })).toBeVisible({ timeout: 45000 });
  return releaseFresh;
}

test('cached paint is replaced by the fresh emission', async ({ page }) => {
  const releaseFresh = await bootCachedThenFresh(page, CACHED, FRESH);
  releaseFresh();
  await expect(page.getByText('Fresh Gamma', { exact: true })).toBeVisible({ timeout: 45000 });
  await expect(page.getByText('Fresh Beta', { exact: true })).toBeVisible();
  await expect(page.getByText('Cached Gamma', { exact: true })).toHaveCount(0);
});

test.fixme('mid-only fresh change repaints', async ({ page }) => {
  const releaseFresh = await bootCachedThenFresh(page, CACHED, FRESH_MID);
  releaseFresh();
  await expect(page.getByText('Fresh Beta', { exact: true })).toBeVisible({ timeout: 45000 });
});

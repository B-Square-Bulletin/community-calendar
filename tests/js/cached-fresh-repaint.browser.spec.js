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
// SCOPE: two cases guard the same repaint contract from opposite sides. The
// endpoint-changing case (id 3 -> 4) is the older guard: it flips the ingest
// memos' ccArraySig key (length + first/last id), so it also passes with the
// eventsEpoch nudge threaded out. The mid-only case (same length, same endpoint
// ids) is the one #85/#86 target: ccArraySig cannot see it, so the whole chain
// — combineEvents, the memoizeIngest wrappers, and collapseLongRunningEvents's
// inner cache — would HIT and serve the stale paint even after
// cc-events-emit-fresh fires. shell.js now publishes window.__ccEmitSig (the
// full-payload eventsSignature plus an emit sequence) at every emit and the
// memo keys carry it, so a mid-only emission invalidates the chain and repaints.
// This DOM assertion is the end-to-end proof; the emission-keyed memo contract
// itself is pinned at the node seam in emission-keyed-ingest-memos.test.js.
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
// the payload shape ccArraySig cannot see and eventsSignature was added for.
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

test('mid-only fresh change repaints', async ({ page }) => {
  const releaseFresh = await bootCachedThenFresh(page, CACHED, FRESH_MID);
  releaseFresh();
  await expect(page.getByText('Fresh Beta', { exact: true })).toBeVisible({ timeout: 45000 });
});

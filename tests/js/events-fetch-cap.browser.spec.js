// tests/js/events-fetch-cap.browser.spec.js — #247: a capped event fetch must
// say so.
//
// The prefetch in shell.js orders start_time.asc against a REST row limit, so a
// city with more events in the window than the cap gets the earliest rows only
// and its far months end the calendar early. This spec boots the real
// index.html hermetically (REST intercepted) and asserts the shipped shell logs
// a warning naming the city when the page is full, and stays quiet when it is
// not.
import { test, expect } from '@playwright/test';

const CITY = 'bloomington';
const CAP = 6000;
const CAP_WARNING =
  'Events fetch hit the 6000-row cap for bloomington; events later in the window are missing';

function event(id) {
  return {
    id,
    title: 'Cap Test ' + id,
    start_time: new Date(Date.now() + (id + 60) * 60000).toISOString(),
    source: 'Test Source',
  };
}

function capSizedRows() {
  return Array.from({ length: CAP }, (_, i) => event(i + 1));
}

async function bootAndCollectWarnings(page, rows) {
  const warnings = [];
  const requests = [];
  page.on('console', (msg) => {
    if (msg.type() === 'warning') warnings.push(msg.text());
  });
  await page.route('**/rest/v1/**', (route) => {
    const url = route.request().url();
    requests.push(url);
    if (url.includes('/deduplicated_events')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(rows),
      });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
  });
  await page.route('**/auth/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  );
  await page.goto('/xmlui/index.html?city=' + CITY);
  return { warnings, requests };
}

test('a full page warns, naming the city and the cap', async ({ page }) => {
  const { warnings, requests } = await bootAndCollectWarnings(page, capSizedRows());
  await expect
    .poll(() => warnings.filter((w) => w.includes('row cap')).length, { timeout: 45000 })
    .toBe(1);
  expect(warnings.find((w) => w.includes('row cap'))).toBe(CAP_WARNING);
  // The warning only means truncation if the request still asks for the cap
  // in start_time order, so pin the query the response is paired with.
  const eventsRequest = requests.find((u) => u.includes('/deduplicated_events'));
  expect(eventsRequest).toContain('limit=6000');
  expect(eventsRequest).toContain('order=start_time.asc');
});

test('a city under the cap is unchanged', async ({ page }) => {
  const { warnings } = await bootAndCollectWarnings(page, [event(1), event(2), event(3)]);
  await expect(page.getByText('Cap Test 1', { exact: true })).toBeVisible({ timeout: 45000 });
  expect(warnings.filter((w) => w.includes('row cap'))).toHaveLength(0);
});

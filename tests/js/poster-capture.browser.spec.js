// tests/js/poster-capture.browser.spec.js — Playwright guard for #254.
//
// WHY: poster capture was reported as "the upload returns a promise that is
// used as if it were the result", so the dialog would always fail and never
// show the spinner. The dialogs assign `const result = window.resizeAndUpload(…)`
// without `await`; XMLUI has no `await`, and compiles that declaration to
// `await runtime.complete(runtime.call(…))`, flushing pending state first
// (xmlui@0.14.27 event-async.ts / event-runtime.ts). This spec is the only
// seam that proves the runtime contract end to end: the dialog boots the real
// index.html hermetically, the capture-event request is held open, and the
// spinner, the editor fill, and the bearer token are all observed in the DOM.
// If XMLUI ever stops awaiting that call, this test fails rather than silently
// spending an API call and showing "Failed to extract event".
import { test, expect } from '@playwright/test';

const CITY = 'davis';
const TOKEN = 'test-token';
const AUTH_STORAGE_KEY = 'sb-qatykxdvbpojxnvpicyi-auth-token';
const SPINNER = 'Extracting event details...';

// One transparent pixel: enough for resizeImageFile to decode and re-encode.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64'
);

const EXTRACTED = {
  event: {
    title: 'Poster Show',
    start_time: '2026-11-05T19:30:00',
    end_time: '2026-11-05T21:00:00',
    location: 'Hall',
    description: 'Music',
    url: 'https://example.com/show',
  },
};

async function boot(page) {
  await page.route('**/rest/v1/**', (route) => {
    const url = route.request().url();
    let body = '[]';
    // shell.js reloads the page when the signed-in user has no feed token.
    if (url.includes('/feed_tokens')) body = JSON.stringify([{ token: 'existing-token' }]);
    return route.fulfill({ status: 200, contentType: 'application/json', body });
  });
  await page.route('**/auth/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  );
  await page.addInitScript(
    ([key, token]) => {
      localStorage.setItem(
        key,
        JSON.stringify({
          access_token: token,
          refresh_token: 'refresh',
          token_type: 'bearer',
          expires_in: 3600,
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: { id: 'u1', email: 'curator@example.com', user_metadata: { user_name: 'curator' } },
        })
      );
    },
    [AUTH_STORAGE_KEY, TOKEN]
  );
  await page.goto('/xmlui/index.html?city=' + CITY);
  await expect(page.locator('[aria-label="Capture Event from Poster"]')).toBeVisible({
    timeout: 45000,
  });
}

async function openPosterCapture(page) {
  await page.locator('[aria-label="Capture Event from Poster"]').click();
  await expect(page.locator('input[accept="image/*"]')).toHaveCount(1);
}

test('poster extraction fills the editor and spins while the request runs', async ({ page }) => {
  let release;
  const inFlight = new Promise((resolve) => {
    release = resolve;
  });
  await page.route('**/functions/v1/capture-event', async (route) => {
    await inFlight;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(EXTRACTED),
    });
  });

  await boot(page);
  await openPosterCapture(page);
  const requestPromise = page.waitForRequest('**/functions/v1/capture-event');
  await page
    .locator('input[accept="image/*"]')
    .setInputFiles({ name: 'poster.png', mimeType: 'image/png', buffer: PNG });

  const request = await requestPromise;
  expect(request.headers()['authorization']).toBe('Bearer ' + TOKEN);

  // The spinner lives only while the upload is pending; it is buffered state
  // flushed before the awaited call, so seeing it proves the await boundary.
  await expect(page.getByText(SPINNER)).toBeVisible();

  release();
  await expect(page.getByRole('heading', { name: 'Save Captured Event' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue(
    'Poster Show'
  );
  await expect(page.getByRole('textbox', { name: 'Date', exact: true })).toHaveValue('2026-11-05');
  await expect(page.getByText(SPINNER)).toBeHidden();
});

test('poster extraction shows the server message on failure', async ({ page }) => {
  await page.route('**/functions/v1/capture-event', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Extraction is temporarily unavailable' }),
    })
  );

  await boot(page);
  await openPosterCapture(page);
  await page
    .locator('input[accept="image/*"]')
    .setInputFiles({ name: 'poster.png', mimeType: 'image/png', buffer: PNG });

  await expect(page.getByText('Extraction is temporarily unavailable')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Save Captured Event' })).toBeHidden();
  await expect(page.getByText(SPINNER)).toBeHidden();
});

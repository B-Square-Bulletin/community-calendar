// tests/js/test-html.browser.spec.js — Playwright gate for the (shrunk)
// xmlui/test.html browser groups (Date tabs, Brand chrome, Content links).
//
// WHY: pure-logic groups moved to vitest (tests/js/validate-*.test.js);
// test.html keeps only served-file browser groups. This spec boots the
// static server (see playwright.config.js), loads test.html, waits for
// .summary, and fails on any failed test.
import { test, expect } from '@playwright/test';

test('test.html browser groups all pass', async ({ page }) => {
  await page.goto('/xmlui/test.html');
  await page.waitForSelector('.summary', { timeout: 30000 });
  const summary = await page.textContent('.summary');
  expect(summary).toBeTruthy();
  expect(summary).not.toMatch(/failed/);
});

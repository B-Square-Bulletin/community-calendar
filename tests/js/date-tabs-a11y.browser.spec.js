// tests/js/date-tabs-a11y.browser.spec.js — Playwright + axe gate for #109.
//
// WHY: the vitest suites assert the shipped markup as text. This spec is the
// only seam that proves the rendered DOM contract: aria-pressed on the date
// tabs, keyboard operability, focus discipline (Escape returns focus to the
// Custom tab, commit moves no focus), the 360px wrap, and an axe scan of the
// date-filter region. It boots the real xmlui/index.html hermetically —
// Supabase REST is intercepted with a deterministic fixture, so no live data
// or network race is involved (see docs/adr/0008).
//
// The browser cannot sign off speech quality or the live-data checklist; those
// stay human, in docs/date-tabs-a11y-checklist.md.
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TAB_STRIP = '[data-xmlui-id="dateTabStrip"]';
const HEADING = '[data-xmlui-id="dateTabHeading"]';
const CUSTOM_ROW = '[data-xmlui-id="customPickerRow"]';
const CUSTOM_TAB = '[data-xmlui-id="customDateTab"]';

const TABS = ['All dates', 'Today', 'Tonight', 'Tomorrow', 'This weekend', 'Next 7 days', 'This month', 'Custom'];

function tab(page, label) {
  return page.locator(`${TAB_STRIP} button`, { hasText: label });
}

async function boot(page) {
  await page.route('**/rest/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  await page.route('**/auth/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
  await page.goto('/xmlui/index.html?city=bloomington');
  await page.waitForSelector(TAB_STRIP, { state: 'visible', timeout: 45000 });
}

test('date-filter region has no WCAG A/AA axe violations', async ({ page }) => {
  await boot(page);
  const results = await new AxeBuilder({ page })
    .include(TAB_STRIP)
    .include(HEADING)
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  // Full-page scan is informational only: the vendored picker and unrelated
  // app regions are out of this ticket's scope, so they must not gate CI.
  const full = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  if (full.violations.length) {
    console.log('[a11y informational] full-page violations: ' +
      full.violations.map((v) => v.id).join(', '));
  }
  expect(results.violations).toEqual([]);
});

test('exactly one tab is pressed and it tracks the committed window', async ({ page }) => {
  await boot(page);
  const pressed = page.locator(`${TAB_STRIP} button[aria-pressed="true"]`);
  await expect(pressed).toHaveCount(1);
  await expect(tab(page, 'All dates')).toHaveAttribute('aria-pressed', 'true');

  await tab(page, 'Today').click();
  await expect(tab(page, 'Today')).toHaveAttribute('aria-pressed', 'true');
  await expect(tab(page, 'All dates')).toHaveAttribute('aria-pressed', 'false');
  await expect(pressed).toHaveCount(1);
});

test('Custom tab reads pressed while its flow is open, before any range commits', async ({ page }) => {
  await boot(page);
  await page.locator(CUSTOM_TAB).click();
  await expect(page.locator(CUSTOM_ROW)).toBeVisible();
  await expect(page.locator(CUSTOM_TAB)).toHaveAttribute('aria-pressed', 'true');
  await expect(tab(page, 'All dates')).toHaveAttribute('aria-pressed', 'false');
});

test('keyboard-only: Enter on a focused tab commits the window and syncs the URL', async ({ page }) => {
  await boot(page);
  const today = tab(page, 'Today');
  await today.focus();
  await page.keyboard.press('Enter');
  await expect(today).toHaveAttribute('aria-pressed', 'true');
  await expect(page).toHaveURL(/[?&]date=today(&|$)/);
});

test('committing a preset keeps focus on the pressed tab (no focus move)', async ({ page }) => {
  await boot(page);
  const tonight = tab(page, 'Tonight');
  await tonight.focus();
  await page.keyboard.press('Enter');
  await expect(tonight).toHaveAttribute('aria-pressed', 'true');
  // A commit that scrolled, re-rendered, or moved focus elsewhere would leave
  // the button unfocused; Enter commits without a mouse.
  await expect(tonight).toBeFocused();
});

test('Escape in the Custom picker returns focus to the Custom tab', async ({ page }) => {
  await boot(page);
  await page.locator(CUSTOM_TAB).click();
  await expect(page.locator('[data-xmlui-id="customRangePicker"][data-state="open"]')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator(CUSTOM_TAB)).toBeFocused();
});

test('360px: the tab strip wraps with every preset reachable and no horizontal scroll', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await boot(page);
  const overflow = await page.locator(TAB_STRIP).evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  // The strip must not push the page itself into horizontal scroll either.
  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(pageOverflow).toBeLessThanOrEqual(1);
  for (const label of TABS) {
    await expect(tab(page, label)).toBeVisible();
  }
});

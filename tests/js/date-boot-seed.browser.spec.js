// tests/js/date-boot-seed.browser.spec.js — boot deep-link seeds (#105/#107,
// re-pinned for the #286 commit seam).
//
// WHY: the boot seed now applies the same commitFor patch as a tab tap, so
// these are the three URL outcomes the seed owns and nothing else tests in a
// real browser: an honored ?date= restores its tab, a retired key falls back
// to All WITHOUT rewriting the visitor's URL, and a clamped Custom start
// rewrites to the stable dates (the one case where the URL and the committed
// window disagreed).
import { test, expect } from '@playwright/test';

test('boot: honored preset key restores the pressed tab, no URL churn', async ({ page }) => {
  await page.goto('/xmlui/index.html?city=bloomington&date=thismonth');
  const tab = page.getByRole('button', { name: 'This month' });
  await expect(tab).toHaveAttribute('aria-pressed', 'true');
  await expect(page).toHaveURL(/date=thismonth/);
});

test('boot: retired preset key falls back to All and is NOT rewritten', async ({ page }) => {
  await page.goto('/xmlui/index.html?city=bloomington&date=month');
  await expect(page.getByRole('button', { name: 'All dates' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page).toHaveURL(/date=month/);
});

test('boot: clamped Custom start rewrites the URL to stable dates', async ({ page }) => {
  await page.goto('/xmlui/index.html?city=bloomington&from=2020-01-01&to=2020-01-05');
  await expect(page.getByRole('button', { name: 'Custom' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(page).not.toHaveURL(/2020-01-01/);
  await expect(page).toHaveURL(/from=\d{4}-\d{2}-\d{2}/);
  await expect(page).toHaveURL(/to=\d{4}-\d{2}-\d{2}/);
});

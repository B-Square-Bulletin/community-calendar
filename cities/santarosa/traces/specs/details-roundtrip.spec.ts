import { test, expect } from '@playwright/test';
import { captureTrace } from './trace-capture';

test('details-roundtrip', async ({ page }) => {
  test.setTimeout(30000);

  try {
    await page.goto('./');

    const santaRosaBtn = page.getByText('Santa Rosa Now', { exact: true });
    await expect(santaRosaBtn).toBeVisible({ timeout: 15000 });
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/rest/v1/deduplicated_events')),
      santaRosaBtn.click(),
    ]);

    await expect(page.getByPlaceholder('Search events...')).toBeVisible({ timeout: 15000 });

    const detailsToggle = page.getByText('ⓘ', { exact: true }).first();
    await expect(detailsToggle).toBeVisible({ timeout: 15000 });
    await detailsToggle.click();

    const hideDetails = page.getByRole('button', { name: 'Hide details' }).first();
    await expect(hideDetails).toBeVisible({ timeout: 15000 });

    await hideDetails.click();
    await expect(page.getByRole('button', { name: 'Hide details' })).toHaveCount(0, { timeout: 15000 });
  } finally {
    await captureTrace(page);
  }
});

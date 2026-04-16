import { test, expect } from './test-helpers';
import { captureTrace } from './trace-capture';

test('manage-feeds-roundtrip', async ({ page }) => {
  test.setTimeout(30000);

  try {
    await page.goto('./');

    const santaRosaBtn = page.getByText('Santa Rosa Now', { exact: true });
    await expect(santaRosaBtn).toBeVisible({ timeout: 15000 });
    await santaRosaBtn.click();

    await expect(page.getByPlaceholder('Search events...')).toBeVisible({ timeout: 15000 });

    const manageFeedsButton = page.getByRole('button', { name: 'Manage Feeds' });
    await expect(manageFeedsButton).toBeVisible({ timeout: 15000 });

    await manageFeedsButton.click();
    await expect(page.getByText('Manage Feeds', { exact: true })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Add a feed', { exact: true })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/^Feeds \(/)).toBeVisible({ timeout: 15000 });

    const feedUrl = page.getByPlaceholder('Feed URL (https://...)');
    const feedName = page.getByPlaceholder('Source name (e.g. Brown County Events)');
    const validateButton = page.getByRole('button', { name: 'Validate Feed' });

    await feedUrl.fill('https://www.ashevillenc.gov/events/?ical=1');
    await feedName.fill('Temporary Test Feed');
    await expect(validateButton).toBeEnabled({ timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/functions/v1/validate-feed') &&
        r.request().method() === 'POST'
      ),
      validateButton.click(),
    ]);

    await expect(page.getByText(/^Preview:/)).toBeVisible({ timeout: 15000 });

    await manageFeedsButton.click();
    await expect(page.getByText(/^Preview:/)).toHaveCount(0, { timeout: 15000 });
    await expect(page.getByText('Manage Feeds', { exact: true })).toHaveCount(0, { timeout: 15000 });

    await manageFeedsButton.click();
    await expect(page.getByText('Manage Feeds', { exact: true })).toBeVisible({ timeout: 15000 });
    await expect(feedUrl).toHaveValue('', { timeout: 15000 });
    await expect(feedName).toHaveValue('', { timeout: 15000 });
  } finally {
    await captureTrace(page);
  }
});

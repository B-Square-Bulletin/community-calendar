import { test, expect } from './test-helpers';
import { captureTrace } from './trace-capture';

test('toggle-sources', async ({ page }) => {
  test.setTimeout(30000);

  try {
    await page.goto('./');

    const santaRosaBtn = page.getByText('Santa Rosa Now', { exact: true });
    await expect(santaRosaBtn).toBeVisible({ timeout: 15000 });
    await santaRosaBtn.click();

    await expect(page.getByPlaceholder('Search events...')).toBeVisible({ timeout: 15000 });

    const sourcesButton = page.getByRole('button', { name: 'Sources', exact: true });
    await expect(sourcesButton).toBeVisible({ timeout: 15000 });

    await sourcesButton.click();
    await expect(page.getByText('Sources', { exact: true })).toBeVisible({ timeout: 15000 });

    const sourceToggle = page.getByRole('checkbox', { name: 'North Bay Bohemian' });
    await expect(sourceToggle).toBeVisible({ timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/rest/v1/user_settings?on_conflict=user_id,city') &&
        r.request().method() === 'POST' &&
        (r.request().postData() || '').includes('North Bay Bohemian')
      ),
      sourceToggle.click(),
    ]);

    await expect(sourceToggle).not.toBeChecked({ timeout: 15000 });

    await sourcesButton.click();
    await expect(page.getByText('Sources', { exact: true })).toHaveCount(0, { timeout: 15000 });

    await sourcesButton.click();
    await expect(page.getByText('Sources', { exact: true })).toBeVisible({ timeout: 15000 });

    const sourceToggleReopened = page.getByRole('checkbox', { name: 'North Bay Bohemian' });
    await expect(sourceToggleReopened).not.toBeChecked({ timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/rest/v1/user_settings?on_conflict=user_id,city') &&
        r.request().method() === 'POST'
      ),
      sourceToggleReopened.click(),
    ]);

    await expect(sourceToggleReopened).toBeChecked({ timeout: 15000 });

    await sourcesButton.click();
    await expect(page.getByText('Sources', { exact: true })).toHaveCount(0, { timeout: 15000 });
  } finally {
    await captureTrace(page);
  }
});

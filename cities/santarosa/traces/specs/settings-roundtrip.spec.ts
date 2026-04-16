import { test, expect } from '@playwright/test';
import { captureTrace } from './trace-capture';

test('settings-roundtrip', async ({ page }) => {
  test.setTimeout(30000);

  try {
    await page.goto('./');

    const santaRosaBtn = page.getByText('Santa Rosa Now', { exact: true });
    await expect(santaRosaBtn).toBeVisible({ timeout: 15000 });
    await santaRosaBtn.click();

    await expect(page.getByPlaceholder('Search events...')).toBeVisible({ timeout: 15000 });

    const settingsButton = page.getByRole('button', { name: 'Display settings' });
    await expect(settingsButton).toBeVisible({ timeout: 15000 });

    await settingsButton.click();
    await expect(page.getByText('Display Settings', { exact: true })).toBeVisible({ timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/rest/v1/user_settings?on_conflict=user_id,city') &&
        r.request().method() === 'POST' &&
        (r.request().postData() || '').includes('"image_mode":"preview"')
      ),
      page.getByRole('radio', { name: 'Only in previews' }).click(),
    ]);
    await expect(page.getByRole('radio', { name: 'Only in previews' })).toHaveAttribute('aria-checked', 'true', { timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/rest/v1/user_settings?on_conflict=user_id,city') &&
        r.request().method() === 'POST' &&
        (r.request().postData() || '').includes('"one_click_pick":true')
      ),
      page.getByRole('checkbox', { name: 'One-click pick (skip editor)' }).click(),
    ]);
    await expect(page.getByRole('checkbox', { name: 'One-click pick (skip editor)' })).toBeChecked({ timeout: 15000 });

    await settingsButton.click();
    await expect(page.getByText('Display Settings', { exact: true })).toHaveCount(0, { timeout: 15000 });

    await settingsButton.click();
    await expect(page.getByText('Display Settings', { exact: true })).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('radio', { name: 'Only in previews' })).toHaveAttribute('aria-checked', 'true', { timeout: 15000 });
    await expect(page.getByRole('checkbox', { name: 'One-click pick (skip editor)' })).toBeChecked({ timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/rest/v1/user_settings?on_conflict=user_id,city') &&
        r.request().method() === 'POST' &&
        (r.request().postData() || '').includes('"image_mode":"everywhere"')
      ),
      page.getByRole('radio', { name: 'Everywhere' }).click(),
    ]);
    await expect(page.getByRole('radio', { name: 'Everywhere' })).toHaveAttribute('aria-checked', 'true', { timeout: 15000 });

    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/rest/v1/user_settings?on_conflict=user_id,city') &&
        r.request().method() === 'POST' &&
        (r.request().postData() || '').includes('"one_click_pick":false')
      ),
      page.getByRole('checkbox', { name: 'One-click pick (skip editor)' }).click(),
    ]);
    await expect(page.getByRole('checkbox', { name: 'One-click pick (skip editor)' })).not.toBeChecked({ timeout: 15000 });

    await settingsButton.click();
    await expect(page.getByText('Display Settings', { exact: true })).toHaveCount(0, { timeout: 15000 });
  } finally {
    await captureTrace(page);
  }
});

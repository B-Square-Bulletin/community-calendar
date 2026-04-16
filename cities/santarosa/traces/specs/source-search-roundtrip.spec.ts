import { test, expect } from './test-helpers';
import { captureTrace } from './trace-capture';

test('source-search-roundtrip', async ({ page }) => {
  test.setTimeout(30000);

  try {
    await Promise.all([
      page.waitForResponse((r) => r.url().includes('/rest/v1/deduplicated_events')),
      page.goto('./?city=santarosa&search=North+Bay+Bohemian'),
    ]);

    const searchBox = page.getByPlaceholder('Search events...');
    await expect(searchBox).toBeVisible({ timeout: 15000 });
    await expect(searchBox).toHaveValue('North Bay Bohemian');

    await expect(page.getByText('North Bay Bohemian', { exact: true }).first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/North Bay Bohemian/i)).not.toHaveCount(0, { timeout: 15000 });
  } finally {
    await captureTrace(page);
  }
});

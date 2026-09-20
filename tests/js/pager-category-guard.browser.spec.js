// tests/js/pager-category-guard.browser.spec.js — Playwright integration guard
// for issue #146: the Earlier/Later pager must read the SAME list the rendered
// list does (date window + search + category), not the un-categorized list.
//
// SYMPTOM (issue #146): on a category-filtered view whose category has fewer
// rows than one page, but whose un-categorized window has more than one page,
// "Later" renders anyway. Clicking it slices the *filtered* list past its end,
// so the view goes empty while both Earlier and Later stay visible (and the
// "No events" message stays hidden because matches do exist).
//
// This spec boots the real index.html hermetically (REST intercepted, no live
// data) with 245 rows total: 4 in the small category, 241 in the large one.
// With page size 50 the un-categorized list has a next page but the small
// category does not, so "Later" must not render. The large category still
// needs its "Later" so the fix cannot simply hide the pager.
import { test, expect } from '@playwright/test';

const CITY = 'bloomington';
const SMALL_CATEGORY = 'Comedy / Improv';
const LARGE_CATEGORY = 'Music / Concerts';
const SMALL_COUNT = 4;
const LARGE_COUNT = 241;

function at(offsetDays) {
  return new Date(Date.now() + offsetDays * 86400000).toISOString();
}

function event(id, title, category) {
  return {
    id,
    title,
    start_time: at(1),
    end_time: at(1),
    category,
    source: 'Test Source',
    city: CITY,
  };
}

// 4 + 241 = 245 rows: the un-categorized list spans 5 pages at size 50, while
// the small category fits entirely on page 1. This is the exact shape #146
// describes (245 all-categories vs a handful in the selected category).
function dataset() {
  const rows = [];
  for (let i = 0; i < SMALL_COUNT; i++) {
    rows.push(event('small-' + i, 'Comedy Event ' + i, SMALL_CATEGORY));
  }
  for (let i = 0; i < LARGE_COUNT; i++) {
    rows.push(event('large-' + i, 'Music Event ' + i, LARGE_CATEGORY));
  }
  return rows;
}

async function boot(page, query) {
  await page.route('**/rest/v1/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: route.request().url().includes('/deduplicated_events')
        ? JSON.stringify(dataset())
        : '[]',
    })
  );
  await page.route('**/auth/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  );
  await page.goto('/xmlui/index.html?' + query);
}

test('Later is not offered when the selected category fits one page', async ({ page }) => {
  await boot(page, 'city=' + CITY + '&category=' + encodeURIComponent(SMALL_CATEGORY));

  // The category does have matches; all four must render.
  await expect(page.getByText('Comedy Event 0', { exact: true })).toBeVisible({ timeout: 45000 });
  for (let i = 1; i < SMALL_COUNT; i++) {
    await expect(page.getByText('Comedy Event ' + i, { exact: true })).toBeVisible();
  }

  // The pager must not claim a next/previous page the filtered list lacks.
  await expect(page.getByRole('button', { name: 'Later', exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: 'Earlier', exact: true })).toBeHidden();
});

test('Later is still offered and pages forward when the category spans multiple pages', async ({
  page,
}) => {
  await boot(page, 'city=' + CITY + '&category=' + encodeURIComponent(LARGE_CATEGORY));

  await expect(page.getByText('Music Event 0', { exact: true })).toBeVisible({ timeout: 45000 });

  // 241 rows over pages of 50: there is a genuine next page.
  const later = page.getByRole('button', { name: 'Later', exact: true });
  await expect(later).toBeVisible();

  // Paging still advances within the filtered list (one-item overlap: page 1
  // starts at index 49, so it ends at index 98).
  await later.click();
  await expect(page.getByText('Music Event 98', { exact: true })).toBeVisible();
  await expect(page.getByText('Music Event 0', { exact: true })).toBeHidden();
});

test('changing the category resets to the first page of the new filter', async ({ page }) => {
  await boot(page, 'city=' + CITY + '&category=' + encodeURIComponent(LARGE_CATEGORY));
  await expect(page.getByText('Music Event 0', { exact: true })).toBeVisible({ timeout: 45000 });

  // Move to page 2 so a stale index would slice the small category past its end.
  await page.getByRole('button', { name: 'Later', exact: true }).click();
  await expect(page.getByText('Music Event 98', { exact: true })).toBeVisible();

  await page.getByLabel('Event category').click();
  // Options render the active count alongside the label.
  await page.getByRole('option', { name: SMALL_CATEGORY + ' (' + SMALL_COUNT + ')' }).click();

  // The new filter must render its own first page, not an empty slice at the
  // previous index (with no pager and no "No events" message).
  await expect(page.getByText('Comedy Event 0', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Later', exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: 'Earlier', exact: true })).toBeHidden();
});

test('clicking a category badge resets to the first page', async ({ page }) => {
  // All categories, page 2: every visible card is a Music card.
  await boot(page, 'city=' + CITY);
  await expect(page.getByText('Music Event 0', { exact: true })).toBeVisible({ timeout: 45000 });
  await page.getByRole('button', { name: 'Later', exact: true }).click();
  await expect(page.getByText('Music Event 45', { exact: true })).toBeVisible();

  // The chip on a visible card funnels through the shared setCategoryFilter
  // path (EventCard.xmlui), not the Select; it must reset to page 1.
  await page.getByText(LARGE_CATEGORY, { exact: true }).first().click();

  await expect(page.getByText('Music Event 0', { exact: true })).toBeVisible();
});

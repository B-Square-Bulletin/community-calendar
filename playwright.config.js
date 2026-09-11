import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/js',
  testMatch: '**/*.browser.spec.js',
  fullyParallel: false,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:8080',
  },
  webServer: {
    command: 'python3 -m http.server 8080',
    url: 'http://localhost:8080/xmlui/test.html',
    reuseExistingServer: true,
    timeout: 30000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'webkit',
      testMatch: '**/date-tabs-a11y.browser.spec.js',
      use: { ...devices['Desktop Safari'] },
    },
  ],
});

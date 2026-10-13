import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.GP5_QA_URL ?? 'http://127.0.0.1:4173/gp5-qa/';
export default defineConfig({
  testDir: './test',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  outputDir: 'qa/web-runtime-results',
  reporter: [['list'], ['json', { outputFile: 'qa/web-runtime-playwright.json' }]],
  use: { baseURL, viewport: { width: 1440, height: 1000 }, acceptDownloads: true,
    trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    ...['chromium', 'webkit', 'firefox'].map(browserName => ({
      name: browserName, testMatch: 'browser.spec.js',
      use: { browserName, ...(browserName === 'chromium' ? { channel: 'chromium' } : {}) },
    })),
    { name: 'iphone-webkit', testMatch: 'mobile.spec.js', use: { ...devices['iPhone 13'], browserName: 'webkit' } },
    { name: 'android-chromium', testMatch: 'mobile.spec.js', use: { ...devices['Pixel 7'], browserName: 'chromium', channel: 'chromium' } },
    { name: 'ipad-webkit', testMatch: 'mobile.spec.js', use: { ...devices['iPad (gen 7)'], browserName: 'webkit' } },
  ],
  webServer: process.env.GP5_QA_URL ? undefined : {
    command: 'npm run build && npm run preview -- --base=/gp5-qa/ --host 127.0.0.1 --port 4173 --strictPort',
    url: baseURL,
    timeout: 120_000,
    reuseExistingServer: false,
  },
});

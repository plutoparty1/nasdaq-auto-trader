import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests', testMatch: '*.spec.js', timeout: 30000, expect: { timeout: 5000 }, workers: 1,
  reporter: [['list'], ['json', { outputFile: 'qa/browser-results.json' }]],
  use: { channel: 'chrome', baseURL: 'http://127.0.0.1:4173', viewport: { width: 240, height: 282 }, headless: true, screenshot: 'only-on-failure' },
  webServer: { command: 'npm start', url: 'http://127.0.0.1:4173', reuseExistingServer: true, timeout: 10000 },
});

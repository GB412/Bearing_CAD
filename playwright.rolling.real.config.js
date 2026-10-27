import {defineConfig} from '@playwright/test';

// Real, same-origin Python/OCCT service; unlike ordinary browser tests no
// API or STL route is mocked. Built dist/ is required before starting.
export default defineConfig({
  testDir: './tests-browser-real',
  timeout: 240_000,
  expect: {timeout: 120_000},
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8090',
    browserName: 'chromium',
    headless: true,
  },
  webServer: {
    command: 'python -m bearing_cad.api --port 8090 --static dist --artifacts build/real-browser-e2e-artifacts',
    url: 'http://127.0.0.1:8090/api/v2/cad/status',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

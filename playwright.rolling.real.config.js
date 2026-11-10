import {defineConfig} from '@playwright/test';

const port = Number(process.env.ROBAS_BROWSER_PORT || 8090);
const url = 'http://127.0.0.1:' + port;
const profiles = process.env.ROBAS_BROWSER_PROFILES;
const artifacts = process.env.ROBAS_BROWSER_ARTIFACTS || 'build/real-browser-e2e-artifacts';
const resources = process.env.ROBAS_WINDOWS_RESOURCES || 'C:/RollBearing';
const bridge = process.env.ROBAS_BROWSER_CADIMPORT;
const args = ['--port', port, '--static', 'dist', '--artifacts', artifacts];
if (profiles) args.push('--robas-resources', resources, '--robas-analysis-profiles', profiles);
if (bridge) args.push('--cadimport-bridge', bridge);

// Real, same-origin Python/OCCT service; unlike ordinary browser tests no
// API or STL route is mocked. Built dist/ is required before starting.
export default defineConfig({
  testDir: './tests-browser-real',
  timeout: 240_000,
  expect: {timeout: 120_000},
  workers: 1,
  use: {
    baseURL: url,
    browserName: 'chromium',
    // The GitHub Ubuntu runner ships Chrome; avoid re-downloading Chromium.
    // Local developers keep using the Playwright-managed Chromium.
    ...((process.env.PLAYWRIGHT_CHROMIUM_CHANNEL || process.env.CI) ?
      {channel: process.env.PLAYWRIGHT_CHROMIUM_CHANNEL || 'chrome'} : {}),
    headless: true,
  },
  webServer: {
    command: 'python -m bearing_cad.api ' + args.map(arg => '"' + String(arg) + '"').join(' '),
    url: url + '/api/v2/cad/status',
    reuseExistingServer: !process.env.CI && !profiles,
    timeout: 120_000,
  },
});

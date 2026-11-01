import {test, expect} from '@playwright/test';

const drawingSvg = [
  '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
  '<rect width="1200" height="800" fill="#151e27"/>',
  '<g fill="none" stroke="#9ec4d5" stroke-width="3">',
  '<circle cx="600" cy="400" r="230"/>',
  '<circle cx="600" cy="400" r="150"/>',
  '<path d="M370 400H830M600 170V630"/>',
  '</g><text x="600" y="90" fill="#d7e5eb" text-anchor="middle" font-size="28">RoBAS drawing preview</text></svg>',
].join('');

test('2D drawing generation opens the large preview workspace and supports sheet navigation', async ({page}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));

  const sheets = [
    ['assembly', 'assembly.dxf', 'assembly.svg'],
    ['outer_ring', 'outer_ring.dxf', 'outer_ring.svg'],
    ['inner_ring', 'inner_ring.dxf', 'inner_ring.svg'],
    ['cage', 'cage.dxf', 'cage.svg'],
  ];
  const jobId = 'c'.repeat(32);
  const manifestUrl = '/api/v2/cad/drawings/jobs/' + jobId + '/manifest.json';
  const fileUrls = {};
  for (const [, dxf, svg] of sheets) {
    fileUrls[dxf] = '/api/v2/cad/drawings/jobs/' + jobId + '/files/' + dxf;
    fileUrls[svg] = '/api/v2/cad/drawings/jobs/' + jobId + '/files/' + svg;
  }

  await page.route('**/api/v2/cad/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v2/cad/status') {
      return route.fulfill({json: {
        available: true,
        supported_bearings: ['rolling.deep_groove_ball'],
      }});
    }
    if (path === '/api/v2/cad/drawings/status') {
      return route.fulfill({json: {
        available: true,
        supported_bearings: ['rolling.deep_groove_ball'],
        failures: [],
      }});
    }
    if (path === '/api/v2/cad/drawings' && request.method() === 'POST') {
      const body = request.postDataJSON();
      expect(body.drawing.model).toBe('6208');
      expect(body.design.schema_version).toBe('bearing-cad.request.v1');
      return route.fulfill({status: 201, json: {
        manifest_url: manifestUrl,
        request_hash: 'd'.repeat(64),
      }});
    }
    if (path === manifestUrl) {
      return route.fulfill({json: {
        manifest: {
          request_hash: 'd'.repeat(64),
          sheets: sheets.map(([view, file, preview_file]) => ({view, file, preview_file})),
        },
        file_urls: fileUrls,
      }});
    }
    if (path.endsWith('.svg')) {
      return route.fulfill({status: 200, contentType: 'image/svg+xml', body: drawingSvg});
    }
    return route.fulfill({status: 404, json: {error: {message: 'not found'}}});
  });

  await page.goto('/rolling.html');
  await expect(page.locator('#generate2d')).toBeEnabled();
  await page.locator('#generate2d').click();

  await expect(page.locator('#drawingWorkspace')).toBeVisible();
  await expect(page.locator('#workspace2dTab')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#drawingPreviewImage')).toBeVisible();
  await expect(page.locator('#drawingSheetTabs [role="tab"]')).toHaveCount(4);
  await expect(page.locator('#drawingSheetTitle')).toHaveText('总装图');
  await expect(page.locator('#drawingDownloadCurrent')).toHaveAttribute('download', 'assembly.dxf');

  await page.locator('#drawingSheetTabs [data-sheet-key="outer_ring"]').click();
  await expect(page.locator('#drawingSheetTitle')).toHaveText('外圈图');
  await expect(page.locator('#drawingDownloadCurrent')).toHaveAttribute('download', 'outer_ring.dxf');

  await page.locator('#drawingZoomIn').click();
  await expect(page.locator('#drawingZoomLabel')).toHaveText('120%');
  await page.locator('#drawingFit').click();
  await expect(page.locator('#drawingZoomLabel')).toHaveText('100%');

  await page.locator('#workspace3dTab').click();
  await expect(page.locator('#modelWorkspace')).toBeVisible();
  await expect(page.locator('#workspace3dTab')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#viewport canvas')).toBeVisible();

  await page.locator('#workspace2dTab').click();
  await page.locator('#drawingAccuracy').selectOption('P6');
  await expect(page.locator('#drawingPreviewEmpty')).toBeVisible();
  await expect(page.locator('#drawingDownloadCurrent')).toBeHidden();
  await expect(page.locator('#drawingTabCount')).toHaveText('等待生成');

  expect(errors).toEqual([]);
});

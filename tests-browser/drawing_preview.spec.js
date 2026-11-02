import {expect, test} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';

let appUrl;
let fixtureServer;
test.beforeAll(async () => {
  // Chromium download navigation bypasses Playwright route.fulfill(). Serve
  // downloads over real HTTP and proxy the built app, keeping one origin.
  fixtureServer = createServer(async (request, response) => {
    try {
      const name = request.url.match(/^\/mock\/(assembly|outer_ring|inner_ring|cage)\.dxf$/)?.[1];
      if (name) {
        const body = process.env.BEARING_DRAWING_FIXTURES
          ? readFileSync(join(process.env.BEARING_DRAWING_FIXTURES, name + '.dxf'))
          : Buffer.from('download fixture');
        response.writeHead(200, {'Content-Type': 'application/dxf',
          'Content-Disposition': `attachment; filename="${name}.dxf"`});
        response.end(body);
        return;
      }
      const upstream = await fetch('http://127.0.0.1:4173' + request.url);
      response.writeHead(upstream.status, {'Content-Type': upstream.headers.get('content-type') || 'text/plain'});
      response.end(Buffer.from(await upstream.arrayBuffer()));
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise(resolve => fixtureServer.listen(0, '127.0.0.1', resolve));
  appUrl = 'http://127.0.0.1:' + fixtureServer.address().port;
});
test.afterAll(async () => {
  fixtureServer.closeAllConnections();
  await new Promise(resolve => fixtureServer.close(resolve));
});

const views = ['assembly', 'outer_ring', 'inner_ring', 'cage'];
const requestHash = 'f'.repeat(64);
const manifest = {
  request_hash: requestHash,
  sheets: views.map(view => ({
    view,
    file: view + '.dxf',
    preview_file: view + '.svg',
  })),
};
const fileUrls = Object.fromEntries(views.flatMap(view => [
  [view + '.dxf', '/mock/' + view + '.dxf'],
  [view + '.svg', '/mock/' + view + '.svg'],
]));

async function checkPreview(page, viewport, fixtureDir) {
  await page.setViewportSize(viewport);
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route('**/api/v2/cad/drawings/status', route => route.fulfill({
    json: {available: true, supported_bearings: ['rolling.deep_groove_ball']},
  }));
  await page.route('**/api/v2/cad/drawings', route => route.fulfill({
    status: 201,
    json: {manifest_url: '/mock/manifest', request_hash: requestHash},
  }));
  await page.route('**/mock/manifest', route => route.fulfill({json: {manifest, file_urls: fileUrls}}));
  await page.route('**/mock/*.svg', route => {
    const view = new URL(route.request().url()).pathname.split('/').pop().replace('.svg', '');
    if (fixtureDir) return route.fulfill({
      contentType: 'image/svg+xml', body: readFileSync(join(fixtureDir, view + '.svg')),
    });
    const width = view === 'inner_ring' ? 240 : 480;
    const height = view === 'inner_ring' ? 480 : 240;
    return route.fulfill({
      contentType: 'image/svg+xml',
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}mm" height="${height}mm" viewBox="0 0 ${width} ${height}"><rect x="4" y="4" width="${width - 8}" height="${height - 8}" fill="none" stroke="black"/></svg>`,
    });
  });
  await page.goto(appUrl + '/rolling.html');
  await expect(page).toHaveTitle(/滚动轴承/);
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
  await expect(page.locator('#generate2d')).toBeEnabled();
  await page.locator('#generate2d').click();
  await expect(page.locator('#drawingSheetTabs [role="tab"]')).toHaveCount(4);

  const stage = page.locator('#drawingPreviewStage');
  const image = page.locator('#drawingPreviewImage');
  for (const view of views) {
    await page.locator(`[data-sheet-key="${view}"]`).click();
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate(node => node.complete && node.naturalWidth > 0)).toBe(true);
    await expect(page.locator('#drawingZoomLabel')).toHaveText('100%');
    const geometry = await page.evaluate(() => {
      const stageRect = document.querySelector('#drawingPreviewStage').getBoundingClientRect();
      const imageRect = document.querySelector('#drawingPreviewImage').getBoundingClientRect();
      return {stageRect, imageRect};
    });
    expect(Math.abs((geometry.imageRect.left + geometry.imageRect.right) / 2 -
      (geometry.stageRect.left + geometry.stageRect.right) / 2)).toBeLessThan(1);
    expect(geometry.imageRect.left).toBeGreaterThanOrEqual(geometry.stageRect.left - 1);
    expect(geometry.imageRect.right).toBeLessThanOrEqual(geometry.stageRect.right + 1);
    expect(geometry.imageRect.top).toBeGreaterThanOrEqual(geometry.stageRect.top - 1);
    expect(geometry.imageRect.bottom).toBeLessThanOrEqual(geometry.stageRect.bottom + 1);
    expect(Math.abs((geometry.imageRect.top + geometry.imageRect.bottom) / 2 -
      (geometry.stageRect.top + geometry.stageRect.bottom) / 2)).toBeLessThan(1);

    await page.locator('#drawingZoomIn').click();
    await expect(page.locator('#drawingZoomLabel')).toHaveText('120%');
    await page.locator('#drawingZoomIn').click();
    await page.locator('#drawingZoomIn').click();
    await stage.scrollIntoViewIfNeeded();
    const stageBox = await stage.boundingBox();
    await page.mouse.move(stageBox.x + stageBox.width / 2, stageBox.y + stageBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(stageBox.x + stageBox.width / 2 + 80, stageBox.y + stageBox.height / 2 + 60);
    await page.mouse.up();
    const pan = await image.evaluate(node => {
      const transform = new DOMMatrixReadOnly(getComputedStyle(node).transform);
      return Math.hypot(transform.m41, transform.m42);
    });
    // A portrait sheet can overflow vertically only; a landscape sheet horizontally.
    expect(pan).toBeGreaterThan(0);
    await page.locator('#drawingZoomOut').click();
    await expect(page.locator('#drawingZoomLabel')).toHaveText('144%');
    await page.locator('#drawingFit').click();
    await expect(page.locator('#drawingZoomLabel')).toHaveText('100%');
    expect(await image.evaluate(node => new DOMMatrixReadOnly(getComputedStyle(node).transform).m41)).toBe(0);
    await expect(page.locator('#drawingDownloadCurrent')).toHaveAttribute(
      'href', new URL('/mock/' + view + '.dxf', page.url()).href);
    const [download] = await Promise.all([
      page.waitForEvent('download'), page.locator('#drawingDownloadCurrent').click(),
    ]);
    const downloaded = readFileSync(await download.path());
    if (fixtureDir) expect(createHash('sha256').update(downloaded).digest('hex')).toBe(
      createHash('sha256').update(readFileSync(join(fixtureDir, view + '.dxf'))).digest('hex'));
    if (fixtureDir && process.env.BEARING_PREVIEW_SCREENSHOTS) {
      await stage.screenshot({path: join(process.env.BEARING_PREVIEW_SCREENSHOTS, view + '-' + viewport.width + '.png')});
    }
    // Leave the old sheet zoomed: switching sheets must fit the new one.
    await page.locator('#drawingZoomIn').click();
  }
  await page.locator('#workspace3dTab').click();
  await expect(page.locator('#viewport canvas')).toBeVisible();
  await page.locator('#workspace2dTab').click();
  await expect(image).toBeVisible();
  expect(pageErrors).toEqual([]);
}

for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
  test('four SVG sheets fit, pan, reset and download at ' + viewport.width + 'px', async ({page}) => {
    await checkPreview(page, viewport);
  });
}

test('local CADImport DXF/SVG sheets fit and DXF downloads retain their SHA256', async ({page}) => {
  test.skip(!process.env.BEARING_DRAWING_FIXTURES, 'Set BEARING_DRAWING_FIXTURES to a local four-sheet DXF/SVG directory');
  for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
    await checkPreview(page, viewport, process.env.BEARING_DRAWING_FIXTURES);
    await page.unrouteAll({behavior: 'wait'});
  }
});

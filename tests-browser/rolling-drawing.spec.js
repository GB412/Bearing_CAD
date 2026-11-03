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
          unfilled_template_variable_count: 2,
          unfilled_database_unused_count: 54,
          sheets: sheets.map(([view, file, preview_file]) => ({
            view, file, preview_file,
            variable_diagnostics: {
              unfilled_variable_count: view === 'assembly' ? 2 : 0,
              unfilled_variable_names: view === 'assembly' ? ['C_', 'W01'] : [],
            },
          })),
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
  await expect(page.locator('#drawingWorkspaceSubtitle')).toContainText('模板实际命中空变量 2 项');
  await expect(page.locator('#drawingSheetDiagnostics')).toContainText('C_、W01');
  await expect(page.locator('#drawingDownloadCurrent')).toHaveAttribute('download', 'assembly.dxf');

  await page.locator('#drawingSheetTabs [data-sheet-key="outer_ring"]').click();
  await expect(page.locator('#drawingSheetTitle')).toHaveText('外圈图');
  await expect(page.locator('#drawingSheetDiagnostics')).toContainText('均有值');
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
  await expect(page.locator('#drawingSheetDiagnostics')).toHaveText('');

  expect(errors).toEqual([]);
});


test('NUP source template composition exposes fifth detachable rib DXF', async ({page}) => {
  const job='f'.repeat(32), hash='d'.repeat(64);
  const manifestUrl='/api/v2/cad/drawings/'+job;
  const views=['assembly','outer_ring','inner_ring','cage','loose_rib'];
  const sheets=views.map(view=>({view,file:view+'.dxf',preview_file:view+'.svg'}));
  const urls=Object.fromEntries(views.flatMap(view=>[
    [view+'.dxf',manifestUrl+'/files/'+view+'.dxf'],
    [view+'.svg',manifestUrl+'/files/'+view+'.svg'],
  ]));

  await page.route('**/api/v2/cad/**', async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/v2/cad/status')return route.fulfill({json:{available:true,
      supported_bearings:['rolling.cylindrical_roller']}});
    if(path==='/api/v2/cad/drawings/status')return route.fulfill({json:{
      available:true,supported_bearings:['rolling.cylindrical_roller:NUP'],failures:[],
    }});
    if(path==='/api/v2/cad/drawings' && route.request().method()==='POST'){
      const req=route.request().postDataJSON();
      expect(req.design.parameters.configuration).toBe('NUP');
      return route.fulfill({status:201,json:{manifest_url:manifestUrl,request_hash:hash}});
    }
    if(path===manifestUrl)return route.fulfill({json:{manifest:{
      schema_version:'robas.drawing.bundle.v1',request_hash:hash,
      bearing_type:'rolling.cylindrical_roller',configuration:'NUP',
      sheets},file_urls:urls}});
    if(path.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:drawingSvg});
    return route.fulfill({status:404,json:{}});
  });
  await page.goto('/rolling.html');
  await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
  await page.locator('#param-configuration').selectOption('NUP');
  await expect(page.locator('#generate2d')).toBeEnabled();
  await page.locator('#generate2d').click();
  await expect(page.locator('#drawingSheetTabs [role="tab"]')).toHaveCount(5);
  await expect(page.locator('#drawingTabCount')).toHaveText('5 张已生成');
  await page.locator('#drawingSheetTabs [data-sheet-key="loose_rib"]').click();
  await expect(page.locator('#drawingSheetTitle')).toHaveText('活动挡圈图');
  await expect(page.locator('#drawingDownloadCurrent')).toHaveAttribute('download','loose_rib.dxf');
});

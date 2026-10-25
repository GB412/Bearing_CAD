import { test, expect } from '@playwright/test';

test('built production demo works without external network',async ({page})=>{
  const errors=[];
  page.on('pageerror',err=>errors.push(err.message));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1(:4173)?(?:\/|$)|localhost(:4173)?(?:\/|$))/,route=>route.abort());
  await page.goto('/');
  await expect(page.locator('#stage canvas')).toHaveCount(1);
  await expect.poll(()=>page.evaluate(()=>window.bearingViewerSnapshot?.().parts.length)).toBe(3);
  const before=await page.evaluate(()=>window.bearingViewerSnapshot());
  expect(before.canvasWidth).toBeGreaterThan(0);
  expect(before.canvasHeight).toBeGreaterThan(0);
  for(const part of before.parts)expect(part.vertexCount).toBeGreaterThan(100);
  await page.locator('#shaft_d_mm').fill('60');
  await page.locator('#bush_od_mm').fill('82');
  await page.locator('#housing_od_mm').fill('100');
  await expect(page.locator('#visual2d')).toContainText('60');
  await expect(page.locator('#visual2d')).toContainText('82');
  await expect(page.locator('#visual2d')).toContainText('100');
  const after=await page.evaluate(()=>window.bearingViewerSnapshot());
  expect(after.parts[2].diameterX).toBeGreaterThan(before.parts[2].diameterX);
  expect(errors).toEqual([]);
});

test('invalid input clears scene and blocks exports',async ({page})=>{
 await page.goto('/');
 await expect.poll(()=>page.evaluate(()=>window.bearingViewerSnapshot?.().parts.length)).toBe(3);
 await page.locator('#radial_clearance_mm').fill('0.00549');
 await expect(page.locator('#previewInvalid')).toBeVisible();
 await expect(page.locator('#visual2d')).toHaveText('');
 await expect.poll(()=>page.evaluate(()=>window.bearingViewerSnapshot().parts.length)).toBe(0);
 for(const id of ['saveSvg','saveDxf','saveJson'])await expect(page.locator('#'+id)).toBeDisabled();
 await page.locator('#radial_clearance_mm').fill('0.05');
 await expect.poll(()=>page.evaluate(()=>window.bearingViewerSnapshot().parts.length)).toBe(3);
});

test('3D visibility, transparency, cutaway and explosion change actual scene objects',async ({page})=>{
 await page.goto('/');
 await expect.poll(()=>page.evaluate(()=>window.bearingViewerSnapshot?.().parts.length)).toBe(3);
 await page.locator('#showHousing').uncheck();
 expect((await page.evaluate(()=>window.bearingViewerSnapshot())).parts[0].visible).toBe(false);
 await page.locator('#showHousing').check();
 await page.locator('#transparent').check();
 expect((await page.evaluate(()=>window.bearingViewerSnapshot())).parts[0].opacity).toBeLessThan(1);
 await page.locator('#cutaway').uncheck();
 const whole=await page.evaluate(()=>window.bearingViewerSnapshot());
 await page.locator('#cutaway').check();
 const cut=await page.evaluate(()=>window.bearingViewerSnapshot());
 expect(cut.parts[0].vertexCount).not.toBe(whole.parts[0].vertexCount);
 await page.locator('#explode').fill('90');
 const exploded=await page.evaluate(()=>window.bearingViewerSnapshot());
 expect(exploded.parts[0].positionZ).toBeLessThan(0);
 expect(exploded.parts[2].positionZ).toBeGreaterThan(0);
});

test('fixed demo STEP and generated DXF are available in production',async ({page})=>{
 await page.goto('/');
 const response=await page.request.get('/outputs/bearing_assembly.step');
 expect(response.ok()).toBeTruthy();
 expect((await response.body()).length).toBeGreaterThan(1000);
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#saveDxf').click()]);
 expect(download.suggestedFilename()).toBe('bearing_section.dxf');
});

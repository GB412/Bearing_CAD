import {test,expect} from '@playwright/test';

// Do not intercept /api/v2/cad; these are real OCCT-generated STEP/STL files.
test('browser, real CAD API, STEP and STL complete all migrated cage assemblies',async({page})=>{
 const errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto('/rolling.html');
 await expect(page.locator('#connection')).toContainText('在线');
 await expect(page.locator('#generate')).toBeEnabled();

 async function build(expectedInstances,expectedParts,expectedKind){
  await page.locator('#generate').click();
  await expect.poll(
   ()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length),
   {timeout:160_000}
  ).toBe(expectedInstances);
  await expect(page.locator('#parts input')).toHaveCount(expectedInstances);
  await expect(page.locator('#quality')).toContainText('CAD 几何已检查');
  const screenshot=await page.evaluate(()=>window.rollingViewerSnapshot());
  expect(screenshot.instances.every(x=>x.triangles>0)).toBe(true);
  expect(screenshot.requestHash).toMatch(/^[0-9a-f]{64}$/);

  const all=page.locator('#downloads a');
  await expect(all.filter({hasText:'bearing_assembly.step'})).toHaveCount(1);
  await expect(all.filter({hasText:'geometry_quality.json'})).toHaveCount(1);
  const step=page.locator('#downloads a').filter({hasText:'bearing_assembly.step'});
  const address=await step.getAttribute('href');
  expect(address).toMatch(/^\/api\/v2\/cad\/artifacts\/[0-9a-f]{32}\/files\/bearing_assembly\.step$/);
  const response=await page.request.get(address);
  expect(response.ok()).toBe(true);
  const bytes=await response.body();
  expect(bytes.byteLength).toBeGreaterThan(10000);
  expect(bytes.subarray(0,500).toString('utf8')).toContain('ISO-10303-21');

  const base=address.replace('/files/bearing_assembly.step','');
  const meta=await page.request.get(base);
  expect(meta.ok()).toBe(true);
  const {manifest,file_urls}=await meta.json();
  expect(manifest.instances).toHaveLength(expectedInstances);
  expect(manifest.parts).toHaveLength(expectedParts);
  expect(manifest.completeness).toBe(expectedKind);
  expect(manifest.request_hash).toBe(screenshot.requestHash);
  expect(Object.keys(manifest.files)).toContain('geometry_quality.json');
  expect(file_urls['bearing_assembly.step']).toBe(address);
  const quality=await page.request.get(file_urls['geometry_quality.json']);
  expect(quality.ok()).toBe(true);
  const q=await quality.json();
  expect(q.instance_count).toBe(expectedInstances);
  expect(q.step_roundtrip.solid_count).toBe(expectedInstances);
  expect(q.step_roundtrip.worst_part_centroid_error_mm).toBeLessThan(0.001);
  return manifest;
 }

 // Deep-groove pressed halves: 11 balls + 11 rivets + 2 halves + 2 rings.
 await page.locator('#cageKind').selectOption('stamping_double_half');
 const deep=await build(26,6,'STAMPING_DOUBLE_HALF');
 expect(deep.instances.filter(x=>x.part_id==='rivet')).toHaveLength(11);
 expect(deep.instances.filter(x=>x.part_id.startsWith('cage_'))).toHaveLength(2);

 // NUP detached collar remains a distinct entity in the real backend STEP.
 await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
 await page.locator('#param-configuration').selectOption('NUP');
 await page.locator('#cageEnabled').check();
 const cyl=await build(15,5,'CYLINDRICAL_WINDOW_CAGE');
 expect(cyl.parts.some(x=>x.id==='loose_rib')).toBe(true);

 // 25-degree angular-contact model includes a real radial window cage.
 await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
 await page.locator('#cageEnabled').check();
 await build(14,4,'STRAIGHT_POCKET_CAGE');

 // UI input invalidation and a real HTTP 422 must remove stale geometry.
 await page.locator('#param-pitch_d_mm').fill('100');
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(0);
 await page.locator('#generate').click();
 await expect(page.locator('#status')).toContainText('CAD 生成失败');
 await expect(page.locator('#downloads a')).toHaveCount(0);
 expect(errors).toEqual([]);
});


test('real OCCT builds a rescaled 50 mm bore angular-contact assembly',async({page})=>{
 await page.goto('/rolling.html');
 await expect(page.locator('#generate')).toBeEnabled();
 await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
 await page.locator('#scaleTarget').fill('50');
 await page.locator('#scaleApply').click();
 await expect(page.locator('#validation')).toBeHidden();
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length),
  {timeout:160_000}).toBe(13);
 const stepLink=page.locator('#downloads a').filter({hasText:'bearing_assembly.step'});
 await expect(stepLink).toBeVisible();
 const href=await stepLink.getAttribute('href');
 const url=href.replace('/files/bearing_assembly.step','');
 const meta=await (await page.request.get(url)).json();
 const design=(await (await page.request.get(meta.file_urls['design_snapshot.json'])).json());
 expect(design.parameters.bore_d_mm).toBe(50);
 expect(design.parameters.outside_d_mm).toBe(85);
 expect(design.parameters.contact_angle_deg).toBe(25);
 expect(meta.manifest.instances).toHaveLength(13);
});

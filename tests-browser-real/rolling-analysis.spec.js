import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {test, expect} from '@playwright/test';

const route = '/api/v2/cad/analyses';
const cases = [
  {
    name: 'DGB', type: 'rolling.deep_groove_ball',
    dimensions: {bore_d_mm:40,outside_d_mm:68,width_mm:15,ball_d_mm:8.334,pitch_d_mm:54,
      ball_count:11,inner_groove_radius_mm:4.50036,outer_groove_radius_mm:4.33368,
      inner_shoulder_d_mm:49,outer_shoulder_d_mm:59.02},
    geometry:{inner_race_od_mm:49}, firstLoad:2251, nonfinite:15,
  },
  {
    name: 'ACB', type: 'rolling.angular_contact_ball',
    dimensions: {bore_d_mm:65,outside_d_mm:100,width_mm:18,ball_d_mm:11,pitch_d_mm:82.5,
      ball_count:20,inner_groove_radius_mm:5.94,outer_groove_radius_mm:5.72,contact_angle_deg:25,
      inner_shoulder_left_d_mm:75.9,inner_shoulder_right_d_mm:72.44,
      outer_shoulder_left_d_mm:92.56,outer_shoulder_right_d_mm:89.15},
    geometry:{inner_race_od_mm:75.9,inner_sidewall_mm:75.9,outer_sidewall_mm:89.15}, firstLoad:954.5, nonfinite:15,
  },
  {
    name: 'N222', type: 'rolling.cylindrical_roller',
    dimensions: {bore_d_mm:110,outside_d_mm:200,width_mm:38,roller_d_mm:28,roller_length_mm:28,
      pitch_d_mm:155,roller_count:14,radial_clearance_mm:0,axial_clearance_mm:.1,rib_width_mm:3,
      inner_rib_tip_d_mm:137.22,outer_rib_tip_d_mm:172.78},
    geometry:{}, firstLoad:16750, nonfinite:5,
  },
];

test.skip(process.platform !== 'win32' || !process.env.ROBAS_BROWSER_PROFILES,
  'requires Windows original RoBAS.exe and operator-owned DGB, ACB and N222 profile manifest');

async function run(page) {
  const response = page.waitForResponse(res => new URL(res.url()).pathname === route && res.request().method() === 'POST',
    {timeout:75_000});
  await page.locator('#runAnalysis').click();
  const result = await response;
  const data = await result.json();
  expect(result.status(), JSON.stringify(data)).toBe(201);
  await expect(page.locator('#analysisResultVersion')).toHaveText('当前设计与工况的结果');
  expect(data.result.execution).toEqual({status:'EXITED_ZERO',exit_code:0});
  expect(data.result.source_binding.status).toBe('HASH_VERIFIED');
  expect(data.result.output_status).toBe('PARSED_SUPPORTED_SECTIONS');
  expect(data.result.convergence.status).toBe('UNKNOWN');
  expect(data.result.files['DATA.txt'].sha256).toBe(data.generated_data_sha256);
  return {data, submitted:result.request().postDataJSON()};
}

for (const spec of cases) {
  test('Windows original solver from the workbench · ' + spec.name, async ({page}, info) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/rolling.html');
    await expect(page.locator('#generate')).toBeEnabled();
    await page.locator('#bearingType').selectOption(spec.type);
    await page.locator('#cageEnabled').uncheck();
    if (spec.name === 'N222') {
      await page.locator('#param-configuration').selectOption('N');
      await page.locator('#param-roller_profile').selectOption('plain');
    } else {
      await page.locator('#explicitBallGeometry').check();
      if (spec.name === 'ACB') await page.locator('#param-cage_material').selectOption('');
    }
    for (const [field,value] of Object.entries(spec.dimensions)) await page.locator('#param-' + field).fill(String(value));
    await expect(page.locator('#validation')).toBeHidden();
    await page.locator('#confirmDesign').click();
    await expect(page.locator('#designConfirmation')).toContainText('当前设计已确认');
    await page.locator('#generate').click();
    await expect(page.locator('#quality')).toHaveText('CAD 几何已检查');
    const designUrl = await page.getByRole('link', {name:'design_snapshot.json'}).getAttribute('href');
    const snapshot = await (await page.request.get(designUrl)).body();
    const hash = createHash('sha256').update(snapshot).digest('hex');
    if (spec.name === 'DGB' && process.env.ROBAS_BROWSER_CADIMPORT) {
      await page.locator('#workspace2dTab').click();
      await page.locator('#drawingModel').fill('6008');
      await page.locator('#drawingClearance').selectOption('C0');
      await expect(page.locator('#generate2d')).toBeEnabled();
      await page.locator('#generate2d').click();
      await expect(page.locator('#drawingDesignVersion')).toContainText('与当前三维作业使用同一设计快照');
      await expect(page.locator('#drawingDesignVersion')).toContainText(hash);
      await expect(page.locator('#drawingPreviewImage')).toBeVisible();
    }
    await page.locator('#workspaceAnalysisTab').click();
    await expect(page.locator('#analysisAvailability')).toHaveText('本机分析配置可用');
    const profile = page.locator('#analysisProfile option:enabled:not([value=""])');
    await expect(profile).toHaveCount(1);
    await page.locator('#analysisProfile').selectOption(await profile.getAttribute('value'));
    for (const [key,value] of Object.entries(spec.geometry)) {
      const field = page.locator('#analysis-' + key);
      if (key.endsWith('sidewall_mm')) await field.selectOption(String(value));
      else await field.fill(String(value));
    }
    const baseline = await run(page);
    expect(baseline.submitted.design).toEqual(JSON.parse(snapshot));
    expect(baseline.data.request_hash).toBe(hash);
    expect(baseline.data.analysis_geometry).toEqual(spec.geometry);
    expect(baseline.data.result.contacts[0].outer.load.value).toBe(spec.firstLoad);
    expect(baseline.data.result.nonfinite_evidence).toHaveLength(spec.nonfinite);
    await page.getByText('内外圈接触数据', {exact:true}).click();
    await expect(page.getByRole('cell', {name:String(spec.firstLoad),exact:true}).first()).toBeVisible();
    await page.getByText('非有限输出 · ' + spec.nonfinite + ' 项').click();
    await expect(page.getByRole('cell', {name:'NaN',exact:true}).first()).toBeVisible();
    await page.screenshot({path:info.outputPath(spec.name + '-browser.png'),fullPage:true});
    if (spec.name === 'DGB') {
      await page.locator('#analysis-load_z_n').fill('2400');
      await expect(page.locator('#analysisResultVersion')).toContainText('历史结果');
      const changed = await run(page);
      expect(changed.submitted.operating_conditions).toEqual({load_z_n:2400});
      expect(changed.data.operating_conditions.effective.load_z_n).toBe(2400);
      expect(changed.data.request_hash).toBe(baseline.data.request_hash);
      expect(changed.data.run_id).not.toBe(baseline.data.run_id);
      expect(changed.data.generated_data_sha256).not.toBe(baseline.data.generated_data_sha256);
      expect(changed.data.result.files['OUT.txt'].sha256).not.toBe(baseline.data.result.files['OUT.txt'].sha256);
      expect(changed.data.result.contacts[0].outer.load.value).toBe(2330);
      const root = process.env.ROBAS_BROWSER_ARTIFACTS ?? 'build/real-browser-e2e-artifacts';
      const original = await readFile(root + '/robas-analysis/analysis-' + baseline.data.run_id + '/DATA.txt', 'utf8');
      const updated = await readFile(root + '/robas-analysis/analysis-' + changed.data.run_id + '/DATA.txt', 'utf8');
      const changes = original.split(/\r?\n/).map((line,i) => [line,updated.split(/\r?\n/)[i]]).filter(([a,b]) => a !== b);
      expect(changes).toHaveLength(1);
      expect(changes[0][0].replace(/,2000(?=,|$)/, ',2400.0')).toBe(changes[0][1]);
      await page.locator('#param-width_mm').fill('16');
      await expect(page.locator('#analysisResultVersion')).toContainText('历史结果');
      await expect(page.locator('#runAnalysis')).toBeDisabled();
    }
    expect(errors).toEqual([]);
  });
}

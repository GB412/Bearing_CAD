import {createHash} from 'node:crypto';
import {test, expect} from '@playwright/test';

const base = '/api/v2/cad';
const dgb = 'rolling.deep_groove_ball', acb = 'rolling.angular_contact_ball', crb = 'rolling.cylindrical_roller';
const stl = 'solid part\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid part';
const digest = text => createHash('sha256').update(text).digest('hex');
const profile = {bearing_type: dgb, source: 'Reviewed test profile', sha256: digest('reference'), available: true};
const valid = value => ({value, status: 'VALID'});
const invalid = raw => ({value: null, status: 'INVALID', raw});

async function setup(page, state) {
  let snapshot, hash, job;
  await page.route('**/api/v2/cad/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === base + '/status') return route.fulfill({json: {available:true, supported_bearings:[dgb,acb,crb]}});
    if (path === base + '/analyses/status') return route.fulfill({json: state.readiness ?? {
      available:true, timeout_s:45, profiles:{reviewed:profile},
    }});
    if (path === base + '/jobs') {
      if (state.cadFailure) return route.fulfill({status:422, json:{error:{message:'CAD was rejected'}}});
      snapshot = JSON.stringify(route.request().postDataJSON());
      hash = digest(snapshot);
      job = 'a'.repeat(32);
      return route.fulfill({status:201, json:{status:'succeeded', job_id:job, request_hash:hash, manifest_url:base + '/artifacts/' + job}});
    }
    const artifact = base + '/artifacts/' + job;
    if (path === artifact) {
      const files = ['design_snapshot.json', 'inner_ring.stl'];
      return route.fulfill({json:{job_id:job, file_urls:Object.fromEntries(files.map(name => [name, artifact + '/files/' + name])),
        manifest:{status:'GEOMETRY_VALIDATED', geometry_unit:'mm', request_hash:hash, completeness:'CAGE_OMITTED',
          parts:[{id:'inner_ring',role:'inner_ring'}], files:Object.fromEntries(files.map(name => [name, {}])),
          instances:[{id:'inner_ring',part_id:'inner_ring',translation_mm:[0,0,0]}]}}});
    }
    if (path === artifact + '/files/design_snapshot.json') return route.fulfill({body: state.corruptSnapshot ? '{}' : snapshot});
    if (path === artifact + '/files/inner_ring.stl') return route.fulfill({body:stl});
    if (path === base + '/analyses') {
      const body = route.request().postDataJSON();
      state.posts.push(body);
      if (state.pending) await state.pending;
      if (state.failure) return route.fulfill(state.failure);
      const data = digest(JSON.stringify(body.operating_conditions));
      const caseHash = state.wrongHash ? '0'.repeat(64) : body.request_hash;
      const contact = {load:valid(2251), stress:valid(3402), angle:valid(2), deflection:invalid('NaN')};
      return route.fulfill({status:201,json:{
        ...body, request_hash:caseHash, profile:{id:'reviewed', ...profile},
        run_id:String(state.posts.length).padStart(32,'0'), generated_data_sha256:data, solver_exe_sha256:digest('exe'),
        operating_conditions:{requested:body.operating_conditions, inherited:{}, effective:{
          load_x_n:4500, load_y_n:0, load_z_n:2000, outer_speed_rpm:0, inner_speed_rpm:20000, free_clearance_mm:0,
          ...body.operating_conditions,
        }},
        result:{execution:{status:'EXITED_ZERO',exit_code:0}, source_binding:{status:state.unbound ? 'UNVERIFIED' : 'HASH_VERIFIED'},
          output_status:'PARSED_SUPPORTED_SECTIONS', convergence:{status:'UNKNOWN'},
          summary:{total_power_loss:valid(3092),internal_clearance:invalid('Infinity')},
          contacts:[{rolling_element:1,outer:contact,inner:contact}],
          stiffness_sweep:[{point:1,inner_speed:valid(20000),stiffness_xx:valid(2000)}],
          nonfinite_evidence:[{file:'OUT.txt',line:9,raw:'NaN'},{file:'OUT.txt',line:12,raw:'Infinity'}],
          files:{'DATA.txt':{sha256:data},'OUT.txt':{sha256:digest('output')}},
        },
      }});
    }
    return route.fulfill({status:404, json:{}});
  });
  await page.goto('/rolling.html');
  await expect(page.locator('#generate')).toBeEnabled();
}

async function selectAnalysis(page) {
  await page.locator('#workspaceAnalysisTab').click();
  await expect(page.locator('#analysisProfile option[value="reviewed"]')).toBeEnabled();
  await page.locator('#analysisProfile').selectOption('reviewed');
}

async function cad(page) {
  await page.locator('#generate').click();
  await expect(page.locator('#quality')).toContainText('CAD 几何已检查');
}

test('workbench gates analysis on explicit confirmation and successful CAD', async ({page}) => {
  const state = {posts:[]};
  await setup(page, state);
  await selectAnalysis(page);
  await expect(page.locator('#analysisDesign')).toContainText('显式 CAD 保持架');
  await page.locator('#cageEnabled').uncheck();
  await expect(page.locator('#analysisDesign')).toContainText('先确认');
  await cad(page);
  await expect(page.locator('#runAnalysis')).toBeDisabled();
  await page.locator('#confirmDesign').click();
  await expect(page.locator('#runAnalysis')).toBeEnabled();
  state.cadFailure = true;
  await page.locator('#generate').click();
  await expect(page.locator('#status')).toContainText('CAD 生成失败');
  await expect(page.locator('#analysisDesign')).toContainText('等待成功生成');
  await expect(page.locator('#runAnalysis')).toBeDisabled();
  await page.locator('#bearingType').selectOption(crb);
  await expect(page.locator('#analysisDesign')).toContainText('仅支持 N 型直滚子');
  await page.locator('#bearingType').selectOption(acb);
  await page.locator('#cageEnabled').uncheck();
  await expect(page.locator('#analysisDesign')).toContainText('CAD 保持架材料');
  expect(state.posts).toHaveLength(0);
});

test('unconfigured and invalid profiles remain unavailable', async ({page}) => {
  const state = {posts:[], readiness:{available:false, profiles:{}, unavailable_reason:'未配置'}};
  await setup(page, state);
  await page.locator('#workspaceAnalysisTab').click();
  await expect(page.locator('#analysisAvailability')).toContainText('未配置');
  state.readiness = {available:false, profiles:{reviewed:{...profile, available:false, unavailable_reason:'SHA-256 不匹配'}}};
  await page.locator('#workspaceAnalysisTab').click();
  await expect(page.locator('#analysisAvailability')).toContainText('SHA-256 不匹配');
  await expect(page.locator('#analysisProfile option[value="reviewed"]:disabled')).toHaveCount(1);
  await expect(page.locator('#runAnalysis')).toBeDisabled();
});

test('analysis form reports errors and keeps late results tied to their submitted design and conditions', async ({page}) => {
  const state = {posts:[]};
  await setup(page, state);
  await page.locator('#cageEnabled').uncheck();
  await page.locator('#confirmDesign').click();
  await cad(page);
  await selectAnalysis(page);
  const run = page.locator('#runAnalysis');
  const status = page.locator('#analysisStatus');
  await run.click();
  await expect(status).toContainText('分析内圈外径');
  expect(state.posts).toHaveLength(0);
  await page.locator('#analysis-inner_race_od_mm').fill('49');
  state.corruptSnapshot = true;
  await run.click();
  await expect(status).toContainText('快照 SHA-256 不一致');
  state.corruptSnapshot = false;
  for (const [code, http, text, field] of [
    ['ANALYSIS_BUSY',503,'正处理另一项'], ['ANALYSIS_TIMEOUT',504,'超过执行时限'],
    ['ANALYSIS_RESULT_INVALID',502,'来源绑定失败'], ['DESIGN_HASH_MISMATCH',409,'哈希不一致'],
    ['ANALYSIS_INPUT_INVALID',422,'/analysis_geometry','/analysis_geometry'],
  ]) {
    state.failure = {status:http,json:{error:{error_code:code,message:'backend detail',field_path:field}}};
    await run.click();
    await expect(status).toContainText(text);
    await expect(run).toBeEnabled();
  }
  state.failure = null;
  state.unbound = true;
  await run.click();
  await expect(status).toContainText('文件来源不匹配');
  await expect(page.locator('#analysisResult')).toBeHidden();
  state.unbound = false;
  let release;
  state.pending = new Promise(resolve => {release = resolve;});
  const count = state.posts.length;
  await run.click();
  await expect.poll(() => state.posts.length).toBe(count + 1);
  await expect(run).toBeDisabled();
  await page.locator('#analysis-load_z_n').fill('2400');
  release();
  await expect(page.locator('#analysisResultVersion')).toContainText('历史结果');
  await expect(page.locator('#analysisResultBody')).toContainText('收敛 未知');
  await expect(page.locator('#analysisResultBody')).toContainText('不可用 (Infinity)');
  await page.getByText('非有限输出 · 2 项').click();
  await expect(page.getByRole('cell', {name:'NaN', exact:true})).toBeVisible();
  state.pending = null;
  await run.click();
  await expect(page.locator('#analysisResultVersion')).toHaveText('当前设计与工况的结果');
  expect(state.posts.at(-1).operating_conditions).toEqual({load_z_n:2400});
  expect(state.posts.at(-1).request_hash).toBe(state.posts.at(-2).request_hash);
  await page.locator('#param-width_mm').fill('16');
  await expect(page.locator('#analysisResultVersion')).toContainText('历史结果');
  await expect(run).toBeDisabled();
});

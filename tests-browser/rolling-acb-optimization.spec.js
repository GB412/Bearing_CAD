import {test, expect} from '@playwright/test';

const optimized = {
  schema_version: 'bearing-cad.robas-acb-optimization.v1',
  candidate_only: true, applied: false,
  source_model: '7008', source_initial_hash: 'b'.repeat(64),
  total_valid_candidates: 78,
  warnings: [
    'SOURCE_ACB_MODEL_CATALOG_EMPTY_NO_MODEL_DIMENSION_CERTIFICATION',
    'SOURCE_OPTIMIZER_MAXIMIZES_SPIN_RATIO_ENGINEERING_DIRECTION_UNREVIEWED',
  ],
  candidates: [{
    rank: 1, candidate_id: 'acb-01', score: .87,
    metrics: {spin_ratio: .109, axial_stiffness_source_units: 205,
              dynamic_load_n: 19000, static_load_n: 14000},
    design: {
      schema_version: 'bearing-cad.request.v1',
      bearing_type: 'rolling.angular_contact_ball',
      unit: 'mm', detail_level: 'functional', geometry_strategy: 'explicit',
      parameters: {
        bore_d_mm:40, outside_d_mm:68, width_mm:15,
        ball_d_mm:8.33438, pitch_d_mm:54.5, ball_count:16,
        inner_groove_radius_mm:4.2927057,
        outer_groove_radius_mm:4.3755495,
        contact_angle_deg:25, cage_material:'engineering_plastic',
        inner_shoulder_left_d_mm:49,
        inner_shoulder_right_d_mm:47.75,
        outer_shoulder_left_d_mm:61,
        outer_shoulder_right_d_mm:59.75,
      },
    },
  }],
};

async function setup(page, observed) {
  await page.route('**/api/v2/cad/**', async route => {
    const request=route.request(), url=new URL(request.url()), path=url.pathname;
    if(path==='/api/v2/cad/status')
      return route.fulfill({json:{
        available:true,robas_sizing_available:true,
        robas_optimization_available:true,
        robas_acb_optimization_available:true,
        supported_bearings:['rolling.deep_groove_ball','rolling.angular_contact_ball'],
      }});
    if(path==='/api/v2/cad/drawings/status')
      return route.fulfill({json:{
        available:true,supported_bearings:['rolling.deep_groove_ball','rolling.angular_contact_ball'],
      }});
    if(path==='/api/v2/cad/optimization/acb'){
      observed.optimize=request.postDataJSON();
      observed.requests=(observed.requests??0)+1;
      if(observed.pending)await observed.pending;
      return route.fulfill(observed.optimizationResponse??{json:optimized});
    }
    if(path==='/api/v2/cad/jobs'){
      observed.cad=request.postDataJSON();
      return route.fulfill({status:422,json:{error:{error_code:'TEST_STOP',field_path:'',
        message:'Mock stops before real OCCT geometry'}}});
    }
    if(path==='/api/v2/cad/drawings'){
      observed.drawing=request.postDataJSON();
      return route.fulfill({status:422,json:{error:{error_code:'TEST_STOP',
        message:'Mock stops before real CADImport'}}});
    }
    return route.fulfill({status:404,json:{error:{message:'Not found'}}});
  });
  await page.goto('/rolling.html');
  await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
  await expect(page.locator('#acbOptimizationPanel')).toBeVisible();
  await page.locator('#acbModel').fill('7008');
  await expect(page.locator('#runRoBASACBOptimizer')).toBeEnabled();
  await expect(page.locator('#dgbOptimizationPanel')).toBeHidden();
}

test('ACB source-weighted candidates are read-only until explicit selection; 2D/3D share applied parameters', async ({page})=>{
  const observed={};
  await setup(page,observed);
  const previous=await page.locator('#param-ball_count').inputValue();
  await page.locator('#runRoBASACBOptimizer').click();
  const card=page.locator('#acbOptimizationCandidates .optimization-candidate');
  await expect(card).toHaveCount(1);
  await expect(page.locator('#acbOptimizationHint')).toContainText('找到 78 组可行方案');
  for(const metric of ['钢球直径','球数','节圆直径','动载荷 Cr','轴向刚度 Ka','旋滚比'])
    await expect(card.locator('dt').filter({hasText:metric})).toHaveCount(1);
  expect(observed.optimize.initial).toEqual({
    bearing_type:'rolling.angular_contact_ball',
    bore_d_mm:40, outside_d_mm:68,width_mm:15,
    contact_angle_deg:25,cage_material:'engineering_plastic',cage:null,
  });
  expect(observed.optimize.optimization).toEqual({
    model:'7008', accuracy_class:'P5',preload_n:100,
    weights:{spin_ratio:.3,axial_stiffness:.3,dynamic_load:.4},
  });
  await expect(page.locator('#param-ball_count')).toHaveValue(previous);
  expect(observed.cad).toBeUndefined();
  expect(observed.drawing).toBeUndefined();

  await page.getByRole('button',{name:'确认并应用此设计'}).click();
  await expect(page.locator('#param-ball_d_mm')).toHaveValue('8.33438');
  await expect(page.locator('#param-ball_count')).toHaveValue('16');
  await expect(page.locator('#param-pitch_d_mm')).toHaveValue('54.5');
  await expect(page.locator('#param-inner_shoulder_right_d_mm')).toHaveValue('47.75');
  await expect(page.locator('#param-outer_shoulder_right_d_mm')).toHaveValue('59.75');
  await expect(page.locator('#acbOptimizationResults')).toBeHidden();
  await expect(page.locator('#acbOptimizationHint')).toContainText('三维完成后可进入拟静力学分析');

  await page.locator('#generate').click();
  await expect.poll(()=>observed.cad?.parameters?.ball_count).toBe(16);
  expect(observed.cad.parameters.pitch_d_mm).toBe(54.5);
  await page.locator('#workspace2dTab').click();
  await page.locator('#generate2d').click();
  await expect.poll(()=>observed.drawing?.design?.parameters?.ball_count).toBe(16);
  expect(observed.drawing.design.parameters.pitch_d_mm).toBe(54.5);
  expect(observed.drawing.drawing.model).toBe('7008');
});

test('ACB changing preload invalidates old candidate and leaves geometry unchanged',async ({page})=>{
  const observed={};
  await setup(page,observed);
  const original=await page.locator('#param-ball_count').inputValue();
  await page.locator('#runRoBASACBOptimizer').click();
  await expect(page.locator('#acbOptimizationResults')).toBeVisible();
  await page.locator('#acbPreloadN').fill('200');
  await expect(page.locator('#acbOptimizationResults')).toBeHidden();
  await expect(page.locator('#acbOptimizationHint')).toContainText('原候选已失效');
  await expect(page.locator('#param-ball_count')).toHaveValue(original);
});

test('ACB enabled cage explicitly blocks optimization until recalculated',async ({page})=>{
  const observed={};
  await setup(page,observed);
  await page.locator('#cageEnabled').check();
  await page.locator('#runRoBASACBOptimizer').click();
  await expect(page.locator('#acbCageHint')).toContainText('请先取消保持架');
  await expect(page.locator('#acbOptimizationHint')).toContainText('请先取消保持架');
  expect(observed.optimize).toBeUndefined();
});


test('ACB shares model edits both ways and validates series and weights before submitting',async ({page})=>{
  const observed={};
  await setup(page,observed);
  const model=page.locator('#acbModel');
  const run=page.locator('#runRoBASACBOptimizer');
  const feedback=page.locator('#acbOptimizationHint');
  await model.fill('6208');
  await expect(model).toHaveAttribute('aria-invalid','true');
  await expect(page.locator('#acbModelHint')).toContainText('70、72 或 73');
  await run.click();
  await expect(feedback).toContainText('70、72 或 73');
  expect(observed.requests).toBeUndefined();
  await page.locator('#workspace2dTab').click();
  await expect(page.locator('#drawingModel')).toHaveValue('6208');
  await page.locator('#drawingModel').fill('7208');
  await page.locator('#workspace3dTab').click();
  await expect(model).toHaveValue('7208');
  await expect(model).toHaveAttribute('aria-invalid','false');
  await page.locator('#acbSpinWeight').fill('0.5');
  await expect(page.locator('#acbWeightHint')).toContainText('须等于 1');
  await run.click();
  await expect(feedback).toContainText('须等于 1');
  expect(observed.requests).toBeUndefined();
  await page.locator('#acbSpinWeight').fill('0.3');
  await expect(page.locator('#acbWeightHint')).toHaveText('权重合计 1');
  await run.click();
  await expect(feedback).toContainText('找到 78 组');
  expect(observed.optimize.optimization.model).toBe('7208');
});

test('ACB reports busy and stale responses near the button, and gives actionable errors',async ({page})=>{
  let release;
  const observed={pending:new Promise(resolve=>{release=resolve;})};
  await setup(page,observed);
  const run=page.locator('#runRoBASACBOptimizer');
  const feedback=page.locator('#acbOptimizationHint');
  await run.click();
  await expect(feedback).toHaveText('正在计算候选方案…');
  await expect(run).toBeDisabled();
  await expect.poll(()=>observed.requests).toBe(1);
  await page.locator('#acbPreloadN').fill('150');
  await expect(feedback).toContainText('原候选已失效');
  release();
  await expect(run).toBeEnabled();
  await expect(page.locator('#acbOptimizationResults')).toBeHidden();
  observed.optimizationResponse={status:422,json:{error:{message:'No ACB candidate satisfies RoBAS search bounds'}}};
  await run.click();
  await expect(feedback).toContainText('未找到可行候选');
  await expect(feedback).toContainText('核对型号');
  observed.optimizationResponse={status:503,json:{error:{message:'Resources unavailable'}}};
  await run.click();
  await expect(feedback).toContainText('检查本机 RoBAS 资源配置');
  await expect(run).toBeEnabled();
});

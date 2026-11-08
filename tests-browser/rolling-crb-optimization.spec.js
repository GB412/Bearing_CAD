import {test,expect} from '@playwright/test';

const candidate={
  schema_version:'bearing-cad.robas-crb-optimization.v1',
  candidate_only:true,applied:false,
  objective_status:'CR_ONLY_SOURCE_KR_NOT_IMPLEMENTED',
  source_model:'NU208',source_initial_hash:'c'.repeat(64),
  total_valid_candidates:180,
  total_distinct_structures:12,
  candidates:[{
    rank:1,candidate_id:'crb-01',score:1.0,
    metrics:{
      dynamic_load_n:112000,static_load_n:34000,
      radial_stiffness_source_units:null,
    },
    design:{
      schema_version:'bearing-cad.request.v1',
      bearing_type:'rolling.cylindrical_roller',
      unit:'mm',detail_level:'functional',geometry_strategy:'explicit',
      parameters:{
        bore_d_mm:40,outside_d_mm:80,width_mm:18,
        roller_d_mm:11,roller_length_mm:13,
        pitch_d_mm:60.8,roller_count:13,
        configuration:'NU',radial_clearance_mm:.05,
        axial_clearance_mm:.4,rib_width_mm:2,
        inner_rib_tip_d_mm:54.475,
        outer_rib_tip_d_mm:67.785,
        roller_profile:'crowned',
        roller_end_chamfer_mm:.2,roller_crown_relief_mm:.02,
      },
    },
  }],
};

async function setup(page,observed){
  await page.route('**/api/v2/cad/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    if(path==='/api/v2/cad/status')
      return route.fulfill({json:{
        available:true,robas_sizing_available:true,
        robas_optimization_available:true,
        robas_acb_optimization_available:true,
        robas_crb_optimization_available:true,
        supported_bearings:['rolling.deep_groove_ball','rolling.angular_contact_ball',
                            'rolling.cylindrical_roller'],
      }});
    if(path==='/api/v2/cad/drawings/status')
      return route.fulfill({json:{
        available:true,supported_bearings:['rolling.cylindrical_roller:NU'],
      }});
    if(path==='/api/v2/cad/optimization/crb'){
      observed.optimizer=req.postDataJSON();
      return route.fulfill({json:candidate});
    }
    if(path==='/api/v2/cad/jobs'){
      observed.cad=req.postDataJSON();
      return route.fulfill({status:422,json:{error:{
        error_code:'STOP',field_path:'',
        message:'Mock ends before real OCCT build',
      }}});
    }
    if(path==='/api/v2/cad/drawings'){
      observed.drawing=req.postDataJSON();
      return route.fulfill({status:422,json:{error:{
        error_code:'STOP',message:'Mock ends before CADImport',
      }}});
    }
    return route.fulfill({status:404,json:{error:{message:'not found'}}});
  });
  await page.goto('/rolling.html');
  await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
  await page.locator('#param-outside_d_mm').fill('80');
  await page.locator('#workspace2dTab').click();
  await page.locator('#drawingModel').fill('NU208');
  await page.locator('#workspace3dTab').click();
  await expect(page.locator('#crbOptimizationPanel')).toBeVisible();
  await expect(page.locator('#dgbOptimizationPanel')).toBeHidden();
  await expect(page.locator('#acbOptimizationPanel')).toBeHidden();
  await expect(page.locator('#runRoBASCRBOptimizer')).toBeEnabled();
}

test('source CRB Cr-only candidate stays read-only until user confirms, then same 2D/3D parameters',async ({page})=>{
  const observed={};
  await setup(page,observed);
  const original=await page.locator('#param-roller_count').inputValue();
  await page.locator('#runRoBASCRBOptimizer').click();
  await expect(page.locator('#crbOptimizationCandidates .optimization-candidate')).toHaveCount(1);
  await expect(page.locator('#crbOptimizationCandidates')).toContainText('Kr 原版未实现');
  expect(observed.optimizer.initial).toEqual({
    bearing_type:'rolling.cylindrical_roller',
    bore_d_mm:40,outside_d_mm:80,width_mm:18,
    configuration:'NU',radial_clearance_mm:.05,
    axial_clearance_mm:.4,rib_width_mm:2,
    roller_profile:'crowned',
    roller_end_chamfer_mm:.2,roller_crown_relief_mm:.02,
    cage:null,
  });
  expect(observed.optimizer.optimization).toEqual({
    model:'NU208',accuracy_class:'P5',objective:'dynamic_load_only',
  });
  await expect(page.locator('#param-roller_count')).toHaveValue(original);
  expect(observed.cad).toBeUndefined();
  expect(observed.drawing).toBeUndefined();
  await page.getByRole('button',{name:'确认并应用此设计'}).click();
  await expect(page.locator('#param-roller_d_mm')).toHaveValue('11');
  await expect(page.locator('#param-roller_length_mm')).toHaveValue('13');
  await expect(page.locator('#param-roller_count')).toHaveValue('13');
  await expect(page.locator('#param-pitch_d_mm')).toHaveValue('60.8');
  await expect(page.locator('#param-inner_rib_tip_d_mm')).toHaveValue('54.475');
  await expect(page.locator('#crbOptimizationResults')).toBeHidden();
  await page.locator('#generate').click();
  await expect.poll(()=>observed.cad?.parameters?.roller_count).toBe(13);
  expect(observed.cad.parameters.pitch_d_mm).toBe(60.8);
  await page.locator('#workspace2dTab').click();
  await page.locator('#generate2d').click();
  await expect.poll(()=>observed.drawing?.design?.parameters?.roller_count).toBe(13);
  expect(observed.drawing.design.parameters.pitch_d_mm).toBe(60.8);
});

test('CRB changing model invalidates old candidates without writing current parameters',async ({page})=>{
  const observed={};
  await setup(page,observed);
  const before=await page.locator('#param-roller_count').inputValue();
  await page.locator('#runRoBASCRBOptimizer').click();
  await expect(page.locator('#crbOptimizationResults')).toBeVisible();
  await page.locator('#workspace2dTab').click();
  await page.locator('#drawingModel').fill('NUP208');
  await page.locator('#workspace3dTab').click();
  await expect(page.locator('#crbOptimizationResults')).toBeHidden();
  await expect(page.locator('#param-roller_count')).toHaveValue(before);
});

test('CRB existing window cage is rejected before sending optimization',async ({page})=>{
  const observed={};
  await setup(page,observed);
  await page.locator('#cageEnabled').check();
  await page.locator('#runRoBASCRBOptimizer').click();
  await expect(page.locator('#status')).toContainText('先取消原有窗孔保持架');
  expect(observed.optimizer).toBeUndefined();
});

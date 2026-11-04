import {test,expect} from '@playwright/test';

test('RoBAS DGBGeometry preset fills only source-backed dimensions',async({page})=>{
 const requests=[],errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 const profile={
  schema_version:'bearing-cad.robas-dgb-geometry.v1',
  candidate_only:true,
  parameters:{
   bore_d_mm:40,outside_d_mm:68,width_mm:15,ball_d_mm:8.33438,
   pitch_d_mm:54,ball_count:11,inner_groove_radius_mm:4.2505338,
   outer_groove_radius_mm:4.4172214,inner_shoulder_d_mm:48.999372,
   outer_shoulder_d_mm:59.013628
  },
  simplified_cage_dimensions:{inner_d_mm:49.97935944,outside_d_mm:57.83335544,width_mm:14.25},
  source_files:{'BallDB.csv':'a'.repeat(64)},
  warnings:['not an optimizer result']
 };
 await page.route('**/api/v2/cad/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/v2/cad/status')
   return route.fulfill({json:{available:true,robas_sizing_available:true,
    supported_bearings:['rolling.deep_groove_ball','rolling.cylindrical_roller','rolling.angular_contact_ball']}});
  if(path==='/api/v2/cad/sizing/dgb-geometry'){
   requests.push(route.request().postDataJSON());
   return route.fulfill({json:profile});
  }
  return route.fulfill({status:404,json:{error:{message:'not found'}}});
 });
 await page.goto('/rolling.html');
 const button=page.locator('#applyRoBASGeometry');
 await expect(button).toBeVisible();
 await expect(button).toBeEnabled();
 await button.click();
 await expect(page.locator('#param-ball_d_mm')).toHaveValue('8.33438');
 await expect(page.locator('#param-pitch_d_mm')).toHaveValue('54');
 await expect(page.locator('#param-ball_count')).toHaveValue('11');
 await expect(page.locator('#param-inner_groove_radius_mm')).toHaveValue('4.2505338');
 await expect(page.locator('#param-outer_groove_radius_mm')).toHaveValue('4.4172214');
 await expect(page.locator('#param-inner_shoulder_d_mm')).toHaveValue('48.999372');
 await expect(page.locator('#param-outer_shoulder_d_mm')).toHaveValue('59.013628');
 await expect(page.locator('#cage-inner_d_mm')).toHaveValue('49.97935944');
 await expect(page.locator('#cage-outside_d_mm')).toHaveValue('57.83335544');
 await expect(page.locator('#cage-width_mm')).toHaveValue('14.25');
 await expect(page.locator('#cage-pocket_clearance_mm')).toHaveValue('0.25');
 expect(requests).toEqual([{bearing_type:'rolling.deep_groove_ball',bore_d_mm:40,outside_d_mm:68,width_mm:15}]);
 await expect(page.locator('#status')).toContainText('未运行 DGBOptimizer');
 await page.locator('#cageKind').selectOption('stamping_double_half');
 await expect(page.locator('#cage-board_thickness_mm')).toHaveValue('0.7');
 await expect(page.locator('#cage-rivet_head_d_mm')).toHaveValue('1.6');
 await button.click();
 await expect(page.locator('#cage-board_thickness_mm')).toHaveValue('0.7');
 await expect(page.locator('#cage-rivet_head_d_mm')).toHaveValue('1.6');
 await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
 await expect(button).toBeHidden();
 expect(errors).toEqual([]);
});

test('a stale RoBAS sizing response cannot overwrite a newer manual edit',async({page})=>{
 let releaseSizing;
 const pending=new Promise(resolve=>{releaseSizing=resolve;});
 const profile={
  schema_version:'bearing-cad.robas-dgb-geometry.v1',
  candidate_only:true,
  parameters:{
   bore_d_mm:40,outside_d_mm:68,width_mm:15,ball_d_mm:8.33438,
   pitch_d_mm:54,ball_count:11,inner_groove_radius_mm:4.2505338,
   outer_groove_radius_mm:4.4172214,inner_shoulder_d_mm:48.999372,
   outer_shoulder_d_mm:59.013628
  },
  simplified_cage_dimensions:{inner_d_mm:49.97935944,outside_d_mm:57.83335544,width_mm:14.25},
  source_files:{'BallDB.csv':'a'.repeat(64)},warnings:[]
 };
 await page.route('**/api/v2/cad/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/v2/cad/status')
   return route.fulfill({json:{available:true,robas_sizing_available:true,
    supported_bearings:['rolling.deep_groove_ball','rolling.cylindrical_roller','rolling.angular_contact_ball']}});
  if(path==='/api/v2/cad/sizing/dgb-geometry'){
   await pending;
   return route.fulfill({json:profile});
  }
  return route.fulfill({status:404,json:{error:{message:'not found'}}});
 });
 await page.goto('/rolling.html');
 const button=page.locator('#applyRoBASGeometry');
 await expect(button).toBeEnabled();
 await button.click();
 await page.locator('#param-ball_d_mm').fill('9');
 releaseSizing();
 await expect(page.locator('#param-ball_d_mm')).toHaveValue('9');
 await expect(page.locator('#status')).toContainText('输入已改变');
 await expect(button).toBeEnabled();
});


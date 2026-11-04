import {test,expect} from '@playwright/test';

const profile={
 schema_version:'bearing-cad.robas-stamping-adapter.v1',
 candidate_only:true,bearing_model:'6008',
 cad_cage:{
  kind:'stamping_double_half',
  inner_d_mm:50.4,outside_d_mm:57.6,width_mm:10.2,
  pocket_clearance_mm:.4,board_thickness_mm:.7,
  rivet_shaft_d_mm:1,rivet_head_d_mm:1.6,rivet_hole_clearance_mm:.05
 },
 source_dimensions:{width_radial_mm:3.6,board_thickness_mm:.7,sphere_radius_mm:4.4},
 warnings:['not manufacturing approved']
};
const status={
 available:true,robas_sizing_available:false,robas_stamping_available:true,
 supported_bearings:['rolling.deep_groove_ball','rolling.cylindrical_roller','rolling.angular_contact_ball']
};
function intercept(page, stampHandler){
 const requests=[];
 page.route('**/api/v2/cad/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/v2/cad/status')return route.fulfill({json:status});
  if(path==='/api/v2/cad/sizing/dgb-stamping'){
   requests.push(route.request().postDataJSON());
   return stampHandler(route);
  }
  return route.fulfill({status:404,json:{error:{message:'not found'}}});
 });
 return requests;
}

test('source RoBAS stamped-cage prefill is opt-in, separate from drawing model',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const requests=intercept(page,route=>route.fulfill({json:profile}));
 await page.goto('/rolling.html');
 const button=page.locator('#applyRoBASStamping');
 await expect(page.locator('#robasStampingActions')).toBeHidden();
 await page.locator('#cageKind').selectOption('stamping_double_half');
 await expect(page.locator('#robasStampingActions')).toBeVisible();
 await expect(button).toBeEnabled();
 await expect(page.locator('#robasStampingModel')).toHaveValue('6008');
 await button.click();
 await expect(page.locator('#cage-inner_d_mm')).toHaveValue('50.4');
 await expect(page.locator('#cage-outside_d_mm')).toHaveValue('57.6');
 await expect(page.locator('#cage-width_mm')).toHaveValue('10.2');
 await expect(page.locator('#cage-pocket_clearance_mm')).toHaveValue('0.4');
 await expect(page.locator('#cage-board_thickness_mm')).toHaveValue('0.7');
 await expect(page.locator('#cage-rivet_shaft_d_mm')).toHaveValue('1');
 await expect(page.locator('#cage-rivet_head_d_mm')).toHaveValue('1.6');
 await expect(page.locator('#cage-rivet_hole_clearance_mm')).toHaveValue('0.05');
 await expect(page.locator('#drawingModel')).toHaveValue('6208');
 expect(requests).toEqual([{
  bearing_type:'rolling.deep_groove_ball',
  bearing_model:'6008',
  ball_d_mm:8,pitch_d_mm:54,ball_count:11,bearing_width_mm:15,
  inner_shoulder_d_mm:47.2,outer_shoulder_d_mm:60.8,
  rivet_hole_clearance_mm:.05
 }]);
 await expect(page.locator('#status')).toContainText('冲压双半笼已预填');
 await page.locator('#cageKind').selectOption('simplified_annular');
 await expect(page.locator('#robasStampingActions')).toBeHidden();
 await page.locator('#cageKind').selectOption('stamping_double_half');
 await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
 await expect(page.locator('#robasStampingActions')).toBeHidden();
 expect(errors).toEqual([]);
});

test('stale stamped cage result cannot overwrite user changes',async({page})=>{
 let release;
 const pending=new Promise(resolve=>{release=resolve;});
 intercept(page,async route=>{await pending;return route.fulfill({json:profile});});
 await page.goto('/rolling.html');
 await page.locator('#cageKind').selectOption('stamping_double_half');
 const button=page.locator('#applyRoBASStamping');
 await expect(button).toBeEnabled();
 await button.click();
 await page.locator('#cage-pocket_clearance_mm').fill('0.35');
 release();
 await expect(page.locator('#cage-pocket_clearance_mm')).toHaveValue('0.35');
 await expect(button).toBeEnabled();
});

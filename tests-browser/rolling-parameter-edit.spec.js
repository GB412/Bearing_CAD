import {test,expect} from '@playwright/test';

test('editing bore reports related fields; scaling preserves explicit geometry',async({page})=>{
 let jobCalls=0,errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/v2/cad/**',route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/api/v2/cad/status')return route.fulfill({json:{
   available:true,supported_bearings:['rolling.deep_groove_ball','rolling.cylindrical_roller','rolling.angular_contact_ball']
  }});
  if(url.pathname==='/api/v2/cad/jobs')jobCalls++;
  return route.fulfill({status:422,json:{error:{error_code:'PARAMETER_INVALID',
   field_path:'/parameters',message:'Invalid geometry'}}});
 });
 await page.goto('/rolling.html');
 await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
 await page.locator('#param-bore_d_mm').fill('50');
 await expect(page.locator('#validation')).toContainText('内圈右肩');
 await expect(page.locator('#param-bore_d_mm')).toHaveAttribute('aria-invalid','true');
 await expect(page.locator('#param-inner_shoulder_right_d_mm')).toHaveAttribute('aria-invalid','true');
 await page.locator('#generate').click();
 await expect(page.locator('#status')).toContainText('CAD 生成失败');
 expect(jobCalls).toBe(0);

 await page.locator('#resetParams').click();
 await page.locator('#scaleTarget').fill('50');
 await page.locator('#scaleApply').click();
 await expect(page.locator('#param-bore_d_mm')).toHaveValue('50');
 await expect(page.locator('#param-outside_d_mm')).toHaveValue('85');
 await expect(page.locator('#param-pitch_d_mm')).toHaveValue('67.5');
 await expect(page.locator('#param-inner_shoulder_right_d_mm')).toHaveValue('58.75');
 await expect(page.locator('#param-contact_angle_deg')).toHaveValue('25');
 await expect(page.locator('#param-ball_count')).toHaveValue('11');
 await expect(page.locator('#validation')).toBeHidden();
 expect(errors).toEqual([]);
});
test('cylindrical zero clearances accepted but count over 64 is highlighted',async({page})=>{
 await page.route('**/api/v2/cad/status',route=>route.fulfill({json:{
  available:true,supported_bearings:['rolling.deep_groove_ball','rolling.cylindrical_roller','rolling.angular_contact_ball']
 }}));
 await page.goto('/rolling.html');
 await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
 await page.locator('#param-radial_clearance_mm').fill('0');
 await page.locator('#param-axial_clearance_mm').fill('0');
 await expect(page.locator('#validation')).toBeHidden();
 await page.locator('#param-roller_count').fill('65');
 await expect(page.locator('#validation')).toContainText('roller_count');
 await expect(page.locator('#param-roller_count')).toHaveAttribute('aria-invalid','true');
});

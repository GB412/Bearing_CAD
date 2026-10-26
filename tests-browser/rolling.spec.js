import {test, expect} from '@playwright/test';
const stl = ['solid stub','facet normal 0 0 1',' outer loop','  vertex 0 0 0','  vertex 1 0 0','  vertex 0 1 0',' endloop','endfacet','endsolid stub'].join('\n');
test('rolling workbench expands STL prototypes and handles changes',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/v2/cad/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const id='a'.repeat(32),base='/api/v2/cad/artifacts/'+id;
  if(path==='/api/v2/cad/status')return route.fulfill({json:{available:true,supported_bearings:['rolling.deep_groove_ball']}});
  if(path==='/api/v2/cad/jobs')return route.fulfill({status:201,json:{status:'succeeded',job_id:id,manifest_url:base}});
  if(path.endsWith('.stl'))return route.fulfill({status:200,contentType:'model/stl',body:stl});
  if(path===base){
   const names=['inner_ring','outer_ring','ball','cage'];
   const instances=[...names.slice(0,2).map(x=>({id:x,part_id:x,translation_mm:[0,0,0]})),
      ...Array.from({length:11},(_,i)=>({id:'ball_'+(i+1),part_id:'ball',translation_mm:[27*Math.cos(i*2*Math.PI/11),27*Math.sin(i*2*Math.PI/11),0]})),
      {id:'cage',part_id:'cage',translation_mm:[0,0,0]}];
   const file_urls=Object.fromEntries(names.map(n=>[n+'.stl',base+'/files/'+n+'.stl']));
   return route.fulfill({json:{manifest:{status:'GEOMETRY_VALIDATED',geometry_unit:'mm',request_hash:'b'.repeat(64),completeness:'SIMPLIFIED_CAGE',
    parts:names.map(n=>({id:n,role:n==='ball'?'rolling_element':n})),instances,files:Object.fromEntries(names.map(n=>[n+'.stl',{size_bytes:10,sha256:'stub'}]))},file_urls}});
  }
  return route.fulfill({status:404,json:{error:{message:'not found'}}});
 });
 await page.goto('/rolling.html');
 await expect(page.locator('#generate')).toBeEnabled();
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot?.().instances.length)).toBe(14);
 const before=await page.evaluate(()=>window.rollingViewerSnapshot());
 expect(before.instances.filter(p=>p.role==='rolling_element')).toHaveLength(11);
 expect(new Set(before.instances.filter(p=>p.role==='rolling_element').map(p=>p.position.slice(0,2).join(','))).size).toBe(11);
 await expect(page.locator('#parts input')).toHaveCount(14);
 await page.locator('#parts input').nth(2).uncheck();
 expect((await page.evaluate(()=>window.rollingViewerSnapshot())).instances[2].visible).toBe(false);
 await page.locator('#transparent').check();
 expect((await page.evaluate(()=>window.rollingViewerSnapshot())).instances[0].opacity).toBeLessThan(1);
 await page.locator('#explode').fill('70');
 expect((await page.evaluate(()=>window.rollingViewerSnapshot())).instances[2].position[0]).not.toBe(before.instances[2].position[0]);
 await page.locator('#param-bore_d_mm').fill('42');
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(0);
 expect(errors).toEqual([]);
});

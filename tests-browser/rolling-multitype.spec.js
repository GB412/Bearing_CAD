import {test,expect} from '@playwright/test';
// B-Rep and STEP correctness are tested by Python/OCCT. This is a browser wiring test.
const stl=['solid stub','facet normal 0 0 1',' outer loop','  vertex 0 0 0','  vertex 1 0 0','  vertex 0 1 0',' endloop','endfacet','endsolid stub'].join('\n');
test('one workbench drives cylindrical NUP and angular contact without stale results',async({page})=>{
 const requests=[],errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/v2/cad/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const id='a'.repeat(32),base='/api/v2/cad/artifacts/'+id;
  if(path==='/api/v2/cad/status')return route.fulfill({json:{available:true,supported_bearings:['rolling.deep_groove_ball','rolling.cylindrical_roller','rolling.angular_contact_ball']}});
  if(path==='/api/v2/cad/jobs'){
   requests.push(route.request().postDataJSON());
   return route.fulfill({status:201,json:{status:'succeeded',job_id:id,manifest_url:base}});
  }
  if(path.endsWith('.stl'))return route.fulfill({status:200,contentType:'model/stl',body:stl});
  if(path===base){
   const req=requests.at(-1),type=req.bearing_type;
   const roll=type==='rolling.cylindrical_roller'?'roller':'ball';
   const loose=type==='rolling.cylindrical_roller'&&req.parameters.configuration==='NUP';
   const stamped=req.cage?.kind==='stamping_double_half';
   const cageParts=stamped?['cage_upper','cage_lower','rivet']:req.cage?['cage']:[];
   const parts=['inner_ring','outer_ring',roll,...(loose?['loose_rib']:[]),...cageParts];
   const n=req.parameters.ball_count??req.parameters.roller_count;
   const instances=[...parts.slice(0,2).map(x=>({id:x,part_id:x,translation_mm:[0,0,0]})),
      ...Array.from({length:n},(_,i)=>({id:roll+'_'+i,part_id:roll,translation_mm:[27*Math.cos(i*2*Math.PI/n),27*Math.sin(i*2*Math.PI/n),0]})),
      ...(loose?[{id:'loose_rib',part_id:'loose_rib',translation_mm:[0,0,0]}]:[]),
      ...(stamped?[{id:'cage_upper',part_id:'cage_upper',translation_mm:[0,0,0]},
        {id:'cage_lower',part_id:'cage_lower',translation_mm:[0,0,0]},
        ...Array.from({length:n},(_,i)=>({id:'rivet_'+i,part_id:'rivet',translation_mm:[27*Math.cos((i+.5)*2*Math.PI/n),27*Math.sin((i+.5)*2*Math.PI/n),0]}))]
        :req.cage?[{id:'cage',part_id:'cage',translation_mm:[0,0,0]}]:[])];
   const file_urls=Object.fromEntries(parts.map(name=>[name+'.stl',base+'/files/'+name+'.stl']));
   return route.fulfill({json:{manifest:{status:'GEOMETRY_VALIDATED',geometry_unit:'mm',request_hash:'b'.repeat(64),completeness:'CAGE_OMITTED',
    parts:parts.map(name=>({id:name,role:name===roll?'rolling_element':name})),instances,
    files:Object.fromEntries(parts.map(name=>[name+'.stl',{size_bytes:100,sha256:'stub'}]))},file_urls}});
  }
  return route.fulfill({status:404,json:{error:{message:'unknown'}}});
 });
 await page.goto('/rolling.html');
 await expect(page.locator('#generate')).toBeEnabled();
 await page.locator('#bearingType').selectOption('rolling.cylindrical_roller');
 await expect(page.locator('#param-configuration')).toBeVisible();
 await expect(page.locator('#cagePanel')).toBeVisible();
 await expect(page.locator('#cageOptions')).toBeHidden();
 await page.locator('#param-configuration').selectOption('NUP');
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(14);
 expect(requests[0].bearing_type).toBe('rolling.cylindrical_roller');
 expect(requests[0].parameters.configuration).toBe('NUP');
 expect(requests[0].cage).toBeUndefined();
 await expect(page.locator('#parts input')).toHaveCount(14);
 await page.locator('#cageEnabled').check();
 await expect(page.locator('#cageKind')).toHaveValue('cylindrical_window');
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(15);
 expect(requests.at(-1).cage.kind).toBe('cylindrical_window');
 await page.locator('#bearingType').selectOption('rolling.angular_contact_ball');
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(0);
 await expect(page.locator('#param-contact_angle_deg')).toHaveValue('25');
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(13);
 expect(requests.at(-1).parameters.contact_angle_deg).toBe(25);
 expect(requests.at(-1).parameters.inner_shoulder_right_d_mm).toBe(47);
 await page.locator('#cageEnabled').check();
 await expect(page.locator('#cageKind')).toHaveValue('straight_pocket');
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(14);
 expect(requests.at(-1).cage.kind).toBe('straight_pocket');
 await page.locator('#resetParams').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(0);
 await page.locator('#bearingType').selectOption('rolling.deep_groove_ball');
 await expect(page.locator('#cagePanel')).toBeVisible();
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(14);
 expect(requests.find(r=>r.bearing_type==='rolling.deep_groove_ball').cage?.kind).toBe('simplified_annular');
 await page.locator('#cageKind').selectOption('stamping_double_half');
 await expect(page.locator('#cage-rivet_head_d_mm')).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(0);
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(26);
 const stamped=await page.evaluate(()=>window.rollingViewerSnapshot());
 expect(stamped.instances.filter(p=>p.id.startsWith('rivet_'))).toHaveLength(11);
 expect(stamped.instances.filter(p=>p.id.startsWith('cage_'))).toHaveLength(2);
 expect(requests.at(-1).cage.kind).toBe('stamping_double_half');
 await page.locator('#explode').fill('60');
 const exploded=await page.evaluate(()=>window.rollingViewerSnapshot());
 expect(exploded.instances.find(p=>p.id==='cage_upper').position[2]).toBeGreaterThan(0);
 expect(exploded.instances.find(p=>p.id==='cage_lower').position[2]).toBeLessThan(0);
 await page.locator('#cageEnabled').uncheck();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(0);
 await page.locator('#generate').click();
 await expect.poll(()=>page.evaluate(()=>window.rollingViewerSnapshot().instances.length)).toBe(13);
 expect(requests.at(-1).cage).toBeUndefined();
 expect(errors).toEqual([]);
});

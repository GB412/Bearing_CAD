import test from 'node:test';
import assert from 'node:assert/strict';
import {bearingForms,cageFields,cageForms,cageChoices,defaultCageEnabled,requestFromFields,validateArtifact,buildAssemblyIndex,apiMessage} from './rolling_manifest.js';

const values=kind=>Object.fromEntries(bearingForms[kind].fields.map(([key,,value])=>[key,String(value)]));
const deep='rolling.deep_groove_ball', cylindrical='rolling.cylindrical_roller', angular='rolling.angular_contact_ball';
const def=()=>({status:'GEOMETRY_VALIDATED',geometry_unit:'mm',request_hash:'a'.repeat(64),parts:[{id:'inner_ring',role:'inner_ring'},{id:'ball',role:'rolling_element'}],
 instances:[{id:'inner_ring',part_id:'inner_ring',translation_mm:[0,0,0]},{id:'ball_001',part_id:'ball',translation_mm:[12,0,0]},{id:'ball_002',part_id:'ball',translation_mm:[0,12,0]}],
 files:{'ball.stl':{sha256:'x',size_bytes:100}}});
test('all three UI fixtures translate into explicit valid shaped requests',()=>{
 assert.deepEqual(Object.keys(bearingForms),[deep,cylindrical,angular]);
 const a=requestFromFields(values(deep),Object.fromEntries(cageFields.map(([k,,v])=>[k,String(v)])),deep);
 assert.equal(a.bearing_type,deep);
 assert.equal(a.parameters.ball_count,11);
 assert.equal(a.cage.kind,'simplified_annular');
 const b=requestFromFields(values(cylindrical),null,cylindrical);
 assert.equal(b.bearing_type,cylindrical);
 assert.equal(b.parameters.roller_count,11);
 assert.equal(b.parameters.configuration,'NU');
 assert.equal(b.cage,undefined);
 assert.equal(b.parameters.radial_clearance_mm,0.05);
 const c=requestFromFields(values(angular),null,angular);
 assert.equal(c.bearing_type,angular);
 assert.equal(c.parameters.contact_angle_deg,25);
 assert.equal(c.parameters.inner_shoulder_left_d_mm,49);
 assert.equal(c.cage,undefined);
 for(const request of [a,b,c]){
  assert.equal(request.geometry_strategy,'explicit');
  assert.equal(request.schema_version,'bearing-cad.request.v1');
  assert.equal(request.unit,'mm');
  assert.equal(request.detail_level,'functional');
 }
});
test('cylinder configurations are constrained and numeric fields are validated',()=>{
 for(const configuration of ['N','NU','NJ','NF','NUP']){
  const raw=values(cylindrical);raw.configuration=configuration;
  assert.equal(requestFromFields(raw,null,cylindrical).parameters.configuration,configuration);
 }
 const bad=values(cylindrical);bad.configuration='UNKNOWN';
 assert.throws(()=>requestFromFields(bad,null,cylindrical),/构型/);
 assert.throws(()=>requestFromFields({ ...values(cylindrical),roller_count:'2.4'},null,cylindrical));
 assert.throws(()=>requestFromFields({ ...values(cylindrical),rib_width_mm:'Infinity'},null,cylindrical));
 assert.throws(()=>requestFromFields({ ...values(cylindrical),rib_width_mm:' '},null,cylindrical));
 assert.throws(()=>requestFromFields(values(cylindrical),{},cylindrical),/保持架/);
 assert.throws(()=>requestFromFields(values(angular),{},angular),/保持架/);
 assert.throws(()=>requestFromFields(values(deep),null,'rolling.unknown'),/未支持/);
});
test('prototype STL is expanded to unique instances',()=>{
 const parts=buildAssemblyIndex(def());
 assert.equal(parts.length,3);
 assert.deepEqual(parts.slice(1).map(p=>p.translation_mm),[[12,0,0],[0,12,0]]);
 assert.equal(parts[2].role,'rolling_element');
});
test('invalid and duplicate IDs, transforms are rejected',()=>{
 const x=def();x.instances[1].id=x.instances[0].id;assert.throws(()=>buildAssemblyIndex(x));
 const y=def();y.instances[0].translation_mm[2]=NaN;assert.throws(()=>buildAssemblyIndex(y));
 const z=def();z.parts[1].id='../escape';assert.throws(()=>buildAssemblyIndex(z));
});
test('manifest download URLs must remain local and registered',()=>{
 const m=def(),url='/api/v2/cad/artifacts/'+'a'.repeat(32)+'/files/ball.stl';
 assert.equal(validateArtifact({manifest:m,file_urls:{'ball.stl':url}}).manifest,m);
 assert.throws(()=>validateArtifact({manifest:m,file_urls:{'ball.stl':'https://evil.example/file'}}));
 assert.throws(()=>validateArtifact({manifest:m,file_urls:{'evil.stl':url}}));
 assert.equal(apiMessage({error:{message:'Not supported'}},422),'Not supported');
});

test('all four geometry cage modes match their explicit backend parameter contract',()=>{
 const fixture=kind=>Object.fromEntries(cageForms[kind].fields.map(([name,,val])=>[name,String(val)]));
 const table=[
  [deep,'simplified_annular',5],
  [deep,'stamping_double_half',9],
  [cylindrical,'cylindrical_window',5],
  [angular,'straight_pocket',5]
 ];
 for(const [type,kind,expected] of table){
  const result=requestFromFields(values(type),{kind,...fixture(kind)},type);
  assert.equal(result.cage.kind,kind);
  assert.equal(Object.keys(result.cage).length,expected);
  assert.equal(result.cage.inner_d_mm,Number(fixture(kind).inner_d_mm));
  assert.ok(result.cage.outside_d_mm>result.cage.inner_d_mm);
  assert.ok(cageChoices[type].includes(kind));
 }
 const stamped=requestFromFields(values(deep),{kind:'stamping_double_half',...fixture('stamping_double_half')},deep);
 assert.equal(stamped.cage.rivet_shaft_d_mm,1);
 assert.equal(stamped.cage.board_thickness_mm,.7);
 assert.deepEqual([defaultCageEnabled[deep],defaultCageEnabled[cylindrical],defaultCageEnabled[angular]],[true,false,false]);
});
test('unsupported and incomplete cages fail rather than silently changing geometry',()=>{
 const fixture=kind=>Object.fromEntries(cageForms[kind].fields.map(([name,,val])=>[name,String(val)]));
 assert.throws(()=>requestFromFields(values(cylindrical),{kind:'stamping_double_half',...fixture('stamping_double_half')},cylindrical),/保持架/);
 assert.throws(()=>requestFromFields(values(angular),{kind:'cylindrical_window',...fixture('cylindrical_window')},angular),/保持架/);
 assert.throws(()=>requestFromFields(values(deep),{kind:'stamping_double_half',...fixture('simplified_annular')},deep),/board_thickness_mm/);
 assert.throws(()=>requestFromFields(values(deep),{kind:'simplified_annular',...fixture('simplified_annular'),secret:'8'},deep),/保持架参数/);
 assert.throws(()=>requestFromFields(values(cylindrical),{kind:'cylindrical_window',...fixture('cylindrical_window'),inner_d_mm:'-5'},cylindrical),/无效/);
 assert.throws(()=>requestFromFields(values(angular),{kind:'straight_pocket',...fixture('straight_pocket'),width_mm:'Infinity'},angular),/无效/);
 assert.equal(requestFromFields(values(cylindrical),null,cylindrical).cage,undefined);
});

test('Z rotation is preserved for STL instances and legacy manifest defaults to zero',()=>{
 const legacy=def();
 assert.ok(buildAssemblyIndex(legacy).every(p=>p.rotation_about_z_deg===0));
 legacy.instances[1].rotation_about_z_deg=90;
 assert.equal(buildAssemblyIndex(legacy)[1].rotation_about_z_deg,90);
 legacy.instances[1].rotation_about_z_deg=Infinity;
 assert.throws(()=>buildAssemblyIndex(legacy),/旋转/);
 legacy.instances[1].rotation_about_z_deg='90';
 assert.throws(()=>buildAssemblyIndex(legacy),/旋转/);
});

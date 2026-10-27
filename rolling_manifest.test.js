import test from 'node:test';
import assert from 'node:assert/strict';
import {bearingForms,cageFields,requestFromFields,validateArtifact,buildAssemblyIndex,apiMessage} from './rolling_manifest.js';

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

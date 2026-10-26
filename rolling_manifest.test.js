import test from 'node:test';
import assert from 'node:assert/strict';
import {requestFromFields,validateArtifact,buildAssemblyIndex,apiMessage} from './rolling_manifest.js';
const def=()=>({status:'GEOMETRY_VALIDATED',geometry_unit:'mm',request_hash:'a'.repeat(64),parts:[{id:'inner_ring',role:'inner_ring'},{id:'ball',role:'rolling_element'}],
 instances:[{id:'inner_ring',part_id:'inner_ring',translation_mm:[0,0,0]},{id:'ball_001',part_id:'ball',translation_mm:[12,0,0]},{id:'ball_002',part_id:'ball',translation_mm:[0,12,0]}],
 files:{'ball.stl':{sha256:'x',size_bytes:100}}});
test('request maps explicit dimensions and no hidden CAD algorithm',()=>{
 const result=requestFromFields({bore_d_mm:'40',ball_count:'11'},null);
 assert.equal(result.parameters.ball_count,11);
 assert.equal(result.cage,undefined);
 assert.equal(result.geometry_strategy,'explicit');
 assert.throws(()=>requestFromFields({ball_count:'1.2'},null));
 assert.throws(()=>requestFromFields({width_mm:'Infinity'},null));
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
 const m=def();const url='/api/v2/cad/artifacts/'+'a'.repeat(32)+'/files/ball.stl';
 assert.equal(validateArtifact({manifest:m,file_urls:{'ball.stl':url}}).manifest,m);
 assert.throws(()=>validateArtifact({manifest:m,file_urls:{'ball.stl':'https://evil.example/file'}}));
 assert.throws(()=>validateArtifact({manifest:m,file_urls:{'evil.stl':url}}));
 assert.equal(apiMessage({error:{message:'Not supported'}},422),'Not supported');
});

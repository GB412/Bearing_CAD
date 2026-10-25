import test from 'node:test';
import assert from 'node:assert/strict';
import {check,defaults,dimensions,dxf} from './geometry.js';

test('geometry precision and finite numbers',()=>{
 assert.equal(check({...defaults,radial_clearance_mm:0.00549})!==null,true);
 assert.equal(check({...defaults,radial_clearance_mm:0.005}),null);
 assert.equal(check({...defaults,shaft_d_mm:NaN})!==null,true);
 assert.equal(check({...defaults,shaft_d_mm:'50'})!==null,true);
});
test('display range is enforced by canonical browser schema',()=>{
 assert.notEqual(check({...defaults,bush_od_mm:170,housing_od_mm:190}),null);
 assert.notEqual(check({...defaults,housing_od_mm:201}),null);
});
test('derived bore matches radial clearance',()=>{
 assert.equal(dimensions(defaults).bore,50.1);
 assert.equal(dimensions(defaults).shaftLength,78);
});
test('DXF has explicit table handles, mm units and expected geometry',()=>{
 const s=dxf(defaults);
 assert.match(s,/9\n\$INSUNITS\n70\n4/);
 assert.match(s,/2\nLTYPE\n5\n10\n70/);
 assert.match(s,/2\nLAYER\n5\n11\n70/);
 assert.match(s,/2\nHOUSING/);
 assert.match(s,/2\nBUSHING/);
 assert.match(s,/50\.1/);
});

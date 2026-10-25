import test from 'node:test';
import assert from 'node:assert/strict';
import {defaults} from './geometry.js';
import {validateExactRequest as validate} from './cad03_geometry.js';
const base={...defaults};
test('supports legacy six input fields',()=>assert.equal(validate(base),null));
test('supports paired optional oil hole / annular groove',()=>assert.equal(validate({...base,oil_feed_hole_d_mm:5,annular_groove_width_mm:6,annular_groove_depth_mm:1.2}),null));
test('rejects incomplete and unsafe geometry',()=>{
 for(const p of [
  {...base,annular_groove_width_mm:6},
  {...base,annular_groove_width_mm:6,annular_groove_depth_mm:1},
  {...base,oil_feed_hole_d_mm:0},
  {...base,oil_feed_hole_d_mm:5,annular_groove_width_mm:6,annular_groove_depth_mm:20},
  {...base,oil_feed_hole_d_mm:5.00001},
  {...base,oil_feed_hole_d_mm:Infinity},
 ])assert.notEqual(validate(p),null);
});

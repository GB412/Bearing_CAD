import {check} from './geometry.js';
export function validateExactRequest(p){
 const e=check(p);if(e)return e;
 const keys=['oil_feed_hole_d_mm','annular_groove_width_mm','annular_groove_depth_mm'];
 for(const key of keys)if(Object.hasOwn(p,key)){
  const v=p[key];
  if(typeof v!=='number'||!Number.isFinite(v)||v<=0||Math.abs(v*1000-Math.round(v*1000))>1e-7)return key+' 必须是正数（精度 0.001 mm）';
 }
 const has=k=>Object.hasOwn(p,k);
 if(has(keys[1])!==has(keys[2]))return '槽宽与槽深必须同时填写';
 if(has(keys[1])){
  if(!has(keys[0]))return '此演示的环槽需要供油孔';
  if(p.annular_groove_width_mm>=p.length_mm-4)return '油槽轴向两端保留不足';
  if(p.annular_groove_depth_mm>=(p.bush_od_mm-p.shaft_d_mm-2*p.radial_clearance_mm)/2-2)return '油槽径向壁厚不足';
 }
 if(has(keys[0])&&(p.oil_feed_hole_d_mm>=Math.min(p.length_mm-4,p.housing_length_mm-4)||p.oil_feed_hole_d_mm>=p.bush_od_mm/2))return '供油孔过大';
 return null;
}
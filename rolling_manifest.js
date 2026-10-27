/** UI fixtures and strict request/manifest translation; OCCT remains the geometry source. */
const common = [
  ['bore_d_mm','内径 d',40],
  ['outside_d_mm','外径 D',68],
  ['width_mm','宽度 B',15]
];
export const bearingForms = Object.freeze({
  'rolling.deep_groove_ball': {
    label: '单列深沟球轴承',
    fields: [...common, ['ball_d_mm','钢球直径',8], ['pitch_d_mm','节圆直径',54],
      ['ball_count','钢球数量',11], ['inner_groove_radius_mm','内沟曲率半径',4.3],
      ['outer_groove_radius_mm','外沟曲率半径',4.5],
      ['inner_shoulder_d_mm','内圈肩部直径',47.2], ['outer_shoulder_d_mm','外圈肩部直径',60.8]],
    hasCage: true
  },
  'rolling.cylindrical_roller': {
    label: '单列圆柱滚子轴承',
    fields: [...common.map(([name,label,value])=>[name,label,name==='width_mm'?18:value]),
      ['roller_d_mm','滚子直径',8], ['roller_length_mm','滚子长度',12],
      ['pitch_d_mm','节圆直径',54], ['roller_count','滚子数量',11],
      ['configuration','挡边构型','NU',['N','NU','NJ','NF','NUP']],
      ['radial_clearance_mm','径向几何净距',.05],
      ['axial_clearance_mm','端部轴向净距',.4],
      ['rib_width_mm','挡边宽度',2],
      ['inner_rib_tip_d_mm','内挡边顶径',52],
      ['outer_rib_tip_d_mm','外挡边顶径',56]],
    hasCage: false
  },
  'rolling.angular_contact_ball': {
    label: '单列角接触球轴承',
    fields: [...common, ['ball_d_mm','钢球直径',8], ['pitch_d_mm','节圆直径',54],
      ['ball_count','钢球数量',11], ['inner_groove_radius_mm','内沟曲率半径',4.3],
      ['outer_groove_radius_mm','外沟曲率半径',4.5],
      ['contact_angle_deg','名义接触角 (°)',25],
      ['inner_shoulder_left_d_mm','内圈左肩直径',49],
      ['inner_shoulder_right_d_mm','内圈右肩直径',47],
      ['outer_shoulder_left_d_mm','外圈左肩直径',61],
      ['outer_shoulder_right_d_mm','外圈右肩直径',59]],
    hasCage: false
  }
});
export const cageFields = Object.freeze([
  ['inner_d_mm','保持架内径',48],['outside_d_mm','保持架外径',60],
  ['width_mm','保持架宽度',11],['pocket_clearance_mm','球兜间隙',.25]
]);
function numeric(text, key, integer=false) {
  if (String(text).trim()==='') throw Error('缺少参数 '+key);
  const val=Number(text);
  if (!Number.isFinite(val)||val<=0||(integer&&!Number.isInteger(val)))
    throw Error('尺寸或数量无效：'+key);
  return val;
}
export function requestFromFields(values, cage, bearingType='rolling.deep_groove_ball') {
  const form=bearingForms[bearingType];
  if (!form) throw Error('未支持的轴承类型：'+bearingType);
  if (cage!==null && !form.hasCage) throw Error('当前轴承类型尚无保持架模型');
  const params={};
  for(const [key,, ,options] of form.fields) {
    if (options) {
      if (!options.includes(values[key])) throw Error('不支持的构型：'+String(values[key]));
      params[key]=values[key];
    } else {
      params[key]=numeric(values[key],key,key.endsWith('_count'));
    }
  }
  const result={schema_version:'bearing-cad.request.v1',bearing_type:bearingType,
    unit:'mm',detail_level:'functional',geometry_strategy:'explicit',parameters:params};
  if(cage!==null){
    const dimensions={};
    for(const [key] of cageFields) dimensions[key]=numeric(cage[key],key);
    result.cage={kind:'simplified_annular',...dimensions};
  }
  return result;
}
const PART=/^[a-zA-Z0-9_-]+$/;
const FILE=/^[a-zA-Z0-9_.-]+$/;
function object(x){return x!==null&&typeof x==='object'&&!Array.isArray(x);}
export function validateArtifact(data){
 if(!object(data)||!object(data.manifest)||!object(data.file_urls))throw Error('成果清单格式无效');
 const {manifest,file_urls}=data;
 if(manifest.status!=='GEOMETRY_VALIDATED'||manifest.geometry_unit!=='mm'||!Array.isArray(manifest.parts)||!Array.isArray(manifest.instances))
  throw Error('成果尚未通过几何检查或格式不正确');
 if(!/^[0-9a-f]{64}$/.test(manifest.request_hash||''))throw Error('参数快照哈希无效');
 if(!object(manifest.files))throw Error('缺少文件校验清单');
 for(const [name,url] of Object.entries(file_urls)){
  if(!FILE.test(name)||!Object.hasOwn(manifest.files,name)||!object(manifest.files[name]))throw Error('未登记的文件：'+name);
  if(typeof url!=='string'||!/^\/api\/v2\/cad\/artifacts\/[a-f0-9]{32}\/files\/[a-zA-Z0-9_.-]+$/.test(url)||!url.endsWith('/'+name))
   throw Error('不安全的下载地址：'+name);
 }
 return {manifest,file_urls};
}
export function buildAssemblyIndex(manifest){
 if(!Array.isArray(manifest.parts)||!Array.isArray(manifest.instances))throw Error('缺少零件定义');
 const defs=new Map();
 for(const part of manifest.parts){
  if(!object(part)||!PART.test(part.id||'')||defs.has(part.id))throw Error('零件定义 ID 无效或重复');
  defs.set(part.id,part.role);
 }
 const used=new Set();
 const out=[];
 for(const inst of manifest.instances){
  if(!object(inst)||!PART.test(inst.id||'')||used.has(inst.id)||!defs.has(inst.part_id))throw Error('装配实例 ID 无效');
  if(!Array.isArray(inst.translation_mm)||inst.translation_mm.length!==3||!inst.translation_mm.every(n=>typeof n==='number'&&Number.isFinite(n)))
   throw Error('装配变换无效：'+inst.id);
  used.add(inst.id);out.push({id:inst.id,part_id:inst.part_id,role:defs.get(inst.part_id),translation_mm:inst.translation_mm});
 }
 if(out.length===0||out.length>1000)throw Error('装配实例数超出范围');
 return out;
}
export function apiMessage(payload,status) {
 if(object(payload?.error)&&typeof payload.error.message==='string')return payload.error.message;
 return 'HTTP '+status;
}

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
      ['axial_clearance_mm','端部最小要求净距',.4],
      ['rib_width_mm','挡边宽度',2],
      ['inner_rib_tip_d_mm','内挡边顶径',52],
      ['outer_rib_tip_d_mm','外挡边顶径',56]],
    hasCage: true
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
    hasCage: true
  }
});
export const cageFields = Object.freeze([
  ['inner_d_mm','保持架内径',48],['outside_d_mm','保持架外径',60],
  ['width_mm','保持架宽度',11],['pocket_clearance_mm','球兜间隙',.25]
]);
// Fixtures below are geometry regression cases, not bearing catalogue dimensions.
// The kind and exact numeric fields mirror contracts.py; nothing is inferred.
export const cageForms = Object.freeze({
  simplified_annular: {
    label:'简化环缘保持架（预览级）',
    fields:cageFields
  },
  stamping_double_half: {
    label:'双半笼 + 球兜 + 铆钉',
    fields:[
      ['inner_d_mm','保持架内径',48],['outside_d_mm','保持架外径',60],
      ['width_mm','保持架总宽度',11.5],['pocket_clearance_mm','球兜净距',.15],
      ['board_thickness_mm','球兜外最小轴向余料约束',.7],['rivet_shaft_d_mm','铆钉杆径',1],
      ['rivet_head_d_mm','铆钉头直径',1.6],
      ['rivet_hole_clearance_mm','铆钉孔净距',.05]
    ]
  },
  cylindrical_window: {
    label:'圆柱滚子轴向窗孔保持架',
    fields:[
      ['inner_d_mm','保持架内径',52.6],['outside_d_mm','保持架外径',55.4],
      ['width_mm','保持架宽度',16],['pocket_clearance_mm','滚子窗孔净距',.15]
    ]
  },
  straight_pocket: {
    label:'角接触球径向窗孔保持架',
    fields:[
      ['inner_d_mm','保持架内径',51],['outside_d_mm','保持架外径',57],
      ['width_mm','保持架宽度',11],['pocket_clearance_mm','球兜净距',.15]
    ]
  }
});
export const cageChoices = Object.freeze({
  'rolling.deep_groove_ball':['simplified_annular','stamping_double_half'],
  'rolling.cylindrical_roller':['cylindrical_window'],
  'rolling.angular_contact_ball':['straight_pocket']
});
// Keep existing deep-groove simplified cage as the initial page default.
// Previously unsupported types default to *no cage* until explicitly enabled.
export const defaultCageEnabled = Object.freeze({
  'rolling.deep_groove_ball':true,
  'rolling.cylindrical_roller':false,
  'rolling.angular_contact_ball':false
});
// One UI resource budget shared with contracts.py and api.py.
// These numbers bound interactive CAD execution, not bearing design standards.
export const MAX_ROLLERS = 64;
export const MAX_DIMENSION_MM = 1000;
const NONNEGATIVE = new Set(['radial_clearance_mm','axial_clearance_mm']);
export class ParameterInputError extends Error {
 constructor(message,fieldPath){super(message);this.name='ParameterInputError';this.fieldPath=fieldPath;}
}
function numeric(text,key,integer=false,scope='parameters'){
 const path='/'+scope+'/'+key;
 if(String(text??'').trim()==='')throw new ParameterInputError('请填写 '+key,path);
 const value=Number(text);
 if(!Number.isFinite(value)||(integer&&!Number.isInteger(value))||
    value<0||(value===0&&!NONNEGATIVE.has(key))||
    value>(integer?MAX_ROLLERS:MAX_DIMENSION_MM))
   throw new ParameterInputError('尺寸或数量无效：'+key,path);
 return value;
}
export function scaleGeometryFields(values,cage,bearingType,targetBore){
 const form=bearingForms[bearingType];
 if(!form)throw new ParameterInputError('未支持的轴承类型','/bearing_type');
 const current=numeric(values.bore_d_mm,'bore_d_mm');
 const target=numeric(targetBore,'bore_d_mm');
 const factor=target/current;
 const scaled={...values};
 const decimal=value=>String(Number(value.toPrecision(12)));
 for(const [key,, ,choices] of form.fields){
  if(choices||key.endsWith('_count')||key==='contact_angle_deg')continue;
  scaled[key]=decimal(numeric(values[key],key)*factor);
 }
 const scaledCage=cage===null?null:{...cage};
 if(scaledCage){
  const definition=cageForms[scaledCage.kind];
  if(!definition)throw new ParameterInputError('保持架结构无效','/cage/kind');
  for(const [key] of definition.fields){
   scaledCage[key]=decimal(numeric(cage[key],key,false,'cage')*factor);
  }
 }
 // Do not silently clamp: scaling outside the runtime budget must fail.
 requestFromFields(scaled,scaledCage,bearingType);
 return {values:scaled,cage:scaledCage};
}

// Fast, conservative checks only. The Python/OCCT builder remains authoritative
// for all remaining contact, topology and interference validations.
export function geometryIssues(request){
 const p=request.parameters, c=request.cage, out=[];
 const add=(fieldPath,message,related=[])=>out.push({fieldPath,message,related});
 const d=p.bore_d_mm,D=p.outside_d_mm,P=p.pitch_d_mm,B=p.width_mm;
 if(d>=D)add('/parameters/bore_d_mm','轴承内径必须小于外径。',['/parameters/outside_d_mm']);
 if(!(d<P&&P<D))add('/parameters/pitch_d_mm','节圆直径必须介于内径和外径之间。',['/parameters/bore_d_mm','/parameters/outside_d_mm']);
 const count=p.ball_count??p.roller_count;
 const body=p.ball_d_mm??p.roller_d_mm;
 const kind=request.bearing_type;
 if(count>1&&P*Math.sin(Math.PI/count)<=body)
  add('/parameters/'+(kind==='rolling.cylindrical_roller'?'roller_count':'ball_count'),'滚动体数量过多，相邻滚动体会重叠。',['/parameters/pitch_d_mm']);
 if(kind==='rolling.deep_groove_ball'){
  const i=p.inner_shoulder_d_mm,o=p.outer_shoulder_d_mm;
  const ri=p.inner_groove_radius_mm,ro=p.outer_groove_radius_mm;
  if(!(d<i&&i<P&&P<o&&o<D))
   add('/parameters/bore_d_mm','内径、内肩、节圆、外肩和外径应依次增大。',['/parameters/inner_shoulder_d_mm','/parameters/pitch_d_mm','/parameters/outer_shoulder_d_mm']);
  if(ri<=body/2||ro<=body/2)
   add('/parameters/inner_groove_radius_mm','内外沟道曲率半径都必须大于钢球半径。',['/parameters/outer_groove_radius_mm']);
  if(P/2-ri<=d/2)add('/parameters/bore_d_mm','内孔已侵入内沟道切削区域，请同时调整节圆和沟道尺寸。',['/parameters/pitch_d_mm','/parameters/inner_groove_radius_mm']);
  if(P/2+ro>=D/2)add('/parameters/outside_d_mm','外沟道切削区域超出了外圈直径。',['/parameters/pitch_d_mm']);
 }else if(kind==='rolling.angular_contact_ball'){
  const ir=p.inner_shoulder_right_d_mm,il=p.inner_shoulder_left_d_mm;
  const or=p.outer_shoulder_right_d_mm,ol=p.outer_shoulder_left_d_mm;
  if(!(d<ir&&ir<il&&il<P&&P<or&&or<ol&&ol<D))
   add('/parameters/bore_d_mm','尺寸应满足：内径 < 内圈右肩 < 内圈左肩 < 节圆 < 外圈右肩 < 外圈左肩 < 外径。',['/parameters/inner_shoulder_right_d_mm','/parameters/inner_shoulder_left_d_mm','/parameters/pitch_d_mm','/parameters/outer_shoulder_right_d_mm','/parameters/outer_shoulder_left_d_mm']);
  const r=body/2,ri=p.inner_groove_radius_mm,ro=p.outer_groove_radius_mm;
  if(ri<=r||ro<=r)
   add('/parameters/inner_groove_radius_mm','内外沟道曲率半径都必须大于钢球半径。',['/parameters/outer_groove_radius_mm']);
  const angle=p.contact_angle_deg;
  if(!(angle>0&&angle<90))add('/parameters/contact_angle_deg','接触角必须大于 0° 且小于 90°。');
  if(ri>r&&ro>r&&angle>0&&angle<90){
   const a=angle*Math.PI/180;
   const innerR=P/2+(ri-r)*Math.cos(a);
   const outerR=P/2-(ro-r)*Math.cos(a);
   if(innerR-ri<=d/2)
    add('/parameters/bore_d_mm','内孔已侵入角接触内沟道，请同步调整节圆、沟曲率或内径。',['/parameters/pitch_d_mm','/parameters/inner_groove_radius_mm']);
   if(outerR+ro>=D/2)
    add('/parameters/outside_d_mm','角接触外沟道切削区域超出了外径。');
   if(Math.max(Math.abs((ri-r)*Math.sin(a))+ri,Math.abs((ro-r)*Math.sin(a))+ro)>=B/2)
    add('/parameters/width_mm','轴承宽度不足，沟道切削区域穿过端面。');
  }
 }else if(kind==='rolling.cylindrical_roller'){
  const rollR=p.roller_d_mm/2,gap=p.radial_clearance_mm;
  const inner=P/2-rollR-gap,outer=P/2+rollR+gap;
  if(!(d/2<inner&&inner<p.inner_rib_tip_d_mm/2&&
       p.inner_rib_tip_d_mm<p.outer_rib_tip_d_mm&&
       p.outer_rib_tip_d_mm/2<outer&&outer<D/2))
   add('/parameters/bore_d_mm','内孔、内滚道、挡边、外滚道和外径的径向顺序不成立。',['/parameters/pitch_d_mm','/parameters/inner_rib_tip_d_mm','/parameters/outer_rib_tip_d_mm']);
  if(!(p.roller_length_mm/2+p.axial_clearance_mm<B/2-p.rib_width_mm))
   add('/parameters/width_mm','轴承宽度不足以容纳滚子、轴向净距和挡边。',['/parameters/roller_length_mm','/parameters/axial_clearance_mm','/parameters/rib_width_mm']);
 }
 if(c){
  if(c.width_mm>B)add('/cage/width_mm','保持架总宽度不能大于轴承宽度。',['/parameters/width_mm']);
  if(!(c.inner_d_mm<c.outside_d_mm))add('/cage/inner_d_mm','保持架内径必须小于外径。',['/cage/outside_d_mm']);
  if(kind==='rolling.deep_groove_ball'){
   if(!(p.inner_shoulder_d_mm<c.inner_d_mm&&c.inner_d_mm<P&&P<c.outside_d_mm&&c.outside_d_mm<p.outer_shoulder_d_mm))
    add('/cage/inner_d_mm','保持架必须位于内外圈肩部之间且跨过节圆。',['/cage/outside_d_mm']);
  }else if(kind==='rolling.angular_contact_ball'){
   if(!(Math.max(p.inner_shoulder_left_d_mm,p.inner_shoulder_right_d_mm)<c.inner_d_mm&&c.inner_d_mm<P&&P<c.outside_d_mm&&c.outside_d_mm<Math.min(p.outer_shoulder_left_d_mm,p.outer_shoulder_right_d_mm)))
    add('/cage/inner_d_mm','保持架必须位于角接触球内外肩部之间且跨过节圆。',['/cage/outside_d_mm']);
  }else if(kind==='rolling.cylindrical_roller'){
   if(!(p.inner_rib_tip_d_mm<c.inner_d_mm&&c.inner_d_mm<P&&P<c.outside_d_mm&&c.outside_d_mm<p.outer_rib_tip_d_mm))
    add('/cage/inner_d_mm','保持架必须位于滚子挡边之间且跨过节圆。',['/cage/outside_d_mm']);
  }
 }
 return out;
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
      if(key==='contact_angle_deg'&&!(params[key]>0&&params[key]<90))throw new ParameterInputError('接触角必须介于 0° 和 90° 之间','/parameters/contact_angle_deg');
    }
  }
  const result={schema_version:'bearing-cad.request.v1',bearing_type:bearingType,
    unit:'mm',detail_level:'functional',geometry_strategy:'explicit',parameters:params};
  if(cage!==null){
    // Only old deep-groove callers may omit the kind; other types must
    // explicitly state it. This preserves older simplified cage requests.
    const kind=cage.kind??(bearingType==='rolling.deep_groove_ball'?'simplified_annular':null);
    if(!cageChoices[bearingType]?.includes(kind))throw Error('不支持的保持架类型：'+String(kind));
    const spec=cageForms[kind];
    const expected=new Set(['kind',...spec.fields.map(([key])=>key)]);
    for(const key of Object.keys(cage))if(!expected.has(key))throw Error('不支持的保持架参数：'+key);
    const dimensions={};
    for(const [key] of spec.fields)dimensions[key]=numeric(cage[key],key,false,'cage');
    if(dimensions.inner_d_mm>=dimensions.outside_d_mm)throw Error('保持架内径应小于外径');
    result.cage={kind,...dimensions};
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
  const rotation=inst.rotation_about_z_deg??0;
  if(typeof rotation!=='number'||!Number.isFinite(rotation))
   throw Error('实例 Z 轴旋转无效：'+inst.id);
  used.add(inst.id);out.push({
   id:inst.id,part_id:inst.part_id,role:defs.get(inst.part_id),
   translation_mm:inst.translation_mm,rotation_about_z_deg:rotation
  });
 }
 if(out.length===0||out.length>1000)throw Error('装配实例数超出范围');
 return out;
}
export function apiMessage(payload,status) {
 if(object(payload?.error)&&typeof payload.error.message==='string')return payload.error.message;
 return 'HTTP '+status;
}

export function describeCadError(payload,status){
 const text=apiMessage(payload,status);
 const path=payload?.error?.field_path??'';
 const messages=[
  [/^Expected bore < inner right < inner left < pitch < outer right < outer left < outside/,
   '内径、内圈右肩、内圈左肩、节圆、外圈右肩、外圈左肩及外径必须依次增大。请同时调整相关尺寸。'],
  [/^Expected d < inner shoulder < pitch < outer shoulder < D/,
   '尺寸应满足：内径 < 内圈肩部 < 节圆 < 外圈肩部 < 外径。'],
  [/Raceway cuts through (?:the )?bore|Raceway cuts through bore|Raceway cutter crosses|Raceway cuts through bore or outside envelope/,
   '沟道切削区域穿过内孔或外圈外表面，请检查节圆、内外径和沟道曲率。'],
  [/Raceway cutter crosses the axial end face/,
   '沟道切削区域超出轴承宽度，请调整轴向宽度或沟道。'],
  [/Invalid radial raceway\/flange order/,
   '内外滚道、挡边和内外径的径向尺寸顺序不成立。'],
  [/Cage width cannot exceed bearing axial width|Cage exceeds bearing width|Stamped assembly exceeds bearing width/,
   '保持架宽度不能大于轴承宽度。'],
  [/Adjacent balls overlap|Adjacent rollers overlap/,
   '滚动体数量过多或直径过大，相邻滚动体发生重叠。'],
  [/Exceeds local geometry budget|resource budget exceeded|numeric budget exceeded|Exceeds CAD builder instance budget/i,
   '输入超出本地 CAD 服务的计算资源限制，请缩小尺寸或减少滚动体数量。'],
  [/No axial end clearance/,
   '滚子、轴向净距和挡边的宽度之和超出轴承宽度。']
 ];
 return {
  message:messages.find(([pattern])=>pattern.test(text))?.[1]??text,
  fieldPath:typeof path==='string'?path:''
 };
}

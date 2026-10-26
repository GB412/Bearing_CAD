/** Pure contract helpers for manifest-driven rendering. Do not synthesize CAD geometry. */
export function requestFromFields(values, cage) {
 const params={};
 for(const [key,text] of Object.entries(values)){
  if(String(text).trim()==='')throw Error('缺少参数 '+key);
  const number=Number(text);
  if(!Number.isFinite(number)||number<=0)throw Error('参数必须是有限正数：'+key);
  if(key==='ball_count'&&!Number.isInteger(number))throw Error('钢球数量必须为整数');
  params[key]=number;
 }
 const result={schema_version:'bearing-cad.request.v1',bearing_type:'rolling.deep_groove_ball',
   unit:'mm',detail_level:'functional',geometry_strategy:'explicit',parameters:params};
 if(cage!==null){
  const dimensions={};
  for(const [key,text] of Object.entries(cage)){
   if(String(text).trim()==='')throw Error('保持架缺少 '+key);
   const n=Number(text);if(!Number.isFinite(n)||n<=0)throw Error('保持架尺寸无效：'+key);
   dimensions[key]=n;
  }
  result.cage={kind:'simplified_annular',...dimensions};
 }
 return result;
}
const TOKEN=/^[a-f0-9]{32}$/;
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

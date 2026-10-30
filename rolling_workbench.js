import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import './rolling_workbench.css';
import {bearingForms, cageForms, cageChoices, defaultCageEnabled, buildAssemblyIndex, validateArtifact, requestFromFields, geometryIssues, scaleGeometryFields, describeCadError, ParameterInputError} from './rolling_manifest.js';

const $ = id => document.getElementById(id);
let fields=bearingForms['rolling.deep_groove_ball'].fields;
let cages=cageForms.simplified_annular.fields;
function renderFields(container, prefix, data) {
 container.replaceChildren();
 for (const [key,label,value,choices] of data) {
  const el=document.createElement('label');el.className='field';el.textContent=label;
  const field=choices?document.createElement('select'):document.createElement('input');
  if(choices){
   for(const option of choices){const item=document.createElement('option');item.value=option;item.textContent=option;field.append(item);}
   field.value=value;
  }else{
   field.type='number';field.step=key.endsWith('_count')?'1':'any';field.value=String(value);
  }
  field.id=prefix+key;field.setAttribute('aria-label',label);
  field.addEventListener(choices?'change':'input',()=>{
   invalidatePreview();showDraftIssues();
  });
  el.append(field);container.append(el);
 }
}
renderFields($('parameters'),'param-',fields);
renderFields($('cageParams'),'cage-',cages);
let active=null, token=0, controller=null, available=false;
let supportedTypes=new Set();
const scene=new THREE.Scene();scene.background=null;
const camera=new THREE.PerspectiveCamera(36,1,.1,5000);
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setClearColor(0xffffff,0);
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=1.18;
renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));
renderer.localClippingEnabled=true;$('viewport').prepend(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
scene.add(new THREE.HemisphereLight('#ffffff','#aabcc5',1.65));
const key=new THREE.DirectionalLight('#ffffff',2.1);key.position.set(2,4,6);scene.add(key);
const fill=new THREE.DirectionalLight('#cad8df',0.9);fill.position.set(-5,-2,-3);scene.add(fill);
const rim=new THREE.DirectionalLight('#ffffff',0.55);rim.position.set(0,-5,4);scene.add(rim);
const clipPlane=new THREE.Plane(new THREE.Vector3(1,0,0),0);
// Materials, legend and part tree share the same palette in CSS.
const partColorVars={
 inner_ring:'--part-inner',outer_ring:'--part-outer',
 rolling_element:'--part-rolling',cage:'--part-cage',
 cage_upper:'--part-cage-upper',cage_lower:'--part-cage-lower',
 loose_rib:'--part-rib',rivet:'--part-rivet'
};
const partLabels={
 inner_ring:'内圈',outer_ring:'外圈',cage:'保持架',
 cage_upper:'上半笼',cage_lower:'下半笼',loose_rib:'活动挡圈'
};
function partColor(partId,role){
 const variable=partColorVars[partId]||partColorVars[role]||'--part-default';
 return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
}
function partLabel(part){
 const id=part.userData.partId;
 if(partLabels[id])return partLabels[id];
 const match=/^(ball|roller|rivet)_(\d+)$/.exec(part.name);
 if(match)return ({ball:'钢球',roller:'滚子',rivet:'铆钉'}[match[1]])+' '+String(Number(match[2])).padStart(2,'0');
 return ({ball:'钢球',roller:'滚子',rivet:'铆钉'}[id])||part.name;
}
const loader=new STLLoader();const entries=[];
function status(msg,error=false){$('status').textContent=msg;$('status').classList.toggle('error',error);}
function dispose() {
 for(const object of entries){scene.remove(object);object.geometry.dispose();object.material.dispose();}
 entries.length=0;active=null;$('parts').replaceChildren();$('downloads').replaceChildren();
 $('partCount').textContent='0 个实例';$('quality').textContent='未验证';$('provenance').textContent='正式工程设计和轴承制造校核需进一步审核。';
 $('modelLabel').textContent='尚未生成模型';$('emptyStage').hidden=false;
 $('drawingPanel').hidden=true;$('drawingPreview').removeAttribute('src');
}
function resetCamera(){
 const bounds=new THREE.Box3();
 for(const part of entries){part.updateMatrixWorld(true);bounds.expandByObject(part);}
 const center=bounds.isEmpty()?new THREE.Vector3():bounds.getCenter(new THREE.Vector3());
 const size=bounds.isEmpty()?90:Math.max(bounds.getSize(new THREE.Vector3()).length(),10);
 controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(size*.9,size*.65,size*.85));
 camera.near=Math.max(.01,size/500);camera.far=size*35;camera.updateProjectionMatrix();controls.update();
}
function resize(){const width=$('viewport').clientWidth;const height=renderer.domElement.parentElement.clientHeight;renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe($('viewport'));resize();
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});
function applyVisualOptions(){
 const opacity=$('transparent').checked?0.43:1;
 const explode=Number($('explode').value)/100;
 for(const object of entries){
  object.material.opacity=opacity;object.material.transparent=opacity<1;
  object.material.depthWrite=opacity===1;
  object.material.clippingPlanes=$('cutaway').checked?[clipPlane]:[];
  object.position.copy(object.userData.base);
  const part=object.userData.partId;
  const direction=object.userData.role==='outer_ring'?1
    :object.userData.role==='inner_ring'?-1
    :part==='cage_lower'?-1.1
    :part==='cage_upper'?1.1
    :part==='rivet'?0
    :object.userData.role==='cage'?0.5
    :object.userData.role==='loose_rib'?1.7:0;
  object.position.z+=explode*15*direction;
  if(object.userData.role==='rolling_element'||part==='rivet')object.position.addScaledVector(object.userData.radial,explode*10);
 }
}
function presentTree(){
 $('parts').replaceChildren();$('partCount').textContent=entries.length+' 个实例';
 for(const part of entries){
  const label=document.createElement('label');label.className='partrow';
  const check=document.createElement('input');check.type='checkbox';check.checked=true;check.setAttribute('aria-label','显示 '+part.name);
  check.addEventListener('change',()=>{part.visible=check.checked;});
  const color=document.createElement('span');
  color.className='swatch';color.style.backgroundColor=part.userData.partColor;
  color.setAttribute('aria-hidden','true');
  const name=document.createElement('span');name.className='part-name';name.textContent=partLabel(part);
  const code=document.createElement('small');code.className='part-code';code.textContent=part.name;
  label.append(check,color,name,code);$('parts').append(label);
 }
}
function selectedType(){return $('bearingType').value;}
function rawDraft(){
 const p={};for(const [key] of fields)p[key]=$('param-'+key).value;
 const c=$('cageEnabled').checked
  ?{kind:$('cageKind').value,...Object.fromEntries(cages.map(([key])=>[key,$('cage-'+key).value]))}
  :null;
 return {values:p,cage:c};
}
function paintIssues(issues){
 document.querySelectorAll('#parameters .field, #cageParams .field')
  .forEach(label=>{
   label.removeAttribute('data-invalid');
   const control=label.querySelector('input,select');
   if(control)control.removeAttribute('aria-invalid');
  });
 const panel=$('validation');
 if(!issues.length){panel.hidden=true;panel.textContent='';return;}
 const first=issues[0];
 panel.hidden=false;
 panel.textContent=first.message+(issues.length>1?'（另有 '+(issues.length-1)+' 项待检查）':'');
 const all=new Set(issues.flatMap(issue=>[issue.fieldPath,...(issue.related??[])]));
 for(const path of all){
  const segments=path?.split('/');
  if(!segments||segments.length!==3)continue;
  const prefix=segments[1]==='cage'?'cage-':'param-';
  const input=$(prefix+segments[2]);
  if(!input)continue;
  input.setAttribute('aria-invalid','true');
  input.closest('.field')?.setAttribute('data-invalid','true');
 }
}
function showDraftIssues(){
 try{
  const draft=rawDraft();
  const request=requestFromFields(draft.values,draft.cage,selectedType());
  const issues=geometryIssues(request);
  paintIssues(issues);
  return issues;
 }catch(error){
  const issue={fieldPath:error.fieldPath??'',message:error.message};
  paintIssues([issue]);
  return [issue];
 }
}
function canGenerate(){return available&&supportedTypes.has(selectedType());}
function updateAvailability(){
 const enabled=canGenerate();$('generate').disabled=!enabled;
 $('connection').textContent=available?'本地 OCCT 引擎在线':'CAD 引擎不可用';
 $('connection').dataset.state=available?'ready':'offline';
 if(available&&!enabled)status('当前 CAD 服务暂不支持所选轴承类型',true);
}
function invalidatePreview(message='输入已改变，请重新生成 CAD'){
 token++;controller?.abort();controller=null;
 dispose();status(message);
 $('generate').disabled=!canGenerate();
}
function configureCageKind(reset=false){
 const types=cageChoices[selectedType()]??[];
 const picker=$('cageKind');
 if(reset||!types.includes(picker.value)){
  picker.replaceChildren();
  for(const kind of types){
   const opt=document.createElement('option');opt.value=kind;
   opt.textContent=cageForms[kind].label;picker.append(opt);
  }
 }
 cages=cageForms[picker.value].fields;
 renderFields($('cageParams'),'cage-',cages);
 $('cageOptions').hidden=!$('cageEnabled').checked;
}
function configureForm(){
 fields=bearingForms[selectedType()].fields;
 renderFields($('parameters'),'param-',fields);
 $('cageEnabled').checked=defaultCageEnabled[selectedType()];
 configureCageKind(true);
 $('scaleTarget').value=$('param-bore_d_mm').value;
 invalidatePreview('已切换轴承类型，请重新生成真实 CAD 模型');
 showDraftIssues();
 updateAvailability();
}
function getParams(){
 const draft=rawDraft();
 return requestFromFields(draft.values,draft.cage,selectedType());
}
async function loadArtifacts(result, sequence){
 const {manifest,file_urls}=validateArtifact(result);
 const instances=buildAssemblyIndex(manifest);
 const templates=new Map();
 const ids=new Set(instances.map(p=>p.part_id));
 for(const id of ids){
  const url=file_urls[id+'.stl'];
  if(!url)throw Error('缺少 '+id+' 对应的 STL 文件');
  const response=await fetch(url,{signal:controller.signal,cache:'no-store'});
  if(!response.ok)throw Error('STL 下载失败：'+id+' (HTTP '+response.status+')');
  const bytes=await response.arrayBuffer();
  if(bytes.byteLength>35_000_000)throw Error('STL 文件过大：'+id);
  templates.set(id,loader.parse(bytes));
  if(sequence!==token)throw Error('请求已失效');
 }
 dispose();
 for(const instance of instances){
  const g=templates.get(instance.part_id).clone();g.computeVertexNormals();
  const color=partColor(instance.part_id,instance.role);
  const material=new THREE.MeshStandardMaterial({
   color,metalness:.34,roughness:.42,side:THREE.DoubleSide
  });
  const mesh=new THREE.Mesh(g,material);mesh.name=instance.id;mesh.userData.role=instance.role;
  mesh.userData.partId=instance.part_id;mesh.userData.partColor=color;
  mesh.userData.base=new THREE.Vector3(...instance.translation_mm);
  // Keep exactly the same Z-axis instance rotation as the STEP assembly.
  mesh.rotation.z=THREE.MathUtils.degToRad(instance.rotation_about_z_deg);
  mesh.userData.radial=new THREE.Vector3(instance.translation_mm[0],instance.translation_mm[1],0).normalize();
  mesh.position.copy(mesh.userData.base);
  entries.push(mesh);scene.add(mesh);
 }
 for(const geometry of templates.values())geometry.dispose();
 active={manifest,instances,file_urls};$('emptyStage').hidden=true;$('quality').textContent='CAD 几何已检查';
 $('modelLabel').textContent='零件原型 '+manifest.parts.length+' · 装配实例 '+instances.length+' · 轴向 Z · 单位 mm';
 $('provenance').textContent='完整度：'+manifest.completeness+' · SHA256: '+manifest.request_hash.slice(0,20)+'…  · 非制造批准';
 $('downloads').replaceChildren();
 for(const [name,url] of Object.entries(file_urls)){
  const link=document.createElement('a');link.textContent=name;link.href=url;link.download=name;
  $('downloads').append(link);
 }
 const drawings=['bearing_assembly_review.svg','bearing_inner_ring_review.svg','bearing_outer_ring_review.svg'];
 const found=drawings.filter(name=>typeof file_urls[name]==='string');
 $('drawingPanel').hidden=found.length===0;
 if(found.length){
  const sel=$('drawingView');sel.replaceChildren();
  for(const name of found){const opt=document.createElement('option');opt.value=name;
   opt.textContent=({'bearing_assembly_review.svg':'总装剖视','bearing_inner_ring_review.svg':'内圈剖视','bearing_outer_ring_review.svg':'外圈剖视'})[name];sel.append(opt);}
  $('drawingPreview').src=file_urls[sel.value];
 }
 presentTree();$('cutaway').checked=false;$('transparent').checked=false;$('explode').value='0';
 applyVisualOptions();resetCamera();status('CAD 模型已加载：'+instances.length+' 个独立装配实例');
}
async function generate(){
 if(!canGenerate())return;
 controller?.abort();controller=new AbortController();const version=++token;
 $('generate').disabled=true;dispose();status('提交 CAD 请求…');
 try{
  const data=getParams();
  const problems=geometryIssues(data);
  if(problems.length){
   paintIssues(problems);
   throw new ParameterInputError(problems[0].message,problems[0].fieldPath);
  }
  const response=await fetch('/api/v2/cad/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
  const reply=await response.json();
  if(!response.ok){
   const detail=describeCadError(reply,response.status);
   throw new ParameterInputError(detail.message,detail.fieldPath);
  }
  if(reply.status!=='succeeded'||typeof reply.manifest_url!=='string')throw Error('服务返回的任务状态无效');
  if(version!==token)return;
  status('STEP 已生成，正在加载真实 STL 网格…');
  const result=await fetch(reply.manifest_url,{signal:controller.signal});
  if(!result.ok)throw Error('成果清单无法读取');
  const payload=await result.json();if(version!==token)return;
  await loadArtifacts(payload,version);
 }catch(error){
  if(version===token&&error.name!=='AbortError'){
   dispose();
   if(error.fieldPath)paintIssues([{fieldPath:error.fieldPath,message:error.message}]);
   status('CAD 生成失败：'+error.message,true);
  }
 }finally{if(version===token){controller=null;$('generate').disabled=!canGenerate();}}
}
$('generate').addEventListener('click',generate);
$('drawingView').addEventListener('change',()=>{const name=$('drawingView').value;if(active&&active.file_urls?.[name])$('drawingPreview').src=active.file_urls[name];});
$('resetParams').addEventListener('click',()=>{
 renderFields($('parameters'),'param-',fields);
 $('cageEnabled').checked=defaultCageEnabled[selectedType()];
 configureCageKind(true);
 $('scaleTarget').value=$('param-bore_d_mm').value;
 invalidatePreview('已恢复当前轴承类型的几何测试参数；请重新生成 CAD');
 showDraftIssues();
});
$('scaleApply').addEventListener('click',()=>{
 try{
  const draft=rawDraft();
  const modified=scaleGeometryFields(draft.values,draft.cage,selectedType(),$('scaleTarget').value);
  const problems=geometryIssues(requestFromFields(modified.values,modified.cage,selectedType()));
  if(problems.length){paintIssues(problems);throw new Error(problems[0].message+' 如当前参数已冲突，请先恢复默认值再整体缩放。');}
  for(const [key] of fields)$('param-'+key).value=modified.values[key];
  if(modified.cage)for(const [key] of cages)$('cage-'+key).value=modified.cage[key];
  invalidatePreview('已按当前几何整体等比例缩放，请生成三维模型');
  showDraftIssues();
 }catch(error){status('比例调整未应用：'+error.message,true);}
});
$('cageEnabled').addEventListener('change',()=>{
 $('cageOptions').hidden=!$('cageEnabled').checked;
 invalidatePreview('保持架设置已更改，请重新生成 CAD');
 showDraftIssues();
});
$('cageKind').addEventListener('change',()=>{
 configureCageKind();
 invalidatePreview('保持架结构已更改，请重新生成 CAD');
 showDraftIssues();
});
$('bearingType').addEventListener('change',configureForm);
showDraftIssues();
for(const id of ['cutaway','transparent','explode'])$(id).addEventListener('input',applyVisualOptions);
$('viewReset').addEventListener('click',()=>{resetCamera();controls.reset();resetCamera();});
(async()=>{try{
 const response=await fetch('/api/v2/cad/status');
 const data=await response.json();
 available=response.ok&&data.available===true&&Array.isArray(data.supported_bearings);
 supportedTypes=new Set(available?data.supported_bearings:[]);
 updateAvailability();
 if(canGenerate())status('请选择轴承类型、输入参数并生成精确 CAD 模型');
 else if(!available)status('CAD 服务不可用；启动 python -m bearing_cad.api --static dist',true);
 }catch{
  available=false;updateAvailability();status('CAD-V2 服务不可用，请启动本地 API',true);
 }
 $('generate').disabled=!canGenerate();
})();
window.rollingViewerSnapshot=()=>({instances:entries.map(p=>({id:p.name,role:p.userData.role,visible:p.visible,position:p.position.toArray(),triangles:p.geometry.attributes.position.count/3,opacity:p.material.opacity,rotationZDeg:THREE.MathUtils.radToDeg(p.rotation.z),color:p.userData.partColor})),requestHash:active?.manifest.request_hash??null});

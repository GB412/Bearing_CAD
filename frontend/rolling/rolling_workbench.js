import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import './rolling_workbench.css';
import {initDrawingWorkbench} from './rolling_drawing.js';
import {initAnalysisWorkbench} from './rolling_analysis.js';
import {deriveRoBASGrooves,deriveRoBASBallCount} from './rolling_robas_geometry.js';
import {bearingForms, cageForms, cageChoices, defaultCageEnabled, buildAssemblyIndex, validateArtifact, requestFromFields, geometryIssues, scaleGeometryFields, describeCadError, ParameterInputError} from './rolling_manifest.js';

const $ = id => document.getElementById(id);
let fields=bearingForms['rolling.deep_groove_ball'].fields;
let cages=cageForms.simplified_annular.fields;
function renderFields(container, prefix, data) {
 container.replaceChildren();
 for (const [key,label,value,choices] of data) {
  const el=document.createElement('label');el.className='field';el.textContent=label;
  if(prefix==='param-')el.dataset.parameterTier=key==='configuration'?'drawing':(['bore_d_mm','outside_d_mm','width_mm'].includes(key)?'basic':'advanced');
  const field=choices?document.createElement('select'):document.createElement('input');
  if(choices){
   for(const option of choices){const item=document.createElement('option');item.value=option;item.textContent=({'':'不指定（手动录入球数）',engineering_plastic:'工程塑料',phenolic:'酚醛层压布管',plain:'原版直圆柱',chamfered:'端部倒角',crowned:'凸度修形 + 倒角'}[option]??option);field.append(item);}
   field.value=value;
  }else{
   field.type='number';field.step=key.endsWith('_count')?'1':'any';field.value=String(value);
  }
  field.id=prefix+key;field.setAttribute('aria-label',label);
  if(prefix==='param-' && (key==='inner_groove_radius_mm'||key==='outer_groove_radius_mm'||key==='ball_count')){
   field.readOnly=true;
   field.classList.add('derived-input');
   field.title=key==='ball_count'
    ?'由 RoBAS 原版球数经验式自动计算；深沟球采用 186° 法，角接触球还取决于保持架材料'
    :'由 RoBAS 原版沟曲率系数与钢球直径自动计算，不需要手动输入';
  }
  field.addEventListener(choices?'change':'input',()=>{
   if(prefix==='param-' && ['ball_d_mm','pitch_d_mm','cage_material'].includes(key))syncDerivedGeometry();
   if(prefix==='param-' && key==='roller_profile')syncRollerProfileInputs();
   invalidatePreview();showDraftIssues();
  });
  el.append(field);container.append(el);
 }
 if(prefix==='param-')syncDerivedGeometry();
}
function syncDerivedGeometry(){
 syncRollerProfileInputs();
 const ball=$('param-ball_d_mm');
 const pitch=$('param-pitch_d_mm');
 const countField=$('param-ball_count');
 if(!ball||!pitch||!countField)return;
 const explicit=$('explicitBallGeometry').checked;
 for(const key of ['ball_count','inner_groove_radius_mm','outer_groove_radius_mm']){
  const field=$('param-'+key);
  field.readOnly=!explicit;
  field.classList.toggle('derived-input',!explicit);
 }
 if(explicit)return;
 syncDerivedGrooves();
 if($('param-cage_material')?.value===''){
  countField.value='';
  return;
 }
 const material=$('param-cage_material')?.value||'engineering_plastic';
 try{
  const count=deriveRoBASBallCount($('bearingType').value,ball.value,pitch.value,material);
  countField.value=count===null?'':String(count);
 }catch{
  countField.value='';
 }
}
function syncRollerProfileInputs(){
 const profile=$('param-roller_profile')?.value;
 const chamfer=$('param-roller_end_chamfer_mm');
 const relief=$('param-roller_crown_relief_mm');
 if(!profile||!chamfer||!relief)return;
 if(profile==='plain'){
  chamfer.value='0';relief.value='0';
 }else if(profile==='chamfered'){
  if(Number(chamfer.value)===0)chamfer.value='0.2';
  relief.value='0';
 }else if(profile==='crowned'){
  if(Number(chamfer.value)===0)chamfer.value='0.2';
  if(Number(relief.value)===0)relief.value='0.02';
 }
 chamfer.readOnly=profile==='plain';
 relief.readOnly=profile!=='crowned';
 chamfer.classList.toggle('derived-input',profile==='plain');
 relief.classList.toggle('derived-input',profile!=='crowned');
}
function syncDerivedGrooves(){
 const diameter=$('param-ball_d_mm')?.value;
 if(diameter===undefined)return;
 let radii;
 try {radii=deriveRoBASGrooves($('bearingType').value,diameter);}
 catch {radii=null;}
 if(!radii)return;
 for(const [key,value] of Object.entries(radii)){
  const field=$('param-'+key);
  if(field)field.value=String(value);
 }
}
renderFields($('parameters'),'param-',fields);
renderFields($('cageParams'),'cage-',cages);
let active=null, token=0, controller=null, available=false;
let confirmedKey=null;
let drawings, analysis;
let supportedTypes=new Set(), robasSizingAvailable=false, robasOptimizationAvailable=false;
let robasACBOptimizationAvailable=false, robasCRBOptimizationAvailable=false;
let appliedSizingEvidence=null, appliedStampingEvidence=null, appliedOptimizationEvidence=null;
let optimizationPreview=null, optimizationRun=null, optimizationRevision=0;
const OPTIMIZERS={
 dgb:{type:'rolling.deep_groove_ball',button:'runRoBASOptimizer',stem:'optimization',available:()=>robasOptimizationAvailable},
 acb:{type:'rolling.angular_contact_ball',button:'runRoBASACBOptimizer',stem:'acbOptimization',available:()=>robasACBOptimizationAvailable},
 crb:{type:'rolling.cylindrical_roller',button:'runRoBASCRBOptimizer',stem:'crbOptimization',available:()=>robasCRBOptimizationAvailable},
};
const ACB_MODEL=/^7[023][0-9]{2,3}$/;
const ACB_WEIGHTS=['acbSpinWeight','acbAxialStiffnessWeight','acbDynamicLoadWeight'];
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
}
function resetCamera(){
 const bounds=new THREE.Box3();
 for(const part of entries){part.updateMatrixWorld(true);bounds.expandByObject(part);}
 const center=bounds.isEmpty()?new THREE.Vector3():bounds.getCenter(new THREE.Vector3());
 const size=bounds.isEmpty()?90:Math.max(bounds.getSize(new THREE.Vector3()).length(),10);
 controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(size*.9,size*.65,size*.85));
 camera.near=Math.max(.01,size/500);camera.far=size*35;camera.updateProjectionMatrix();controls.update();
}
function resize(){
 const viewport=$('viewport');
 const width=viewport.clientWidth;
 const height=viewport.clientHeight;
 // The 3D panel is intentionally hidden while the 2D drawing workspace is active.
 // Keep the last valid camera dimensions until the model tab becomes visible again.
 if(width<=0||height<=0)return;
 renderer.setSize(width,height,false);
 camera.aspect=width/height;
 camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe($('viewport'));
window.addEventListener('resize',resize);
resize();
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
function updateStampingActions(){
 const activeCage=selectedType()==='rolling.deep_groove_ball'&&
  $('cageEnabled').checked&&$('cageKind').value==='stamping_double_half';
 $('robasStampingActions').hidden=!activeCage;
 $('applyRoBASStamping').disabled=!available||!activeCage;
}
function updateAvailability(){
 updateStampingActions();
 for(const [kind,opt] of Object.entries(OPTIMIZERS))
  $(kind+'OptimizationPanel').hidden=selectedType()!==opt.type;
 updateOptimizationButtons();
 $('dgbSizingPanel').hidden=selectedType()!==OPTIMIZERS.dgb.type;
 const enabled=canGenerate();$('generate').disabled=!enabled;
 $('connection').textContent=available?'本地 OCCT 引擎在线':'CAD 引擎不可用';
 $('connection').dataset.state=available?'ready':'offline';
 $('applyRoBASGeometry').hidden=selectedType()!=='rolling.deep_groove_ball';
 $('applyRoBASGeometry').disabled=!robasSizingAvailable||selectedType()!=='rolling.deep_groove_ball';
 if(available&&!enabled)status('当前 CAD 服务暂不支持所选轴承类型',true);
}
function optimizationFeedback(kind,message,state=''){
 const hint=$(OPTIMIZERS[kind].stem+'Hint');
 hint.textContent=message;
 hint.hidden=!message;
 hint.dataset.state=state;
}
function updateOptimizationButtons(){
 for(const opt of Object.values(OPTIMIZERS))
  $(opt.button).disabled=Boolean(optimizationRun)||!opt.available()||selectedType()!==opt.type;
}
function clearOptimizationCandidates(invalidated=false){
 const affected=optimizationPreview?.kind??optimizationRun?.kind;
 optimizationRevision++;
 optimizationPreview=null;
 for(const [kind,opt] of Object.entries(OPTIMIZERS)){
  $(opt.stem+'Results').hidden=true;
  $(opt.stem+'Candidates').replaceChildren();
  if(!invalidated||$(opt.stem+'Hint').dataset.state!=='stale')optimizationFeedback(kind,'');
 }
 if(invalidated&&affected)optimizationFeedback(affected,'输入已改变，原候选已失效，请重新计算。','stale');
}
function invalidatePreview(message='输入已改变，请重新生成 CAD'){
 token++;controller?.abort();controller=null;
 clearOptimizationCandidates(true);
 updateACBValidation();
 appliedSizingEvidence=null;appliedStampingEvidence=null;appliedOptimizationEvidence=null;
 dispose();status(message);
 confirmedKey=null;
 $('designConfirmation').textContent='当前设计尚未确认';
 drawings?.invalidate();
 analysis?.invalidateDesign();
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
 updateStampingActions();
}
function configureForm(){
 fields=bearingForms[selectedType()].fields;
 $('explicitBallGeometry').checked=false;
 $('explicitBallGeometryControl').hidden=selectedType()==='rolling.cylindrical_roller';
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
function checkedDesign(){
 const design=getParams();
 const issues=geometryIssues(design);
 if(issues.length)throw new ParameterInputError(issues[0].message,issues[0].fieldPath);
 return design;
}
function confirmDesign(){
 confirmedKey=JSON.stringify(checkedDesign());
 $('designConfirmation').textContent='当前设计已确认 · 仅限本次工作台会话';
 analysis?.syncDesign();
}
async function applyRoBASGeometry(){
 if(selectedType()!=='rolling.deep_groove_ball'||!robasSizingAvailable)return;
 const button=$('applyRoBASGeometry');button.disabled=true;
 const requestToken=token;
 try{
  const input={
   bearing_type:selectedType(),
   bore_d_mm:Number($('param-bore_d_mm').value),
   outside_d_mm:Number($('param-outside_d_mm').value),
   width_mm:Number($('param-width_mm').value)
  };
  const response=await fetch('/api/v2/cad/sizing/dgb-geometry',{
   method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)
  });
  const reply=await response.json();
  if(selectedType()!=='rolling.deep_groove_ball'||requestToken!==token)return;
  if(!response.ok)throw Error(reply.error?.message||'RoBAS 初始几何计算失败');
  if(reply.schema_version!=='bearing-cad.robas-dgb-geometry.v1'||reply.candidate_only!==true)
   throw Error('RoBAS sizing response contract is invalid');
  const p=reply.parameters;
  for(const key of ['bore_d_mm','outside_d_mm','width_mm','ball_d_mm','pitch_d_mm',
                    'ball_count','inner_groove_radius_mm','outer_groove_radius_mm',
                    'inner_shoulder_d_mm','outer_shoulder_d_mm']){
   if(!Number.isFinite(p[key]))throw Error('RoBAS sizing response is missing '+key);
   $('param-'+key).value=String(p[key]);
  }
  syncDerivedGeometry();
  // Keep the backend's source-calculated values as the request snapshot.
  for(const key of ['ball_count','inner_groove_radius_mm','outer_groove_radius_mm'])
   $('param-'+key).value=String(p[key]);
  if($('cageEnabled').checked&&$('cageKind').value==='simplified_annular'){
   for(const [key,value] of Object.entries(reply.simplified_cage_dimensions||{}))
    if($('cage-'+key))$('cage-'+key).value=String(value);
  }
  $('scaleTarget').value=String(p.bore_d_mm);
  invalidatePreview('已按 RoBAS DGBGeometry 预填候选参数，请检查后生成模型');
  appliedSizingEvidence=reply;
  showDraftIssues();
  status('RoBAS DGBGeometry 候选已预填：Dw='+p.ball_d_mm+
         ' mm，Dpw='+p.pitch_d_mm+' mm，Z='+p.ball_count+
         '。未运行 DGBOptimizer，且不是制造批准。');
 }catch(error){
  status('RoBAS 几何预填失败：'+error.message,true);
 }finally{
  button.disabled=!robasSizingAvailable||selectedType()!=='rolling.deep_groove_ball';
 }
}
function currentOptimizationInput(){
 if(selectedType()!=='rolling.deep_groove_ball')
  throw Error('当前仅支持深沟球轴承 DGB 优化');
 const numberFrom=(id,label)=>{
  const raw=$(id).value.trim();
  if(!raw)throw Error('请填写'+label);
  const value=Number(raw);
  if(!Number.isFinite(value))throw Error(label+'必须是有限数值');
  return value;
 };
 const model=$('drawingModel').value.trim();
 const grade=$('drawingAccuracy').value;
 const clearance=$('drawingClearance').value;
 if(!model)throw Error('请在二维图纸设置中填写原版轴承型号');
 if(!clearance)throw Error('请在二维图纸设置中选择径向游隙组');
 let cage=null;
 if($('cageEnabled').checked){
  if($('cageKind').value!=='simplified_annular')
   throw Error('冲压保持架需要重新计算，请先选择简化环缘保持架或暂时取消保持架');
  cage={kind:'simplified_annular',
        pocket_clearance_mm:numberFrom('cage-pocket_clearance_mm','保持架球兜间隙')};
 }
 return {
  initial:{
   bearing_type:selectedType(),
   bore_d_mm:numberFrom('param-bore_d_mm','内径 d'),
   outside_d_mm:numberFrom('param-outside_d_mm','外径 D'),
   width_mm:numberFrom('param-width_mm','宽度 B'),
   cage
  },
  optimization:{
   model,accuracy_class:grade,radial_clearance_group:clearance,
   weights:{
    dynamic_load:numberFrom('optimizerCrWeight','动载荷权重'),
    radial_stiffness:numberFrom('optimizerStiffnessWeight','径向刚度权重')
   }
  }
 };
}
function acbWeightIssue(){
 const weights=ACB_WEIGHTS.map(id=>$(id).value.trim());
 if(weights.some(value=>!value||!Number.isFinite(Number(value))||Number(value)<0||Number(value)>1))
  return '请为三项权重分别填写 0 至 1 的数值。';
 const sum=weights.reduce((total,value)=>total+Number(value),0);
 return Math.abs(sum-1)>1e-9?'权重合计为 '+Number(sum.toFixed(10))+'，须等于 1。':'';
}
function acbCageIssue(){
 if($('cageEnabled').checked)return '请先取消保持架，再计算角接触球候选。';
 if(!$('param-cage_material')?.value)return '请在模型尺寸中选择球数计算使用的保持架材料。';
 return '';
}
function updateACBValidation(){
 if(selectedType()!==OPTIMIZERS.acb.type)return;
 const valid=ACB_MODEL.test($('acbModel').value.trim());
 $('acbModel').setAttribute('aria-invalid',String(!valid));
 const model=$('acbModelHint');
 model.textContent=valid?'与二维图纸共用型号。':'请输入 70、72 或 73 系列型号，例如 7008。';
 model.classList.toggle('field-error',!valid);
 const weightIssue=acbWeightIssue();
 $('acbWeightHint').textContent=weightIssue||'权重合计 1';
 $('acbWeightHint').classList.toggle('field-error',Boolean(weightIssue));
 const cageIssue=acbCageIssue();
 $('acbCageHint').textContent=cageIssue;
 $('acbCageHint').hidden=!cageIssue;
}
function currentACBOptimizationInput(){
 if(selectedType()!=='rolling.angular_contact_ball')
  throw Error('当前仅支持角接触球轴承 ACB 优化');
 const issue=acbCageIssue();
 if(issue)throw Error(issue);
 const numeric=(id,label)=>{
  const value=$(id).value.trim();
  if(value==='')throw Error('请填写'+label);
  const parsed=Number(value);
  if(!Number.isFinite(parsed))throw Error(label+'必须是有限数字');
  return parsed;
 };
 const model=$('drawingModel').value.trim();
 if(!ACB_MODEL.test(model))throw Error('请输入 70、72 或 73 系列轴承型号，例如 7008。');
 const weightIssue=acbWeightIssue();
 if(weightIssue)throw Error(weightIssue);
 const contactAngle=numeric('param-contact_angle_deg','接触角');
 if(![15,25,40].includes(contactAngle))throw Error('请将接触角设为 15°、25° 或 40°。');
 const preload=numeric('acbPreloadN','预载荷 Fa');
 if(preload<=0)throw Error('预载荷 Fa 须大于 0 N。');
 return {
  initial:{
   bearing_type:selectedType(),
   bore_d_mm:numeric('param-bore_d_mm','内径 d'),
   outside_d_mm:numeric('param-outside_d_mm','外径 D'),
   width_mm:numeric('param-width_mm','宽度 B'),
   contact_angle_deg:contactAngle,
   cage_material:$('param-cage_material').value,
   cage:null
  },
  optimization:{
   model,accuracy_class:$('drawingAccuracy').value,
   preload_n:preload,
   weights:{
    spin_ratio:numeric('acbSpinWeight','旋滚比权重'),
    axial_stiffness:numeric('acbAxialStiffnessWeight','轴向刚度权重'),
    dynamic_load:numeric('acbDynamicLoadWeight','动载荷权重'),
   }
  }
 };
}
function currentCRBOptimizationInput(){
 if(selectedType()!=='rolling.cylindrical_roller')
  throw Error('请选择圆柱滚子轴承 CRB');
 if($('cageEnabled').checked)
  throw Error('优化后滚子数量和长度可能改变，请先取消原有窗孔保持架');
 const number=(id,label)=>{
  const raw=$(id).value.trim();
  if(raw==='')throw Error('请填写 '+label);
  const value=Number(raw);
  if(!Number.isFinite(value))throw Error(label+'必须是有限数字');
  return value;
 };
 const configuration=$('param-configuration').value;
 const model=$('drawingModel').value.trim();
 if(!model)throw Error('请先在二维图纸设置中填写 N 系列轴承型号（如 NU208）');
 return {
  initial:{
   bearing_type:selectedType(),
   bore_d_mm:number('param-bore_d_mm','内径 d'),
   outside_d_mm:number('param-outside_d_mm','外径 D'),
   width_mm:number('param-width_mm','宽度 B'),
   configuration,
   radial_clearance_mm:number('param-radial_clearance_mm','径向净距'),
   axial_clearance_mm:number('param-axial_clearance_mm','轴向净距'),
   rib_width_mm:number('param-rib_width_mm','挡边宽度'),
   roller_profile:$('param-roller_profile').value,
   roller_end_chamfer_mm:number('param-roller_end_chamfer_mm','滚子倒角'),
   roller_crown_relief_mm:number('param-roller_crown_relief_mm','滚子凸度'),
   cage:null
  },
  optimization:{
   model,accuracy_class:$('drawingAccuracy').value,
   objective:'dynamic_load_only'
  }
 };
}
function optimizationInputFor(kind){
 if(kind==='acb')return currentACBOptimizationInput();
 if(kind==='crb')return currentCRBOptimizationInput();
 return currentOptimizationInput();
}
function optimizationSnapshot(kind='dgb'){
 return JSON.stringify(optimizationInputFor(kind));
}
function renderOptimizationCandidates(reply,snapshot,version,kind){
 const isACB=kind==='acb',isCRB=kind==='crb';
 const stem=OPTIMIZERS[kind].stem;
 const container=$(stem+'Candidates');
 container.replaceChildren();
 $(stem+'Results').hidden=false;
 optimizationFeedback(kind,'找到 '+reply.total_valid_candidates+' 组可行方案，显示前 '+reply.candidates.length+' 组。','success');
 for(const item of reply.candidates){
  const card=document.createElement('div');
  card.className='optimization-candidate';
  const title=document.createElement('strong');
  title.textContent='候选 '+item.rank+
    (isCRB?' · Cr 相对评分 ':' · 综合评分 ')+item.score.toFixed(3);
  const metrics=document.createElement('dl');
  metrics.className='candidate-metrics';
  const p=item.design.parameters;
  const rows=isCRB
   ? [['滚子直径',p.roller_d_mm.toFixed(3)+' mm'],['滚子长度',p.roller_length_mm.toFixed(2)+' mm'],['滚子数',p.roller_count]]
   : [['钢球直径',p.ball_d_mm.toFixed(3)+' mm'],['球数',p.ball_count]];
  rows.push(['节圆直径',p.pitch_d_mm.toFixed(2)+' mm'],
            ['动载荷 Cr',(item.metrics.dynamic_load_n/1000).toFixed(2)+' kN']);
  if(isACB)rows.push(['轴向刚度 Ka',item.metrics.axial_stiffness_source_units.toFixed(2)],
                     ['旋滚比',item.metrics.spin_ratio.toFixed(5)]);
  else if(isCRB)rows.push(['静载荷 Cor',(item.metrics.static_load_n/1000).toFixed(2)+' kN'],
                         ['Kr 原版未实现','不可用']);
  else rows.push(['经验径向刚度',item.metrics.radial_stiffness_source_units.toFixed(2)]);
  for(const [label,value] of rows){
   const cell=document.createElement('div');
   const name=document.createElement('dt');name.textContent=label;
   const number=document.createElement('dd');number.textContent=String(value);
   cell.append(name,number);metrics.append(cell);
  }
  const button=document.createElement('button');
  button.type='button';button.className='secondary';
  button.textContent='确认并应用此设计';
  button.addEventListener('click',()=>{
   try{
    if(version!==optimizationRevision||!optimizationPreview||
       optimizationPreview.kind!==kind||
       optimizationPreview.snapshot!==optimizationSnapshot(kind))
     throw Error('设计输入已改变，请重新计算优化候选');
    const candidate=optimizationPreview.reply.candidates.find(
      row=>row.candidate_id===item.candidate_id);
    if(!candidate)throw Error('候选已失效');
    const design=candidate.design;
    const draft=rawDraft();
    const next={...draft.values,...design.parameters};
    const nextCage=design.cage??null;
    const verified=requestFromFields(next,nextCage,selectedType());
    const issues=geometryIssues(verified);
    if(issues.length)throw Error(issues[0].message);
    // Only mutate controls after the whole candidate passes preflight.
    for(const [key] of fields)$('param-'+key).value=String(next[key]??'');
    $('cageEnabled').checked=Boolean(nextCage);
    if(nextCage&&$('cageKind').value!==nextCage.kind){
     $('cageKind').value=nextCage.kind;
     configureCageKind();
    }
    $('cageOptions').hidden=!nextCage;
    if(nextCage)for(const [key] of cages)$('cage-'+key).value=String(nextCage[key]);
    $('scaleTarget').value=String(design.parameters.bore_d_mm);
    invalidatePreview('已确认优化候选，请重新生成二维或三维模型');
    appliedOptimizationEvidence={
      source_model:reply.source_model,
      candidate_id:item.candidate_id,
      source_initial_hash:reply.source_initial_hash,
    };
    confirmDesign();
    showDraftIssues();
    const message='已应用候选 '+item.rank+'。可生成 CAD，三维完成后可进入拟静力学分析，按页面提示检查保持架兼容性。';
    optimizationFeedback(kind,message,'success');
    $(stem+'Hint').focus({preventScroll:true});
   }catch(error){optimizationFeedback(kind,'不能应用候选：'+error.message,'error');}
  });
  card.append(title,metrics,button);container.append(card);
 }
}
const NO_CANDIDATES='未找到可行候选。请核对型号、外形尺寸和当前约束，再重新计算。';
function optimizationError(reply,http){
 const detail=reply?.error?.message??'';
 if(/^No (?:source-backed )?(?:DGB |ACB |CRB )?candidates?\b/i.test(detail))return NO_CANDIDATES;
 if(http===503)return '优化服务暂不可用。请检查本机 RoBAS 资源配置后重试。';
 if(reply?.error?.field_path==='/optimization/model')return '型号不符合原版系列要求，请核对型号后重试。';
 if(reply?.error?.field_path?.startsWith('/optimization/weights'))return '请检查各项权重均在 0 至 1 范围内，且合计为 1。';
 return detail ? detail+'。请检查当前输入或原版数据后重试。' : '未收到有效响应，请检查本机 CAD 服务后重试。';
}
function validOptimizationCandidate(candidate,kind){
 const p=candidate?.design?.parameters,m=candidate?.metrics;
 if(typeof candidate?.candidate_id!=='string'||!p||!m||!Number.isFinite(candidate.score))return false;
 if(![p.pitch_d_mm,m.dynamic_load_n].every(Number.isFinite))return false;
 if(kind==='crb')return [p.roller_d_mm,p.roller_length_mm,p.roller_count,m.static_load_n].every(Number.isFinite)&&
  m.radial_stiffness_source_units===null;
 if(![p.ball_d_mm,p.ball_count].every(Number.isFinite))return false;
 return kind==='acb'?[m.spin_ratio,m.axial_stiffness_source_units].every(Number.isFinite):
  Number.isFinite(m.radial_stiffness_source_units);
}
async function runOptimization(kind){
 const opt=OPTIMIZERS[kind];
 if(optimizationRun||!opt.available()||selectedType()!==opt.type)return;
 clearOptimizationCandidates();
 const version=optimizationRevision;
 try{
  const snapshot=optimizationSnapshot(kind);
  optimizationRun={kind};
  updateOptimizationButtons();
  optimizationFeedback(kind,'正在计算候选方案…','busy');
  const response=await fetch('/api/v2/cad/optimization/'+kind,{
   method:'POST',headers:{'Content-Type':'application/json'},body:snapshot
  });
  const reply=await response.json().catch(()=>null);
  if(version!==optimizationRevision||snapshot!==optimizationSnapshot(kind))return;
  if(!response.ok)throw Error(optimizationError(reply,response.status));
  if(reply?.schema_version!=='bearing-cad.robas-'+kind+'-optimization.v1'||
     reply.candidate_only!==true||reply.applied!==false||
     (kind==='crb'&&reply.objective_status!=='CR_ONLY_SOURCE_KR_NOT_IMPLEMENTED')||
     !Array.isArray(reply.candidates))throw Error('候选结果格式无效，请检查本机服务后重试。');
  if(!reply.candidates.length)throw Error(NO_CANDIDATES);
  if(!reply.candidates.every(candidate=>validOptimizationCandidate(candidate,kind)))
   throw Error('候选结果包含无效指标，请检查原版数据后重试。');
  optimizationPreview={reply,snapshot,kind};
  renderOptimizationCandidates(reply,snapshot,version,kind);
 }catch(error){
  if(version===optimizationRevision){
   const message=error instanceof TypeError?'连接优化服务失败，请检查本机 CAD 服务后重试。':error.message;
   optimizationFeedback(kind,message,'error');
  }
 }finally{
  optimizationRun=null;
  updateOptimizationButtons();
 }
}
async function applyRoBASStamping(){
 if(!available||selectedType()!=='rolling.deep_groove_ball'||
    !$('cageEnabled').checked||$('cageKind').value!=='stamping_double_half')return;
 const button=$('applyRoBASStamping');button.disabled=true;
 const requestToken=token;
 try{
  const input={
   bearing_type:selectedType(),bearing_model:$('robasStampingModel').value.trim(),
   ball_d_mm:Number($('param-ball_d_mm').value),
   pitch_d_mm:Number($('param-pitch_d_mm').value),
   ball_count:Number($('param-ball_count').value),
   bearing_width_mm:Number($('param-width_mm').value),
   inner_shoulder_d_mm:Number($('param-inner_shoulder_d_mm').value),
   outer_shoulder_d_mm:Number($('param-outer_shoulder_d_mm').value),
   rivet_hole_clearance_mm:Number($('cage-rivet_hole_clearance_mm').value)
  };
  const response=await fetch('/api/v2/cad/sizing/dgb-stamping',{
   method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)
  });
  const reply=await response.json();
  if(token!==requestToken||selectedType()!=='rolling.deep_groove_ball'||
     !$('cageEnabled').checked||$('cageKind').value!=='stamping_double_half')return;
  if(!response.ok)throw Error(reply.error?.message||'RoBAS 冲压保持架参数计算失败');
  if(reply.schema_version!=='bearing-cad.robas-stamping-adapter.v1'||
     reply.candidate_only!==true||!reply.cad_cage||
     reply.cad_cage.kind!=='stamping_double_half')
   throw Error('RoBAS 保持架响应格式不符合约定');
  const values=reply.cad_cage;
  const keys=cageForms.stamping_double_half.fields.map(field=>field[0]);
  for(const key of keys)
   if(!Number.isFinite(values[key])||values[key]<=0)throw Error('缺失有效保持架参数：'+key);
  // Validate the complete candidate before writing any input.
  const draft=rawDraft();
  const checked=requestFromFields(draft.values,{...values},selectedType());
  const issues=geometryIssues(checked);
  if(issues.length)throw Error(issues[0].message);
  const previousDGB=appliedSizingEvidence;
  for(const key of keys)$('cage-'+key).value=String(values[key]);
  invalidatePreview('已按 RoBAS StampingCage 预填保持架候选参数');
  appliedSizingEvidence=previousDGB;
  appliedStampingEvidence=reply;
  showDraftIssues();
  status('RoBAS 冲压双半笼已预填（型号 '+reply.bearing_model+
         '）：径向宽度 '+reply.source_dimensions.width_radial_mm+
         ' mm，轴向总宽 '+values.width_mm+
         ' mm。尚需确认型号匹配与工艺尺寸，非制造批准。');
 }catch(error){
  if(requestToken===token)status('RoBAS 冲压保持架预填失败：'+error.message,true);
 }finally{updateStampingActions();}
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
 active={manifest,instances};$('emptyStage').hidden=true;$('quality').textContent='CAD 几何已检查';
 $('modelLabel').textContent='零件原型 '+manifest.parts.length+' · 装配实例 '+instances.length+' · 轴向 Z · 单位 mm';
 const sourceHash=appliedSizingEvidence?.source_files?.['BallDB.csv'];
 const sourceParts=[];
 if(sourceHash)sourceParts.push('RoBAS DGBGeometry · BallDB SHA256 '+sourceHash.slice(0,12)+'… · 非 Optimizer');
 if(appliedStampingEvidence)sourceParts.push('RoBAS StampingCage ('+appliedStampingEvidence.bearing_model+') 候选');
 if(appliedOptimizationEvidence)sourceParts.push(
  'RoBAS 优化候选 · '+appliedOptimizationEvidence.source_model+
  ' · 已确认 '+appliedOptimizationEvidence.candidate_id);
 const sourceNote=sourceParts.length
  ?'参数来源（本会话）：'+sourceParts.join(' + ')
  :'参数来源：显式输入/几何测试预设';
 $('provenance').textContent='完整度：'+manifest.completeness+' · SHA256: '+manifest.request_hash.slice(0,20)+'… · '+sourceNote+' · 非制造批准';
 $('downloads').replaceChildren();
 for(const [name,url] of Object.entries(file_urls)){
  const link=document.createElement('a');link.textContent=name;link.href=url;link.download=name;
  $('downloads').append(link);
 }
 presentTree();$('cutaway').checked=false;$('transparent').checked=false;$('explode').value='0';
 applyVisualOptions();resetCamera();status('CAD 模型已加载：'+instances.length+' 个独立装配实例');
}
async function generate(){
 if(!canGenerate())return;
 controller?.abort();controller=new AbortController();const version=++token;
 $('generate').disabled=true;dispose();analysis.syncDesign();drawings.updateVersion();status('提交 CAD 请求…');
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
  if(version!==token)return;
  const snapshotUrl=payload.file_urls['design_snapshot.json'];
  if(/^[a-f0-9]{32}$/.test(reply.job_id??'')&&payload.job_id===reply.job_id&&
     reply.request_hash===active.manifest.request_hash&&
     snapshotUrl===`/api/v2/cad/artifacts/${reply.job_id}/files/design_snapshot.json`){
   active.analysisEvidence={jobId:reply.job_id, hash:reply.request_hash, snapshotUrl, key:JSON.stringify(data)};
  }
  analysis.syncDesign();drawings.updateVersion();
 }catch(error){
  if(version===token&&error.name!=='AbortError'){
   dispose();analysis.syncDesign();drawings.updateVersion();
   if(error.fieldPath)paintIssues([{fieldPath:error.fieldPath,message:error.message}]);
   status('CAD 生成失败：'+error.message,true);
  }
 }finally{if(version===token){controller=null;$('generate').disabled=!canGenerate();}}
}
$('generate').addEventListener('click',generate);
$('applyRoBASGeometry').addEventListener('click',applyRoBASGeometry);
$('applyRoBASStamping').addEventListener('click',applyRoBASStamping);
for(const [kind,opt] of Object.entries(OPTIMIZERS))
 $(opt.button).addEventListener('click',()=>runOptimization(kind));
$('editCRBOptimizationContext').addEventListener('click',()=>{
 $('workspace2dTab').click();
});
$('editOptimizationContext').addEventListener('click',()=>{
 $('workspace2dTab').click();
});
$('acbModel').value=$('drawingModel').value;
$('acbModel').addEventListener('input',()=>{
 const shared=$('drawingModel');
 shared.value=$('acbModel').value;
 shared.dispatchEvent(new Event('input',{bubbles:true}));
});
for(const id of ['drawingModel','drawingAccuracy','drawingClearance',
                 'optimizerCrWeight','optimizerStiffnessWeight','acbPreloadN',...ACB_WEIGHTS]){
 $(id).addEventListener('input',()=>{
  if(id==='drawingModel'&&$('acbModel').value!==$('drawingModel').value)
   $('acbModel').value=$('drawingModel').value;
  clearOptimizationCandidates(true);
  updateACBValidation();
 });
}
$('robasStampingModel').addEventListener('input',()=>invalidatePreview('RoBAS 保持架型号已更改，请重新生成 CAD'));
drawings=initDrawingWorkbench(getParams,()=>active?.analysisEvidence?.hash);
analysis=initAnalysisWorkbench({
 getType:selectedType,
 getDesign:getParams,
 getConfirmedKey:()=>confirmedKey,
 getCad:()=>active?.analysisEvidence,
});
$('confirmDesign').addEventListener('click',()=>{
 try{confirmDesign();showDraftIssues();}
 catch(error){status('不能确认设计：'+error.message,true);showDraftIssues();}
});
$('explicitBallGeometry').addEventListener('change',()=>{
 syncDerivedGeometry();invalidatePreview();showDraftIssues();
});
$('resetParams').addEventListener('click',()=>{
 $('explicitBallGeometry').checked=false;
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
  syncDerivedGeometry();
  if(modified.cage)for(const [key] of cages)$('cage-'+key).value=modified.cage[key];
  invalidatePreview('已按当前几何整体等比例缩放，请生成三维模型');
  showDraftIssues();
 }catch(error){status('比例调整未应用：'+error.message,true);}
});
$('cageEnabled').addEventListener('change',()=>{
 $('cageOptions').hidden=!$('cageEnabled').checked;
 updateStampingActions();
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
 robasSizingAvailable=available&&data.robas_sizing_available===true;
 robasOptimizationAvailable=available&&data.robas_optimization_available===true;
 robasACBOptimizationAvailable=available&&data.robas_acb_optimization_available===true;
 robasCRBOptimizationAvailable=available&&data.robas_crb_optimization_available===true;
 updateAvailability();
 if(canGenerate())status('请选择轴承类型、输入参数并生成精确 CAD 模型');
 else if(!available)status('CAD 服务不可用；启动 python -m bearing_cad.api --static dist',true);
 }catch{
  available=false;robasSizingAvailable=false;robasOptimizationAvailable=false;
  robasACBOptimizationAvailable=false;robasCRBOptimizationAvailable=false;
  updateAvailability();status('CAD-V2 服务不可用，请启动本地 API',true);
 }
 $('generate').disabled=!canGenerate();
})();
window.rollingViewerSnapshot=()=>({instances:entries.map(p=>({id:p.name,role:p.userData.role,visible:p.visible,position:p.position.toArray(),triangles:p.geometry.attributes.position.count/3,opacity:p.material.opacity,rotationZDeg:THREE.MathUtils.radToDeg(p.rotation.z),color:p.userData.partColor})),requestHash:active?.manifest.request_hash??null});

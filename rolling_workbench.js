import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import './rolling_workbench.css';
import {buildAssemblyIndex, validateArtifact, requestFromFields, apiMessage} from './rolling_manifest.js';

const $ = id => document.getElementById(id);
const fields = [
 ['bore_d_mm','内径 d',40],['outside_d_mm','外径 D',68],['width_mm','宽度 B',15],
 ['ball_d_mm','钢球直径',8],['pitch_d_mm','节圆直径',54],['ball_count','钢球数量',11],
 ['inner_groove_radius_mm','内沟曲率半径',4.3],['outer_groove_radius_mm','外沟曲率半径',4.5],
 ['inner_shoulder_d_mm','内圈肩部直径',47.2],['outer_shoulder_d_mm','外圈肩部直径',60.8],
];
const cages=[['inner_d_mm','保持架内径',48],['outside_d_mm','保持架外径',60],['width_mm','保持架宽度',11],['pocket_clearance_mm','球兜间隙',.25]];
function renderFields(container, prefix, data) {
 container.replaceChildren();
 for (const [key,label,value] of data) {
  const el=document.createElement('label');el.className='field';el.textContent=label;
  const input=document.createElement('input');input.type='number';input.step=key.includes('count')?'1':'any';input.value=String(value);
  input.id=prefix+key;input.setAttribute('aria-label',label);el.append(input);container.append(el);
 }
}
renderFields($('parameters'),'param-',fields);renderFields($('cageParams'),'cage-',cages);
let active=null, token=0, controller=null, available=false;
const scene=new THREE.Scene();scene.background=new THREE.Color('#102136');
const camera=new THREE.PerspectiveCamera(36,1,.1,5000);
const renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));
renderer.localClippingEnabled=true;$('viewport').prepend(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
scene.add(new THREE.HemisphereLight('#d5efff','#405c73',2.2));
const key=new THREE.DirectionalLight('#ffffff',2.6);key.position.set(2,4,6);scene.add(key);
const fill=new THREE.DirectionalLight('#66b8f7',1.0);fill.position.set(-5,-2,-3);scene.add(fill);
const clipPlane=new THREE.Plane(new THREE.Vector3(1,0,0),0);
const palette={inner_ring:0x62a8df,outer_ring:0xa4b8cf,rolling_element:0xe5c88c,cage:0x9aabd3};
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
  const direction=object.userData.role==='outer_ring'?1:object.userData.role==='inner_ring'?-1:object.userData.role==='cage'?0.5:0;
  object.position.z+=explode*15*direction;
  if(object.userData.role==='rolling_element')object.position.addScaledVector(object.userData.radial,explode*10);
 }
}
function presentTree(){
 $('parts').replaceChildren();$('partCount').textContent=entries.length+' 个实例';
 for(const part of entries){
  const label=document.createElement('label');label.className='partrow';
  const check=document.createElement('input');check.type='checkbox';check.checked=true;check.setAttribute('aria-label','显示 '+part.name);
  check.addEventListener('change',()=>{part.visible=check.checked;});
  const name=document.createElement('span');name.textContent=part.name;
  label.append(check,name);$('parts').append(label);
 }
}
function getParams(){
 const p={};for(const [key] of fields)p[key]=$('param-'+key).value;
 const c=$('cageEnabled').checked?Object.fromEntries(cages.map(([key])=>[key,$('cage-'+key).value])):null;
 return requestFromFields(p,c);
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
  const material=new THREE.MeshStandardMaterial({color:palette[instance.role]||0xb3c6d8,metalness:.45,roughness:.35,side:THREE.DoubleSide});
  const mesh=new THREE.Mesh(g,material);mesh.name=instance.id;mesh.userData.role=instance.role;
  mesh.userData.base=new THREE.Vector3(...instance.translation_mm);
  mesh.userData.radial=new THREE.Vector3(instance.translation_mm[0],instance.translation_mm[1],0).normalize();
  mesh.position.copy(mesh.userData.base);
  entries.push(mesh);scene.add(mesh);
 }
 for(const geometry of templates.values())geometry.dispose();
 active={manifest,instances};$('emptyStage').hidden=true;$('quality').textContent='CAD 几何已检查';
 $('modelLabel').textContent='零件原型 '+manifest.parts.length+' · 装配实例 '+instances.length+' · 轴向 Z · 单位 mm';
 $('provenance').textContent='完整度：'+manifest.completeness+' · SHA256: '+manifest.request_hash.slice(0,20)+'…  · 非制造批准';
 $('downloads').replaceChildren();
 for(const [name,url] of Object.entries(file_urls)){
  const link=document.createElement('a');link.textContent=name;link.href=url;link.download=name;
  $('downloads').append(link);
 }
 presentTree();$('cutaway').checked=false;$('transparent').checked=false;$('explode').value='0';
 applyVisualOptions();resetCamera();status('CAD 模型已加载：'+instances.length+' 个独立装配实例');
}
async function generate(){
 if(!available)return;
 controller?.abort();controller=new AbortController();const version=++token;
 $('generate').disabled=true;dispose();status('提交 CAD 请求…');
 try{
  const data=getParams();
  const response=await fetch('/api/v2/cad/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
  const reply=await response.json();
  if(!response.ok)throw Error(apiMessage(reply,response.status));
  if(reply.status!=='succeeded'||typeof reply.manifest_url!=='string')throw Error('服务返回的任务状态无效');
  if(version!==token)return;
  status('STEP 已生成，正在加载真实 STL 网格…');
  const result=await fetch(reply.manifest_url,{signal:controller.signal});
  if(!result.ok)throw Error('成果清单无法读取');
  const payload=await result.json();if(version!==token)return;
  await loadArtifacts(payload,version);
 }catch(error){
  if(version===token&&error.name!=='AbortError'){dispose();status('CAD 生成失败：'+error.message,true);}
 }finally{if(version===token){controller=null;$('generate').disabled=!available;}}
}
$('generate').addEventListener('click',generate);
$('resetParams').addEventListener('click',()=>{for(const [key,,value] of fields)$('param-'+key).value=String(value);
 for(const [key,,value] of cages)$('cage-'+key).value=String(value);$('cageEnabled').checked=true;dispose();status('已恢复演示参数；请重新生成 CAD');});
$('cageEnabled').addEventListener('change',()=>{$('cageParams').hidden=!$('cageEnabled').checked;});
for(const el of [...document.querySelectorAll('#parameters input,#cageParams input')])el.addEventListener('input',()=>{token++;controller?.abort();dispose();status('参数已更改，请重新生成以查看对应真实实体');});
for(const id of ['cutaway','transparent','explode'])$(id).addEventListener('input',applyVisualOptions);
$('viewReset').addEventListener('click',()=>{resetCamera();controls.reset();resetCamera();});
(async()=>{try{const response=await fetch('/api/v2/cad/status');const data=await response.json();
 available=response.ok&&data.available&&data.supported_bearings?.includes('rolling.deep_groove_ball');
 $('connection').textContent=available?'本地 OCCT 引擎在线':'CAD 引擎不可用';
 status(available?'输入参数并生成精确 CAD 模型':'未连接 CAD-V2 服务；请使用 python -m bearing_cad.api --static dist 启动',!available);
 }catch{$('connection').textContent='离线';status('CAD-V2 服务不可用，请启动本地 API',true);}
 $('generate').disabled=!available;})();
window.rollingViewerSnapshot=()=>({instances:entries.map(p=>({id:p.name,role:p.userData.role,visible:p.visible,position:p.position.toArray(),triangles:p.geometry.attributes.position.count/3,opacity:p.material.opacity})),requestHash:active?.manifest.request_hash??null});

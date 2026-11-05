import {ids} from './geometry.js';
import {validateExactRequest} from './cad03_geometry.js';
const $=id=>document.getElementById(id);
let version=0,controller=null,server=false;
const fields=['cad03HoleOn','cad03HoleD','cad03GrooveOn','cad03GrooveW','cad03GrooveDepth'];
function number(id){const s=$(id).value.trim();return s?Number(s):NaN;}
function params(){
 const b=window.bearingParams?.();if(!b)return null;const p={...b};
 if($('cad03HoleOn').checked)p.oil_feed_hole_d_mm=number('cad03HoleD');
 if($('cad03GrooveOn').checked){p.annular_groove_width_mm=number('cad03GrooveW');p.annular_groove_depth_mm=number('cad03GrooveDepth');}
 return p;
}
function display(msg,error=false){$('cad03Status').textContent=msg;$('cad03Status').style.color=error?'#a94429':'#345b79';}
function refresh(){
 $('cad03HoleD').disabled=!$('cad03HoleOn').checked;
 $('cad03GrooveW').disabled=!$('cad03GrooveOn').checked;
 $('cad03GrooveDepth').disabled=!$('cad03GrooveOn').checked;
 const p=params(),err=p?validateExactRequest(p):'基础参数无效';
 $('cad03Generate').disabled=!server||Boolean(err)||Boolean(controller);
 if(err)display(err,true);else if(!server)display('需运行 Python CAD 本地服务（当前只有示意预览）');else if(!controller)display('可生成 DRAFT 精确实体');
}
function invalidate(){
 version++;controller?.abort();controller=null;
 $('cad03Result').hidden=true;$('cad03Files').replaceChildren();$('cad03Views').replaceChildren();
 for(const id of ['saveSvg','saveDxf'])$(id).disabled=false;
 window.bearingRefresh?.();
 $('cad03Mode').textContent='当前：Three.js 参数化示意网格（不包含油孔油槽）';
 document.dispatchEvent(new CustomEvent('bearing:exact-clear'));refresh();
}
for(const id of [...ids,...fields]){
 $(id).addEventListener('input',invalidate);
 $(id).addEventListener('change',invalidate);
}
document.addEventListener('bearing:exact-loaded',()=>{$('cad03Mode').textContent='精确模型已就绪 · 来自 OCCT 实体';});
document.addEventListener('bearing:exact-error',e=>display('真实模型加载失败：'+e.detail,true));
$('cad03Generate').addEventListener('click',async()=>{
 const p=params(),e=p?validateExactRequest(p):'基础参数无效';if(e){display(e,true);return;}
 const n=++version;controller=new AbortController();refresh();display('OCCT 正在生成 STEP/STL/DXF/SVG…');
 try{
  const response=await fetch('/api/cad02/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p),signal:controller.signal});
  const d=await response.json();if(!response.ok)throw Error(d.error||'HTTP '+response.status);
  if(n!==version)return;
  if(d.approval_state!=='DRAFT'||!d.files?.['bushing.stl']||!d.files?.['bushing_section.stl']||!d.files?.['bearing_review_sheet.svg'])throw Error('CAD 成果清单不完整');
  $('cad03Files').replaceChildren();$('cad03Views').replaceChildren();
  for(const name of ['bearing_review_sheet.dxf','bearing_review_sheet.svg','bearing_assembly.step','housing.step','bushing.step','shaft.step','housing_section.step','bushing_section.step','shaft_section.step','artifact_manifest.json']){
   if(!d.files[name])continue;const a=document.createElement('a');a.href=d.files[name];a.download=name;a.textContent=name;$('cad03Files').append(a);
  }
  // Drawing is rendered in the main 2D viewport, not duplicated below.
  $('cad03Hash').textContent='SHA256: '+d.geometry_hash+' · '+d.generator_version+' · DRAFT';
  $('cad03Result').hidden=false;
  // The top-level 2D pane now shows the authoritative review sheet rather than
  // the independent CAD-01 schematic. Existing simple export buttons are disabled
  // to avoid exporting stale (or reference-only) geometry; use the file links.
  const preview=$('visual2d');
  preview.replaceChildren();
  const drawing=document.createElementNS('http://www.w3.org/2000/svg','image');
  drawing.setAttribute('width','680');drawing.setAttribute('height','480');
  drawing.setAttribute('href',d.files['bearing_review_sheet.svg']);
  preview.append(drawing);
  for(const id of ['saveSvg','saveDxf'])$(id).disabled=true;
  document.dispatchEvent(new CustomEvent('bearing:exact-ready',{detail:{files:d.files}}));
  const mode=document.querySelector('[name="workbenchMode"]:checked')?.value||'assembly';
  if(mode==='section')document.dispatchEvent(new CustomEvent('bearing:view-mode',{detail:{mode}}));
  display('精确 CAD 文件生成成功，正在加载实体网格');
 }catch(err){if(n===version&&err.name!=='AbortError')display('生成失败：'+err.message,true);}
 finally{if(n===version){controller=null;refresh();}}
});
(async()=>{try{const response=await fetch('/api/cad02/status');const d=await response.json();server=response.ok&&d.available&&d.approval_state==='DRAFT';}catch{server=false;}refresh();})();

for(const el of document.querySelectorAll('[name="workbenchMode"]'))el.addEventListener('change',()=>document.dispatchEvent(new CustomEvent('bearing:view-mode',{detail:{mode:el.value}})));

import {defaults,ids,nfmt,check,dxf} from './geometry.js';

(()=>{
'use strict';
const byId=id=>document.getElementById(id);
function params(){return Object.fromEntries(ids.map(id=>[id,byId(id).value.trim()===''?NaN:Number(byId(id).value)]));}
function shape2d(p){
 const axisX=213,axisY=235,scale=Math.min(2.12,230/p.housing_od_mm,310/(p.housing_length_mm+18)),ex=526;
 const H=p.housing_od_mm/2*scale,B=p.bush_od_mm/2*scale,I=(p.shaft_d_mm+2*p.radial_clearance_mm)/2*scale,S=p.shaft_d_mm/2*scale;
 const housingHL=p.housing_length_mm/2*scale,bushHL=p.length_mm/2*scale,shaftHL=(p.housing_length_mm+18)/2*scale;
 const rr=(x,y,w,h,fill,stroke='#38506e')=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width=".8"/>`;
 const line=(x1,y1,x2,y2,stroke='#405b77',dash='')=>`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}" stroke-width="1" ${dash?`stroke-dasharray="${dash}"`:''}/>`;
 let out=`<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="8" stroke="#7a8ca0" stroke-width="1"/></pattern><marker id="arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto-start-reverse"><path d="M0 0 L6 3 L0 6" fill="none" stroke="#395370" stroke-width="1"/></marker></defs>`;
 out+=`<rect width="680" height="480" fill="#f9fcff"/>`;
 out+=`<text x="22" y="31" font-size="18" font-weight="700" fill="#183651">圆柱径向滑动轴承 · 结构示意</text><text x="22" y="50" font-size="11" fill="#6b85a2">AXIAL SECTION · END VIEW · mm</text>`;
 for(let s of [-1,1]){
  out+=rr(axisX-housingHL,axisY+(s===-1?-H:B),housingHL*2,H-B,'#d9e2ed');
  out+=rr(axisX-housingHL,axisY+(s===-1?-H:B),housingHL*2,H-B,'url(#hatch)','none');
  out+=rr(axisX-bushHL,axisY+(s===-1?-B:I),bushHL*2,B-I,'#78abe1');
 }
 out+=rr(axisX-shaftHL,axisY-S,shaftHL*2,2*S,'#aed5c0','#267651');
 out+=line(40,axisY,394,axisY,'#b34c62','12 5 3 5');
 const dimY=axisY-H-33;out+=line(axisX-bushHL,dimY-8,axisX-bushHL,axisY-H+7)+line(axisX+bushHL,dimY-8,axisX+bushHL,axisY-H+7);
 out+=`<line x1="${axisX-bushHL}" y1="${dimY}" x2="${axisX+bushHL}" y2="${dimY}" stroke="#395370" stroke-width="1" marker-start="url(#arrow)" marker-end="url(#arrow)"/><text x="${axisX}" y="${dimY-6}" text-anchor="middle" font-size="12" font-weight="700" fill="#245d99">L = ${nfmt(p.length_mm)}</text>`;
 out+=`<text x="${axisX-housingHL}" y="${axisY+H+27}" font-size="13" fill="#5d7087">轴向剖视图 A-A</text>`;
 for(const [r,fill] of [[H,'#d9e2ed'],[B,'#78abe1'],[I,'#f9fcff'],[S,'#aed5c0']])out+=`<circle cx="${ex}" cy="${axisY}" r="${r}" fill="${fill}" stroke="#34516f" stroke-width="1.1"/>`;
 out+=line(ex-H-10,axisY,ex+H+10,axisY,'#b34c62','10 4 2 4')+line(ex,axisY-H-10,ex,axisY+H+10,'#b34c62','10 4 2 4');
 out+=`<text x="${ex}" y="${axisY+H+27}" text-anchor="middle" font-size="13" fill="#5d7087">端面视图</text>`;
 out+=`<rect x="17" y="375" width="646" height="83" fill="#eef5fd" stroke="#dae7f2" rx="7"/><text x="30" y="399" font-size="13" fill="#2d5177">轴颈 ⌀${nfmt(p.shaft_d_mm)}　轴瓦内孔 ⌀${nfmt(p.shaft_d_mm+2*p.radial_clearance_mm)}　径向间隙 c = ${nfmt(p.radial_clearance_mm)}</text>`;
 out+=`<text x="30" y="420" font-size="12" fill="#477196">轴瓦外径 ⌀${nfmt(p.bush_od_mm)}　轴承座外径 ⌀${nfmt(p.housing_od_mm)}　座宽 ${nfmt(p.housing_length_mm)}</text>`;
 out+=`<text x="30" y="441" font-size="10" fill="#8b5874">演示级结构示意，间隙保持真实比例；非国家标准制造图 / 未经校核</text>`;
 byId('visual2d').dataset.scale=scale;byId('visual2d').innerHTML=out;
}
function refresh(){const p=params(),err=check(p);byId('error').style.display=err?'block':'none';byId('error').textContent=err||'';byId('ok').style.display=err?'none':'block';
 byId('previewInvalid').style.display=err?'block':'none';byId('viewgrid').classList.toggle('preview-invalid',Boolean(err));
 document.querySelectorAll('#viewgrid .toolbar input,#viewgrid .toolbar button').forEach(el=>el.disabled=Boolean(err));
 document.querySelectorAll('[data-export]').forEach(button=>button.disabled=Boolean(err));
 if(err){byId('visual2d').innerHTML='';byId('calcs').textContent='等待有效参数';document.dispatchEvent(new CustomEvent('bearing:invalid'));return;}
 byId('calcs').innerHTML=`轴瓦内孔 <em>⌀${nfmt(p.shaft_d_mm+2*p.radial_clearance_mm)} mm</em><br/>直径间隙 <em>${nfmt(2*p.radial_clearance_mm)} mm</em><br/>轴瓦壁厚 <em>${nfmt((p.bush_od_mm-p.shaft_d_mm-2*p.radial_clearance_mm)/2)} mm</em>`;
 shape2d(p);document.dispatchEvent(new CustomEvent('bearing:change',{detail:p}));}
 function download(filename,mime,txt){const url=URL.createObjectURL(new Blob([txt],{type:mime}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),500);}
 byId('saveJson').dataset.export='';byId('saveSvg').dataset.export='';byId('saveDxf').dataset.export='';
 byId('saveJson').addEventListener('click',()=>{const p=params();if(check(p))return;download('bearing_parameters.json','application/json',JSON.stringify(p,null,2));});
 byId('saveSvg').addEventListener('click',()=>{const p=params();if(check(p))return;const s=new XMLSerializer().serializeToString(byId('visual2d'));download('bearing_section.svg','image/svg+xml;charset=utf-8',s);});
 byId('saveDxf').addEventListener('click',()=>{const p=params();if(check(p))return;download('bearing_section.dxf','application/dxf',dxf(p));});
 ids.forEach(id=>byId(id).addEventListener('input',refresh));byId('reset').addEventListener('click',()=>{ids.forEach(id=>byId(id).value=defaults[id]);refresh();});
 window.bearingParams=()=>check(params())?null:params();window.bearingRefresh=refresh;refresh();
})();

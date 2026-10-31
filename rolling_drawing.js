// Original RoBAS DWG four-sheet actions, independent from existing 3D viewer.
export function initDrawingWorkbench(getDesign) {
  const $ = name => document.getElementById(name);
  const button=$('generate2d');
  const status=$('drawingStatus');
  const downloads=$('drawingDownloads');
  let online=false;
  let allowed=new Set();
  let busy=false;
  function update(message, error=false){
    status.textContent=message;
    status.classList.toggle('error',error);
    const designType=$('bearingType').value;
    const variant=document.getElementById('param-configuration')?.value;
    const supported=designType==='rolling.cylindrical_roller'
      ?allowed.has(designType+':'+variant):allowed.has(designType);
    button.disabled=!online||!supported||busy;
    if(online&&!supported&&!busy)status.textContent='RoBAS 当前仅支持圆柱滚子 N 型原版模板';
  }
  function clear(){downloads.replaceChildren();}
  async function refresh(){
    try{
      const response=await fetch('/api/v2/cad/drawings/status',{cache:'no-store'});
      const data=await response.json();
      online=response.ok&&data.available===true;
      allowed=new Set(data.supported_bearings||[]);
      update(online?'原版 RoBAS DWG 图纸服务已配置':'本机未配置 Windows/CADImport 原版出图引擎',!online);
    }catch{
      online=false;update('RoBAS 二维图纸服务暂不可用',true);
    }
  }
  button.addEventListener('click',async()=>{
    if(button.disabled)return;
    busy=true;update('正在使用原始 DWG 模板生成四张 DXF…');clear();
    try{
      const drawing={
        model:$('drawingModel').value.trim(),
        accuracy_class:$('drawingAccuracy').value,
        diameter_series:$('drawingSeries').value,
      };
      if(!drawing.model)throw Error('请填写轴承型号');
      for(const [id,key] of [['drawingChamfer1','chamfer1_mm'],
                              ['drawingChamfer2','chamfer2_mm']]){
        const raw=$(id).value.trim();
        if(raw){
          const number=Number(raw);
          if(!Number.isFinite(number)||number<=0)throw Error('倒角应为正数');
          drawing[key]=number;
        }
      }
      const design=getDesign();
      const response=await fetch('/api/v2/cad/drawings',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({design,drawing}),
      });
      const reply=await response.json();
      if(!response.ok)throw Error(reply?.error?.message||'二维出图失败');
      const manifestResponse=await fetch(reply.manifest_url,{cache:'no-store'});
      if(!manifestResponse.ok)throw Error('DXF 成果清单不可用');
      const results=await manifestResponse.json();
      if(results.manifest?.request_hash!==reply.request_hash)throw Error('成果参数不一致');
      for(const sheet of results.manifest.sheets){
        const url=results.file_urls?.[sheet.file];
        if(!url)throw Error('缺少 '+sheet.file+' 下载地址');
        const link=document.createElement('a');
        link.href=url;link.download=sheet.file;link.textContent=sheet.file;
        downloads.append(link);
      }
      update('已按原版模板生成四张 DXF（未作制造批准）');
    }catch(error){
      clear();update('二维出图失败：'+error.message,true);
    }finally{busy=false;update(status.textContent,status.classList.contains('error'));}
  });
  $('bearingType').addEventListener('change',()=>{
    clear();update(online?'选择轴承构型后可生成原版 DXF':'RoBAS 出图引擎未配置',!online);
  });
  $('parameters').addEventListener('change',()=>{
    clear();update(online?'参数已改变；可重新生成原版 DXF':'RoBAS 出图引擎未配置',!online);
  });
  refresh();
}

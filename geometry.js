export const defaults={shaft_d_mm:50,radial_clearance_mm:0.05,bush_od_mm:70,length_mm:50,housing_od_mm:86,housing_length_mm:60};
export const ids=Object.keys(defaults);
export const nfmt=x=>Number(x).toFixed(3).replace(/0+$/,'').replace(/\.$/,'');
export function check(p){
 if(ids.some(k=>typeof p[k]!=='number'||!Number.isFinite(p[k])))return '请填写所有数值';
 if(ids.some(k=>Math.abs(p[k]*1000-Math.round(p[k]*1000))>1e-7))return '设计尺寸最多保留三位小数（精度 0.001 mm）';
 if(p.shaft_d_mm<15||p.shaft_d_mm>120)return '轴颈直径范围：15 至 120 mm';
 if(p.radial_clearance_mm<.005||p.radial_clearance_mm>.3)return '径向间隙范围：0.005 至 0.3 mm';
 if(p.bush_od_mm>160||p.housing_od_mm>200)return '演示范围：轴瓦外径不大于 160 mm，座外径不大于 200 mm';
 if(p.bush_od_mm<=p.shaft_d_mm+2*p.radial_clearance_mm+4)return '轴瓦壁厚需大于 2 mm';
 if(p.housing_od_mm<=p.bush_od_mm+6)return '轴承座壁厚需大于 3 mm';
 if(p.length_mm<15||p.length_mm>150)return '轴瓦宽度范围：15 至 150 mm';
 if(p.housing_length_mm<p.length_mm||p.housing_length_mm>180)return '轴承座宽度需不小于轴瓦宽度且不大于 180 mm';
 return null;
}

export function dxf(p){const error=check(p);if(error)throw new Error(error);const seq=[];function pair(k,v){seq.push(String(k),String(v));}function begin(kind,layer){pair(0,kind);pair(8,layer);}
 function line(x1,y1,x2,y2,layer='OUTLINE'){begin('LINE',layer);pair(10,x1);pair(20,y1);pair(30,0);pair(11,x2);pair(21,y2);pair(31,0);}
 function rectangle(x1,y1,x2,y2,layer){line(x1,y1,x2,y1,layer);line(x2,y1,x2,y2,layer);line(x2,y2,x1,y2,layer);line(x1,y2,x1,y1,layer);}
 function circle(x,y,r,layer){begin('CIRCLE',layer);pair(10,x);pair(20,y);pair(30,0);pair(40,r);}
 function text(t,x,y,size=2.5){begin('TEXT','TEXT');pair(10,x);pair(20,y);pair(30,0);pair(40,size);pair(1,t);}
 function tube(od,id,len,lay){for(const sign of [-1,1]){const a=sign*od/2,b=sign*id/2;rectangle(-len/2,Math.min(a,b),len/2,Math.max(a,b),lay);}}
 pair(0,'SECTION');pair(2,'HEADER');pair(9,'$ACADVER');pair(1,'AC1015');pair(9,'$INSUNITS');pair(70,4);pair(9,'$MEASUREMENT');pair(70,1);pair(0,'ENDSEC');pair(0,'SECTION');pair(2,'TABLES');pair(0,'TABLE');pair(2,'LTYPE');pair(5,'10');pair(70,1);pair(0,'LTYPE');pair(2,'CONTINUOUS');pair(70,0);pair(3,'Solid line');pair(72,65);pair(73,0);pair(40,0);pair(0,'ENDTAB');pair(0,'TABLE');pair(2,'LAYER');pair(5,'11');pair(70,7);for(const [name,color] of [['0',7],['HOUSING',8],['BUSHING',5],['SHAFT',3],['CENTER',1],['DIM',2],['TEXT',7]]){pair(0,'LAYER');pair(2,name);pair(70,0);pair(62,color);pair(6,'CONTINUOUS');}pair(0,'ENDTAB');pair(0,'ENDSEC');pair(0,'SECTION');pair(2,'ENTITIES');
 tube(p.housing_od_mm,p.bush_od_mm,p.housing_length_mm,'HOUSING');tube(p.bush_od_mm,p.shaft_d_mm+2*p.radial_clearance_mm,p.length_mm,'BUSHING');rectangle(-(p.housing_length_mm+18)/2,-p.shaft_d_mm/2,(p.housing_length_mm+18)/2,p.shaft_d_mm/2,'SHAFT');
 line(-(p.housing_length_mm+25)/2,0,(p.housing_length_mm+25)/2,0,'CENTER');
 const ex=Math.max(p.housing_length_mm+18,p.housing_od_mm)*1.85;
 for(const [dia,l] of [[p.housing_od_mm,'HOUSING'],[p.bush_od_mm,'BUSHING'],[p.shaft_d_mm+2*p.radial_clearance_mm,'BUSHING'],[p.shaft_d_mm,'SHAFT']])circle(ex,0,dia/2,l);
 line(ex-p.housing_od_mm/2-5,0,ex+p.housing_od_mm/2+5,0,'CENTER');
 const y=p.housing_od_mm/2+14;line(-p.length_mm/2,y,p.length_mm/2,y,'DIM');line(-p.length_mm/2,p.housing_od_mm/2+2,-p.length_mm/2,y+4,'DIM');line(p.length_mm/2,p.housing_od_mm/2+2,p.length_mm/2,y+4,'DIM');
 text(`L = ${nfmt(p.length_mm)} mm`,-p.length_mm/2,y+4);text(`SHAFT DIA = ${nfmt(p.shaft_d_mm)} mm`,-p.housing_length_mm/2,-p.housing_od_mm/2-11);
 text(`BORE DIA = ${nfmt(p.shaft_d_mm+2*p.radial_clearance_mm)} mm`,-p.housing_length_mm/2,-p.housing_od_mm/2-16);text(`RADIAL CLEARANCE = ${nfmt(p.radial_clearance_mm)} mm`,-p.housing_length_mm/2,-p.housing_od_mm/2-21);
 text(`BUSH OD = ${nfmt(p.bush_od_mm)} mm`, -p.housing_length_mm/2,-p.housing_od_mm/2-26);text(`HOUSING OD = ${nfmt(p.housing_od_mm)} mm; HOUSING LENGTH = ${nfmt(p.housing_length_mm)} mm`, -p.housing_length_mm/2,-p.housing_od_mm/2-31);text('DEMO SCHEMATIC ONLY - NOT A RELEASED ENGINEERING DRAWING',-p.housing_length_mm/2,-p.housing_od_mm/2-38,2);pair(0,'ENDSEC');pair(0,'EOF');return seq.join('\n')+'\n';}
export function dimensions(p){return {bore:p.shaft_d_mm+2*p.radial_clearance_mm,shaftLength:p.housing_length_mm+18};}

// Pure presentation layer. All geometric dimensions are mm, no AI-authored CAD geometry.
// Three.js and OrbitControls are bundled locally by Vite for offline demonstrations.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

const canvasArea=document.getElementById('stage');
const fallback=document.getElementById('fallback');
try {
  const scene=new THREE.Scene();scene.background=new THREE.Color('#edf4fb');
  const camera=new THREE.PerspectiveCamera(35,1,.1,1800);camera.position.set(154,116,160);
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.setSize(canvasArea.clientWidth,canvasArea.clientHeight);
  canvasArea.prepend(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,0,0);controls.minDistance=60;controls.maxDistance=900;controls.update();
  scene.add(new THREE.HemisphereLight('#ffffff','#b2c4d9',2.0));
  const k=new THREE.DirectionalLight('#ffffff',2.4);k.position.set(130,100,185);scene.add(k);
  const fill=new THREE.DirectionalLight('#a6caff',.8);fill.position.set(-110,-60,-95);scene.add(fill);
  const ground=new THREE.GridHelper(270,14,0xaac4da,0xd9e6f1);ground.rotation.x=Math.PI/2;ground.position.z=-80;scene.add(ground);
  let objects=[];
  let exactMeshes=[];let exactMode='assembly';let exactFiles=null;let loadSerial=0;const exactGroup=new THREE.Group();scene.add(exactGroup);
  function clearExact(){loadSerial++;for(const obj of exactMeshes){exactGroup.remove(obj);obj.geometry.dispose();obj.material.dispose();}exactMeshes=[];meshes.visible=true;}
  document.addEventListener('bearing:exact-clear',clearExact);
  document.addEventListener('bearing:change',clearExact);
  document.addEventListener('bearing:invalid',clearExact);
  document.addEventListener('bearing:exact-ready',async(event)=>{
    exactFiles=event.detail.files;await loadExact();
  });
  document.addEventListener('bearing:view-mode',async(e)=>{exactMode=e.detail.mode==='section'?'section':'assembly';if(exactFiles)await loadExact();});
  async function loadExact(){
    clearExact();const serial=loadSerial;
    const loader=new STLLoader(),files=exactFiles;
    if(!files)return;
    try{
      const geometries=await Promise.all(['housing','bushing','shaft'].map(async name=>{
        const response=await fetch(files[name+(exactMode==='section'?'_section':'')+'.stl'],{cache:'no-store'});if(!response.ok)throw Error(name+' STL HTTP '+response.status);
        return loader.parse(await response.arrayBuffer());
      }));
      if(serial!==loadSerial){geometries.forEach(g=>g.dispose());return;}
      geometries.forEach((geometry,i)=>{
        geometry.computeVertexNormals();
        const obj=new THREE.Mesh(geometry,mat(['#b7c4d6','#3b8cda','#69b69a'][i],false));
        exactGroup.add(obj);exactMeshes.push(obj);
      });
      meshes.visible=false;syncExact();fitCamera(true);
      document.dispatchEvent(new CustomEvent('bearing:exact-loaded'));
    }catch(err){if(serial===loadSerial){clearExact();document.dispatchEvent(new CustomEvent('bearing:exact-error',{detail:err.message}));}}
  }
  function syncExact(){if(exactMeshes.length!==3)return;
    for(let i=0;i<3;i++){exactMeshes[i].visible=document.getElementById(['showHousing','showBushing','showShaft'][i]).checked;
      const transparent=document.getElementById('transparent').checked;
      exactMeshes[i].material.transparent=transparent;exactMeshes[i].material.opacity=transparent?.48:1;
      exactMeshes[i].material.depthWrite=!transparent;
    }
    const p=window.bearingParams?.();if(!p)return;
    const t=Number(document.getElementById('explode').value)/100;
    exactMeshes[0].position.z=-(p.housing_length_mm*.66+14)*t;
    exactMeshes[1].position.z=0;
    exactMeshes[2].position.z=(p.housing_length_mm*.78+17)*t;
  }
  function fitCamera(exact=false){
    const p=window.bearingParams?.();if(!p)return;
    const extent=Math.max(p.housing_od_mm,p.housing_length_mm+18);
    const distance=extent*2.45;
    camera.position.set(distance*.75,distance*.58,distance*.82);
    controls.target.set(0,0,0);controls.update();
  }

  const meshes=new THREE.Group();scene.add(meshes);
  const mat=(color,transparent)=>new THREE.MeshStandardMaterial({color,metalness:.34,roughness:.35,side:THREE.DoubleSide,transparent,opacity:transparent?.48:1,depthWrite:!transparent});
  function ring(outer,inner,length,section,color,alpha){
    const shape=new THREE.Shape();
    if(section){const a=.34,b=Math.PI*2-.34;
      shape.moveTo(outer*Math.cos(a),outer*Math.sin(a));shape.absarc(0,0,outer,a,b,false);
      shape.lineTo(inner*Math.cos(b),inner*Math.sin(b));shape.absarc(0,0,inner,b,a,true);shape.closePath();
    }else{shape.absarc(0,0,outer,0,2*Math.PI,false);const hole=new THREE.Path();hole.absarc(0,0,inner,0,2*Math.PI,true);shape.holes.push(hole);}
    const geom=new THREE.ExtrudeGeometry(shape,{depth:length,steps:1,bevelEnabled:false,curveSegments:96});geom.translate(0,0,-length/2);
    return new THREE.Mesh(geom,mat(color,alpha));
  }
  function solid(radius,length,color,alpha){const g=new THREE.CylinderGeometry(radius,radius,length,96,1,false);g.rotateX(Math.PI/2);return new THREE.Mesh(g,mat(color,alpha));}
  function clearMeshes(){for(const obj of objects){meshes.remove(obj);obj.geometry.dispose();obj.material.dispose();}objects=[];}
  function remake(){const p=window.bearingParams?.();if(!p){clearMeshes();return;}
    clearMeshes();
    const cut=document.getElementById('cutaway').checked,transparent=document.getElementById('transparent').checked;
    const housing=ring(p.housing_od_mm/2,p.bush_od_mm/2,p.housing_length_mm,cut,'#b7c4d6',transparent);
    const bush=ring(p.bush_od_mm/2,(p.shaft_d_mm+2*p.radial_clearance_mm)/2,p.length_mm,cut,'#3b8cda',transparent);
    const shaft=solid(p.shaft_d_mm/2,p.housing_length_mm+18,'#69b69a',false);
    objects=[housing,bush,shaft];for(const obj of objects)meshes.add(obj);
    objects[0].visible=document.getElementById('showHousing').checked;
    objects[1].visible=document.getElementById('showBushing').checked;
    objects[2].visible=document.getElementById('showShaft').checked;
    const maxD=Math.max(p.housing_od_mm,p.housing_length_mm);camera.far=1400;camera.updateProjectionMatrix();ground.position.z=-Math.max(80,maxD);explode();fitCamera();
  }
  function explode(){syncExact();if(objects.length!==3)return;const p=window.bearingParams?.();if(!p)return;
    const t=Number(document.getElementById('explode').value)/100;
    objects[0].position.z=-(p.housing_length_mm*.66+14)*t;
    objects[1].position.z=0;
    objects[2].position.z=(p.housing_length_mm*.78+17)*t;
  }
  const obs=new ResizeObserver(()=>{const w=canvasArea.clientWidth,h=canvasArea.clientHeight;if(w<=0||h<=0)return;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);});obs.observe(canvasArea);
  document.addEventListener('bearing:change',remake);
  document.addEventListener('bearing:invalid',clearMeshes);
  // Read-only scene diagnostics used by integration tests; never exposes mutable meshes.
  window.bearingViewerSnapshot=()=>({
    canvasWidth: renderer.domElement.width,
    canvasHeight: renderer.domElement.height,
    exactMode,
    exactParts:exactMeshes.map((obj,i)=>({name:['housing','bushing','shaft'][i],visible:obj.visible,positionZ:obj.position.z,vertexCount:obj.geometry.attributes.position.count})),
    parts: objects.map((obj,i)=>{
      obj.geometry.computeBoundingBox();
      const b=obj.geometry.boundingBox;
      return {
        name:['housing','bushing','shaft'][i],
        visible:obj.visible,
        transparent:obj.material.transparent,
        opacity:obj.material.opacity,
        positionZ:obj.position.z,
        vertexCount:obj.geometry.getAttribute('position').count,
        diameterX:b.max.x-b.min.x,
        widthZ:b.max.z-b.min.z
      };
    })
  });
  for(const id of ['cutaway','transparent','showHousing','showBushing','showShaft'])document.getElementById(id).addEventListener('change',()=>{if(exactMeshes.length){syncExact();return;}remake();});
  document.getElementById('explode').addEventListener('input',explode);
  document.getElementById('viewReset').addEventListener('click',()=>fitCamera());
  remake();
  function frame(){requestAnimationFrame(frame);controls.update();renderer.render(scene,camera);}frame();
}catch(error){
  console.warn('Three.js initialization unavailable:',error);
  fallback.style.display='flex';
}

#!/usr/bin/env python3
"""Parametric plain journal bearing CAD demo (mm). Not a manufacturing release drawing.

Input is an independently validated frozen parameter set. Outputs do not change
any V3.1 confirmation state. CadQuery (OCCT) produces B-Rep STEP and STL; ezdxf
produces a vector axial-section schematic with dimension text.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import math

@dataclass(frozen=True)
class Bearing:
    shaft_d_mm: float
    radial_clearance_mm: float
    bush_od_mm: float
    length_mm: float
    housing_od_mm: float
    housing_length_mm: float

    @property
    def bore_d_mm(self):
        return self.shaft_d_mm + 2 * self.radial_clearance_mm

    @property
    def shaft_length_mm(self):
        return self.housing_length_mm + 18

    def validate(self):
        vals = vars(self)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vals.values()):
            raise ValueError('All input values must be finite numbers')
        if any(abs(v * 1000 - round(v * 1000)) > 1e-7 for v in vals.values()):
            raise ValueError('All dimensions must be expressible to 0.001 mm precision')
        if not (15 <= self.shaft_d_mm <= 120):
            raise ValueError('shaft_d_mm must be 15..120 mm (demo limit)')
        if not (0.005 <= self.radial_clearance_mm <= 0.3):
            raise ValueError('radial clearance must be 0.005..0.3 mm (demo limit)')
        if self.bush_od_mm > 160 or self.housing_od_mm > 200:
            raise ValueError('Demo limit: bushing OD <= 160 mm and housing OD <= 200 mm')
        if self.bush_od_mm <= self.bore_d_mm + 4:
            raise ValueError('bush_od_mm needs >2mm radial bushing wall')
        if self.housing_od_mm <= self.bush_od_mm + 6:
            raise ValueError('housing_od_mm needs >3mm radial wall')
        if not (15 <= self.length_mm <= 150):
            raise ValueError('length_mm must be 15..150')
        if self.housing_length_mm < self.length_mm:
            raise ValueError('housing_length_mm must be >= bush length')
        if self.housing_length_mm > 180:
            raise ValueError('housing_length_mm must be <= 180')
        return self


def cad_models(b: Bearing):
    import cadquery as cq
    def tube(od, inner, length):
        return (cq.Workplane('XY').circle(od/2).circle(inner/2)
                .extrude(length).translate((0, 0, -length/2)))
    return {
        'housing': tube(b.housing_od_mm,b.bush_od_mm,b.housing_length_mm),
        'bushing': tube(b.bush_od_mm,b.bore_d_mm,b.length_mm),
        'shaft': (cq.Workplane('XY').circle(b.shaft_d_mm/2)
                  .extrude(b.shaft_length_mm).translate((0,0,-b.shaft_length_mm/2))),
    }


def make_dxf(b: Bearing, dest: Path):
    import ezdxf
    doc = ezdxf.new('R2010', setup=True)
    doc.units = ezdxf.units.MM
    for name,color in [('HOUSING',8),('BUSHING',5),('SHAFT',3),('CENTER',1),('DIM',2),('NOTES',7)]:
        doc.layers.new(name, dxfattribs={'color':color})
    m = doc.modelspace()
    def line(a, c, layer):m.add_line(a,c,dxfattribs={'layer':layer})
    def rect_rim(outerR,innerR,L,layer):
        for sign in (-1,1):
            x0,x1 = -L/2,L/2
            r0,r1 = sign*innerR,sign*outerR
            pts=[(x0,r0),(x1,r0),(x1,r1),(x0,r1)]
            m.add_lwpolyline(pts,close=True,dxfattribs={'layer':layer})
    rect_rim(b.housing_od_mm/2,b.bush_od_mm/2,b.housing_length_mm,'HOUSING')
    rect_rim(b.bush_od_mm/2,b.bore_d_mm/2,b.length_mm,'BUSHING')
    x0,x1=-b.shaft_length_mm/2,b.shaft_length_mm/2
    m.add_lwpolyline([(x0,-b.shaft_d_mm/2),(x1,-b.shaft_d_mm/2),(x1,b.shaft_d_mm/2),(x0,b.shaft_d_mm/2)],close=True,dxfattribs={'layer':'SHAFT'})
    line((-x1-7,0),(x1+7,0),'CENTER')
    def txt(t,pos,height=2.2,layer='DIM'):
        m.add_text(t,dxfattribs={'height':height,'insert':pos,'layer':layer})
    y=b.housing_od_mm/2 + 11
    for x in [-b.length_mm/2,b.length_mm/2]:line((x,b.housing_od_mm/2+2),(x,y+3),'DIM')
    line((-b.length_mm/2,y),(b.length_mm/2,y),'DIM')
    txt(f'L = {b.length_mm:g} mm',(-b.length_mm/2,y+3))
    # Standard CAD dimension annotations deliberately deferred: current DXF is schematic.
    txt(f'SHAFT DIA = {b.shaft_d_mm:g} mm',(-x1,-b.housing_od_mm/2-12))
    txt(f'BORE DIA = {b.bore_d_mm:.3f} mm',(-x1,-b.housing_od_mm/2-17))
    txt(f'RADIAL CLEARANCE = {b.radial_clearance_mm:g} mm',(-x1,-b.housing_od_mm/2-22))
    txt(f'BUSH OD = {b.bush_od_mm:g} mm',(-x1,-b.housing_od_mm/2-27))
    txt('DEMO SCHEMATIC - NOT A RELEASED MANUFACTURING DRAWING',(-x1,-b.housing_od_mm/2-35),2.5,'NOTES')
    # End view
    ex=max(b.shaft_length_mm, b.housing_od_mm)*1.8
    for diameter,lay in [(b.housing_od_mm,'HOUSING'),(b.bush_od_mm,'BUSHING'),(b.bore_d_mm,'BUSHING'),(b.shaft_d_mm,'SHAFT')]:
        m.add_circle((ex,0),diameter/2,dxfattribs={'layer':lay})
    line((ex-b.housing_od_mm/2-6,0),(ex+b.housing_od_mm/2+6,0),'CENTER')
    line((ex,-b.housing_od_mm/2-6),(ex,b.housing_od_mm/2+6),'CENTER')
    doc.saveas(str(dest))
    # Reopen and audit file to verify serialized DXF format.
    check=ezdxf.readfile(str(dest)); auditor=check.audit()
    if auditor.has_errors:raise RuntimeError('DXF audit failed: '+str(auditor.errors[:3]))


def make_svg(b: Bearing, dest: Path):
    # Static vector schematic. Browser demo also renders SVG parametrically.
    import svgwrite
    svg=svgwrite.Drawing(str(dest), size=('1200px','650px'), viewBox='0 0 1200 650')
    svg.attribs['font-family'] = 'Noto Sans CJK SC, Microsoft YaHei, sans-serif'
    svg.add(svg.rect(insert=(0,0),size=(1200,650),fill='#f8fbff'))
    svg.add(svg.text('圆柱径向滑动轴承 · 参数化二维剖视图', insert=(44,48),font_size=29,font_weight='bold',fill='#15263d'))
    svg.add(svg.text('DEMO / axial section + end view / dimensions in mm',insert=(44,76),font_size=14,fill='#5b7090'))
    center_x, center_y,scale=320,314,min(3.0,360/b.housing_od_mm)
    def ringrect(od,id,L,color):
        outer=od/2*scale;inner=id/2*scale
        for sign in (-1,1):
            cy=center_y - sign*(outer+inner)/2
            svg.add(svg.rect(insert=(center_x-L/2*scale,cy-(outer-inner)/2),size=(L*scale,outer-inner),fill=color,stroke='#31465d',stroke_width=.8))
    ringrect(b.housing_od_mm,b.bush_od_mm,b.housing_length_mm,'#dbe4f0')
    ringrect(b.bush_od_mm,b.bore_d_mm,b.length_mm,'#7aaee4')
    svg.add(svg.rect(insert=(center_x-b.shaft_length_mm/2*scale,center_y-b.shaft_d_mm/2*scale),size=(b.shaft_length_mm*scale,b.shaft_d_mm*scale),fill='#bfd6ca',stroke='#234d3c',stroke_width=1))
    svg.add(svg.line(start=(92,center_y),end=(548,center_y),stroke='#ad4158',stroke_dasharray='14,5,3,5'))
    x0=center_x-b.length_mm/2*scale;x1=center_x+b.length_mm/2*scale
    top=center_y-b.housing_od_mm/2*scale-30
    for x in [x0,x1]:svg.add(svg.line(start=(x,top-4),end=(x,center_y-b.housing_od_mm/2*scale+9),stroke='#223c61',stroke_width=1))
    svg.add(svg.line(start=(x0,top),end=(x1,top),stroke='#223c61',stroke_width=1))
    svg.add(svg.text(f'L = {b.length_mm:g}',insert=(center_x-38,top-8),font_size=16,fill='#163956'))
    svg.add(svg.text(f'φ {b.housing_od_mm:g}',insert=(68,center_y),font_size=17,fill='#163956'))
    svg.add(svg.text(f'φ {b.bush_od_mm:g}',insert=(82,center_y+24),font_size=16,fill='#195f9f'))
    svg.add(svg.text(f'φ {b.shaft_d_mm:g}',insert=(445,center_y+22),font_size=16,fill='#1a765b'))
    endx,endy=865,314
    for d,color in [(b.housing_od_mm,'#dbe4f0'),(b.bush_od_mm,'#7aaee4'),(b.bore_d_mm,'#f8fbff'),(b.shaft_d_mm,'#bfd6ca')]:
        svg.add(svg.circle(center=(endx,endy),r=d/2*scale,fill=color,stroke='#294b72',stroke_width=1.2))
    svg.add(svg.line(start=(endx-145,endy),end=(endx+145,endy),stroke='#ad4158',stroke_dasharray='12,5,3,5'))
    svg.add(svg.line(start=(endx,endy-145),end=(endx,endy+145),stroke='#ad4158',stroke_dasharray='12,5,3,5'))
    svg.add(svg.text('轴向剖视图',insert=(258,532),font_size=18,font_weight='bold',fill='#203956'))
    svg.add(svg.text('端面视图',insert=(823,532),font_size=18,font_weight='bold',fill='#203956'))
    svg.add(svg.text(f'径向间隙 c = {b.radial_clearance_mm:g} mm  |  轴瓦内孔 = {b.bore_d_mm:.3f} mm',insert=(56,575),font_size=18,fill='#194c86'))
    svg.add(svg.text('说明：间隙按真实比例建模，因此在缩略视图中不易辨识；仅用于方案展示，非可制造工程图。',insert=(56,608),font_size=14,fill='#7f5870'))
    svg.save()


def generate(b: Bearing, directory: Path):
    b.validate()
    directory.mkdir(parents=True,exist_ok=True)
    models=cad_models(b)
    import cadquery as cq
    assy=cq.Assembly(name='PlainJournalBearingDemo')
    for name,color in [('housing',cq.Color(0.73,0.79,0.87)),('bushing',cq.Color(0.20,0.53,0.84)),('shaft',cq.Color(0.43,0.72,0.55))]:
        assy.add(models[name],name=name,color=color)
        models[name].export(str(directory/f'{name}.step'))
        models[name].export(str(directory/f'{name}.stl'))
    assy.export(str(directory/'bearing_assembly.step'))
    make_dxf(b,directory/'bearing_section.dxf')
    make_svg(b,directory/'bearing_section.svg')
    (directory/'design_snapshot.json').write_text(json.dumps({**vars(b),'bore_d_mm':b.bore_d_mm,'status':'DEMO_UNVERIFIED','geometry_unit':'mm'},ensure_ascii=False,indent=2),encoding='utf-8')
    canonical=json.dumps(vars(b),sort_keys=True,separators=(',',':'),ensure_ascii=False)
    manifest={'generator':'BearingCAD-Demo/0.1.0','approval_state':'DRAFT',
              'geometry_hash_sha256':hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
              'geometry_unit':'mm','files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                           for f in sorted(directory.iterdir()) if f.is_file() and f.name!='artifact_manifest.json'}}
    (directory/'artifact_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Generated',directory,'files: ',*[f.name for f in directory.iterdir()])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--params',default='sample_params.json')
    parser.add_argument('--out',default='outputs')
    args=parser.parse_args()
    data=json.loads(Path(args.params).read_text(encoding='utf-8'))
    generate(Bearing(**data),Path(args.out))
if __name__=='__main__':main()

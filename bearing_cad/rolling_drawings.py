"""Draft rolling-bearing 2-D sheets generated from the *same* OCCT solids as STEP.

RoBAS used fixed DWG placeholders. Its DWGs are not supplied with RoBAS.zip;
this independent SVG/DXF review drawing therefore does not claim DWG equivalence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq
import ezdxf
import svgwrite

DRAWING_VERSION = "rolling-2d-review/1"
SHEET_MM = (420, 297)  # A3 landscape; geometry is *scaled to fit*.


def _wire_vertices(wire):
    """Discretize curved OCCT edges and join their ordered end points."""
    segments = []
    for edge in wire.Edges():
        n = max(3, min(320, math.ceil(edge.Length() / 0.25) + 1))
        vertices = edge.sample(n)[0]
        pts = [(float(p.z), float(p.x)) for p in vertices]
        if len(pts) >= 2:
            segments.append(pts)
    if not segments:
        return []
    points = segments.pop(0)
    def distance(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    while segments:
        j = min(range(len(segments)), key=lambda i: min(distance(points[-1], segments[i][0]),
                                                        distance(points[-1], segments[i][-1])))
        part = segments.pop(j)
        if distance(points[-1], part[-1]) < distance(points[-1], part[0]):
            part.reverse()
        if distance(points[-1], part[0]) > 1e-6:
            raise ValueError("Disconnected OCCT section wire")
        points.extend(part[1:])
    if distance(points[-1], points[0]) > 1e-6:
        raise ValueError("Open OCCT section wire")
    return points[:-1]


def _cut_contours(shape, extent):
    """Real B-Rep section faces at global Y=0; axes on paper: Z horizontal, X vertical."""
    half = cq.Workplane("XY").box(4 * extent, 2 * extent, 4 * extent).translate((0, -extent, 0)).val()
    cut = shape.intersect(half)
    contours = []
    for face in cut.Faces():
        normal = face.normalAt()
        if abs(face.Center().y) > 1e-5 or abs(normal.y) < 0.999:
            continue
        wires = [_wire_vertices(w) for w in face.Wires()]
        contours.extend(w for w in wires if len(w) >= 3)
    return contours


def _text_values(request):
    p = request.parameters
    values = [
        ("BORE d", p["bore_d_mm"], "mm"),
        ("OUTSIDE D", p["outside_d_mm"], "mm"),
        ("WIDTH B", p["width_mm"], "mm"),
        ("PITCH Dpw", p["pitch_d_mm"], "mm"),
    ]
    if "ball_d_mm" in p:
        values.extend([("BALL Dw", p["ball_d_mm"], "mm"),
                       ("BALL COUNT Z", p["ball_count"], "")])
    else:
        values.extend([("ROLLER Dw", p["roller_d_mm"], "mm"),
                       ("ROLLER Lw", p["roller_length_mm"], "mm"),
                       ("ROLLER COUNT Z", p["roller_count"], "")])
    if "contact_angle_deg" in p:
        values.append(("CONTACT ANGLE", p["contact_angle_deg"], "deg"))
    if "configuration" in p:
        values.append(("FLANGE CONFIG", p["configuration"], ""))
    return values


def generate_review_drawings(request, model, output: Path) -> dict:
    """Write assembly cross-section and ring part section sheets with no guessed tolerances.

    A representative rolling element is placed at the nominal pitch radius in
    the assembly section. It is NOT a literal cut through all actual instances.
    Cage is not sectioned because its detailed pockets need dedicated drafting.
    """
    output = Path(output)
    parts = {part.component_id: part.shape for part in model.components}
    for required in ("inner_ring", "outer_ring"):
        if required not in parts:
            raise ValueError(f"Missing B-Rep for {required}")
    p = request.parameters
    extent = max(float(p["outside_d_mm"]), float(p["width_mm"]), 10.0) * 2
    element_name = "ball" if "ball_d_mm" in p else "roller"
    if element_name not in parts:
        raise ValueError("Missing B-Rep for rolling element")
    pitch_r = float(p["pitch_d_mm"]) / 2
    sections = {
        "inner_ring": _cut_contours(parts["inner_ring"], extent),
        "outer_ring": _cut_contours(parts["outer_ring"], extent),
        "rolling_element_top": _cut_contours(parts[element_name].translate((pitch_r, 0, 0)), extent),
        "rolling_element_bottom": _cut_contours(parts[element_name].translate((-pitch_r, 0, 0)), extent),
    }
    if any(not paths for paths in sections.values()):
        raise ValueError("Incomplete B-Rep section: cannot publish review drawing")
    styles = {"inner_ring": ("INNER_RING", "#7fa9bb", 5),
              "outer_ring": ("OUTER_RING", "#8e9aab", 8),
              "rolling_element_top": ("ROLLING_ELEMENT", "#cd956e", 30),
              "rolling_element_bottom": ("ROLLING_ELEMENT", "#cd956e", 30)}
    index = []
    for sheet, names in (("assembly", tuple(sections)),
                         ("inner_ring", ("inner_ring",)),
                         ("outer_ring", ("outer_ring",))):
        doc = ezdxf.new("R2010", setup=True)
        doc.units = ezdxf.units.MM
        for name, color in (("FRAME", 7), ("CENTER", 1), ("DIM", 2), ("NOTES", 7),
                            ("INNER_RING", 5), ("OUTER_RING", 8), ("ROLLING_ELEMENT", 30)):
            doc.layers.new(name, dxfattribs={"color": color})
        space = doc.modelspace()
        svg = svgwrite.Drawing(size=("1260px", "891px"), viewBox="0 0 420 297")
        svg.attribs["font-family"] = "Arial, Noto Sans, sans-serif"
        svg.add(svg.rect(insert=(0, 0), size=SHEET_MM, fill="#fbfcfd"))
        def line(a, b, layer="FRAME", color="#273b52", weight=.35):
            space.add_line(a, b, dxfattribs={"layer": layer})
            svg.add(svg.line(start=(a[0], 297-a[1]), end=(b[0], 297-b[1]), stroke=color, stroke_width=weight))
        def text(value, x, y, h=3.2, layer="NOTES", color="#24384c"):
            value = str(value)
            space.add_text(value, dxfattribs={"layer": layer, "height": h, "insert": (x, y)})
            svg.add(svg.text(value, insert=(x, 297-y), fill=color, font_size=h))
        for x0,y0,x1,y1 in ((8,8,412,8),(412,8,412,289),(412,289,8,289),(8,289,8,8),
                             (14,14,406,14),(406,14,406,283),(406,283,14,283),(14,283,14,14)):
            line((x0,y0),(x1,y1))
        line((14,263),(406,263))
        text("ROLLING BEARING - PARAMETRIC 2D REVIEW", 22, 273, 5.0)
        text(f"VIEW: {sheet.upper()}  /  AXIAL SECTION Y=0", 22, 255, 3.5)
        # Fit the exact section with a single isotropic sheet transform.
        all_pts = [pt for key in names for wire in sections[key] for pt in wire]
        if not all_pts:
            raise ValueError("Empty section")
        lo_u, hi_u = min(x for x,y in all_pts), max(x for x,y in all_pts)
        lo_v, hi_v = min(y for x,y in all_pts), max(y for x,y in all_pts)
        scale = min(205 / max(hi_u-lo_u, 1e-6), 180 / max(hi_v-lo_v, 1e-6), 4.5)
        origin = (144 - scale * (hi_u+lo_u) / 2, 150 - scale * (hi_v+lo_v) / 2)
        def paper(pt): return (origin[0]+scale*pt[0], origin[1]+scale*pt[1])
        count = 0
        for name in names:
            layer, fill, color_id = styles[name]
            for wire in sections[name]:
                pts = [paper(pt) for pt in wire]
                space.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
                svg.add(svg.polygon([(x,297-y) for x,y in pts], fill=fill, fill_opacity=.18,
                                    stroke="#244660", stroke_width=.23))
                count += 1
        # Axial and radial centrelines; front section outlines are from B-Rep, not SVG circles.
        for a,b in (((18,origin[1]),(260,origin[1])),
                    ((origin[0],49),(origin[0],247))):
            line(a,b,"CENTER","#cc7580",.2)
        labels = _text_values(request)
        for i,(label,value,unit) in enumerate(labels):
            text(f"{label}: {value:g} {unit}" if isinstance(value,(float,int)) else f"{label}: {value}",
                 287,238 - i*10,3.1,"DIM")
        if request.cage is not None:
            text("CAGE: detailed section not shown",287,238-len(labels)*10,2.65)
        line((14,39),(406,39))
        text("SOURCE: OCCT B-Rep / same parameters as STEP",20,29,3.0)
        text("SCHEMATIC ROLLING ELEMENTS / NO TOLERANCES",20,20,2.7,"NOTES","#9b5060")
        text("DRAFT - NOT FOR MANUFACTURE",271,29,3.3,"NOTES","#9b5060")
        text("UNITS: mm    /    SCALE: FIT TO SHEET",271,20,2.8)
        base = f"bearing_{sheet}_review"
        dxf_path, svg_path = output / (base + ".dxf"), output / (base + ".svg")
        doc.saveas(dxf_path)
        audit = ezdxf.readfile(dxf_path).audit()
        if audit.has_errors or audit.fixes:
            raise ValueError(f"DXF audit failed: {base}")
        svg.saveas(str(svg_path))
        index.append({"view": sheet, "dxf": dxf_path.name, "svg": svg_path.name,
                      "section_contours": count, "sheet_scale": scale})
    report = {"schema_version": DRAWING_VERSION,
              "request_hash": request.request_hash,
              "status": "DRAFT_NOT_FOR_MANUFACTURE",
              "source": "OCCT B-Rep used by 3D STEP",
              "geometry": "True axial B-Rep sections for rings; representative rolling elements",
              "exclusions": ["No original RoBAS DWG templates available", "No automatic tolerances/GD&T",
                             "Cage detail not drawn", "Not a manufacturing drawing"],
              "sheets": index}
    (output / "drawing_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    return report

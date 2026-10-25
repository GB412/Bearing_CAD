"""Authoritative OCCT half-section solids and dimensioned A3-style draft drawing.

Source geometry is exactly the B-Rep used for STEP/STL. The sheet is a
dimensioned review drawing, *not* a manufacturing-standard released drawing.
All coordinates are mm. The section plane is y=0, with y<=0 retained.
"""
from __future__ import annotations

import math
from pathlib import Path


STL_TOLERANCE_MM = 0.025
STL_ANGULAR_TOLERANCE_RAD = 0.12


def make_sections(design, models):
    import cadquery as cq
    b = design.bearing
    extent = max(b.housing_od_mm, b.housing_length_mm, b.shaft_length_mm) + 20
    # Intersection (not GPU clipping) creates actual closed section solids,
    # preserving the exact B-Rep faces along the section plane.
    halfspace = cq.Workplane("XY").box(
        4 * extent, 2 * extent, 4 * extent
    ).translate((0, -extent, 0))
    result = {}
    for name, model in models.items():
        section = model.intersect(halfspace)
        solids = section.solids().vals()
        if len(solids) != 1 or not solids[0].isValid():
            raise ValueError(f"Section of {name} is not a valid single solid")
        if not (0 < solids[0].Volume() < model.val().Volume()):
            raise ValueError(f"Section of {name} does not remove material")
        if abs(solids[0].BoundingBox().ymax) > 1e-5:
            raise ValueError(f"Section plane mismatch for {name}")
        result[name] = section
    return result


def check_assembly(design, models):
    """Nominal interference/clearance check, not tolerance-fit certification."""
    b = design.bearing
    if b.bore_d_mm <= b.shaft_d_mm:
        raise ValueError("Bore must exceed shaft diameter")
    pairs = [("shaft", "bushing"), ("bushing", "housing"), ("shaft", "housing")]
    overlaps = {}
    for left, right in pairs:
        volume = models[left].intersect(models[right]).val().Volume()
        overlaps[f"{left}_{right}_mm3"] = round(volume, 7)
        if volume > 1e-5:
            raise ValueError(f"Interfering assembly geometry: {left}, {right}")
    return {
        "radial_clearance_mm": round((b.bore_d_mm - b.shaft_d_mm) / 2, 6),
        "bushing_to_housing_nominal_diametral_gap_mm": 0.0,
        "nominal_interference_mm3": overlaps,
        "note": "Nominal geometry only. Press fits/tolerances require separate engineering review.",
    }


def _wire_points(wire):
    """Order and orient OCCT wire edges for a connected planar polygon."""
    paths = []
    for edge in wire.Edges():
        count = max(2, min(700, math.ceil(edge.Length() / 0.18) + 1))
        nodes = edge.sample(count)[0]
        pts = [(float(v.z), float(v.x)) for v in nodes]  # sheet x=axial z; sheet y=radial x
        if len(pts) > 1:
            paths.append(pts)
    if not paths:
        return []
    ordered = list(paths.pop(0))
    def dist(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
    while paths:
        end = ordered[-1]
        best = min(range(len(paths)), key=lambda i: min(dist(end, paths[i][0]), dist(end, paths[i][-1])))
        part = paths.pop(best)
        if dist(end, part[-1]) < dist(end, part[0]):
            part.reverse()
        if dist(end, part[0]) > 1e-5:
            raise ValueError("Disconnected section wire; cannot hatch inaccurately")
        ordered.extend(part[1:])
    if dist(ordered[-1], ordered[0]) > 1e-5:
        raise ValueError("Open section wire")
    return ordered[:-1] if dist(ordered[-1], ordered[0]) < 1e-10 else ordered


def _section_faces(section):
    faces = []
    for face in section.val().Faces():
        # Use actual planar faces introduced by the OCCT half-space boolean.
        normal = face.normalAt()
        if abs(face.Center().y) > 1e-5 or abs(normal.y) < 0.99999:
            continue
        wires = [_wire_points(wire) for wire in face.Wires()]
        if any(len(wire) < 3 for wire in wires):
            continue
        faces.append(wires)
    if not faces:
        raise ValueError("No physical section faces on y=0")
    return faces


def write_review_drawing(design, models, section_models, output: Path, projector):
    """Create one A3-style SVG and a geometrically matched millimetre DXF.

    The cross-section contours and hatches are taken from real OCCT boolean
    faces. End-view outlines are taken from OCCT HLR on the full assembly.
    """
    import cadquery as cq
    import ezdxf
    import svgwrite

    b, f = design.bearing, design.features
    output.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    palette = {
        "FRAME": 7, "HOUSING": 8, "BUSHING": 5, "SHAFT": 3,
        "SECTION": 8, "VISIBLE": 7, "HIDDEN": 8, "CENTER": 1, "DIM": 2, "NOTES": 7,
    }
    for name, color in palette.items():
        doc.layers.new(name, dxfattribs={"color": color})
    ms = doc.modelspace()
    svg = svgwrite.Drawing(str(output / "bearing_review_sheet.svg"),
        size=("1680px", "1188px"), viewBox="0 0 1680 1188")
    svg.attribs["font-family"] = "Noto Sans CJK SC, Microsoft YaHei, sans-serif"
    svg.add(svg.rect(insert=(0, 0), size=(1680, 1188), fill="#f9fbfd"))

    def point(x, y):
        return (x * 4, (297 - y) * 4)
    def seg(x0, y0, x1, y1, layer="DIM", color="#54718e", width=0.75, dash=None):
        ms.add_line((x0, y0), (x1, y1), dxfattribs={"layer": layer})
        svg.add(svg.line(start=point(x0, y0), end=point(x1, y1),
                         stroke=color, stroke_width=width * 4,
                         stroke_dasharray=dash or "none"))
    def label(text, x, y, size=3.0, layer="NOTES", color="#213a53", bold=False):
        ms.add_text(text, dxfattribs={"height": size, "insert": (x, y), "layer": layer})
        px, py = point(x, y)
        svg.add(svg.text(text, insert=(px, py), font_size=size * 4,
                         font_weight="700" if bold else "400", fill=color))

    pattern = svg.pattern(id="metalHatch", insert=(0, 0), size=(32, 32),
                          patternUnits="userSpaceOnUse", patternTransform="rotate(38)")
    pattern.add(svg.line(start=(0, 0), end=(0, 32), stroke="#899fb6", stroke_width=2))
    svg.defs.add(pattern)

    # A3 landscape sheet, title bar, image field and bottom-right title block.
    for a, c, d, e, width in [(8, 8, 412, 289, 1.4), (14, 14, 406, 283, .45)]:
        for p, q, x, y in ((a,c,d,c),(d,c,d,e),(d,e,a,e),(a,e,a,c)):
            seg(p,q,x,y,"FRAME","#243b51",width)
    seg(14, 267, 406, 267, "FRAME","#243b51", .7)
    label("滑动轴承 | 参数化结构设计图", 24, 274, 5.3, bold=True)
    label("轴向半剖 A-A + 端面投影  /  单位 mm", 252, 274, 3.1)
    # Layout uses true-mm contours; offsets only position the views on A3.
    section_origin = (108.0, 174.0)
    section_count = {}
    for name, color in (("housing", "#dce5ee"), ("bushing", "#94bbdf"), ("shaft", "#b7d8c6")):
        faces = _section_faces(section_models[name])
        section_count[name] = len(faces)
        for wires in faces:
            # A continuous even-odd path supports holes/recesses in cross-sections.
            d = []
            hatch = ms.add_hatch(color=palette[name.upper()], dxfattribs={"layer": "SECTION"})
            hatch.set_pattern_fill("ANSI31", scale=0.65, color=palette[name.upper()])
            for wire_index, local in enumerate(wires):
                points = [(section_origin[0] + u, section_origin[1] + v)
                          for u, v in local]
                if len(points) < 3:
                    continue
                d.append("M " + " L ".join(f"{point(x,y)[0]:.3f},{point(x,y)[1]:.3f}" for x,y in points) + " Z")
                hatch.paths.add_polyline_path(points, is_closed=True, flags=1 if wire_index == 0 else 0)
                ms.add_lwpolyline(points, close=True, dxfattribs={"layer": name.upper()})
            if d:
                svg.add(svg.path(d=" ".join(d), fill=color, fill_rule="evenodd",
                                 stroke="#314b63", stroke_width=2.5))
                svg.add(svg.path(d=" ".join(d), fill="url(#metalHatch)",
                                 fill_rule="evenodd", opacity=0.55))

    # Axis and dimension extensions, all dimension values from validated input.
    zhalf = b.housing_length_mm / 2
    seg(section_origin[0]-b.shaft_length_mm/2-14, section_origin[1],
        section_origin[0]+b.shaft_length_mm/2+14, section_origin[1],
        "CENTER", "#bc6475", .35, "26,9,5,9")
    label("A", 48, 175, 3.2, bold=True)
    label("A", 159, 175, 3.2, bold=True)
    label("A-A 轴向剖视", 78, 109, 3.8, bold=True)
    # Axial dimensions are drawn on the real section geometry.
    x_left, x_right = section_origin[0]-b.length_mm/2, section_origin[0]+b.length_mm/2
    top = section_origin[1]+b.housing_od_mm/2
    for x in (x_left,x_right):
        seg(x, top+2, x, top+14, "DIM", "#4f6e89",.4)
    seg(x_left,top+12,x_right,top+12,"DIM","#4f6e89",.4)
    label(f"L = {b.length_mm:g}",x_left+2,top+15.5,3.2,"DIM")
    seg(section_origin[0]-zhalf, top+2, section_origin[0]-zhalf, top+23,"DIM","#4f6e89",.35)
    seg(section_origin[0]+zhalf, top+2, section_origin[0]+zhalf, top+23,"DIM","#4f6e89",.35)
    seg(section_origin[0]-zhalf,top+21,section_origin[0]+zhalf,top+21,"DIM","#4f6e89",.35)
    label(f"Lh = {b.housing_length_mm:g}",section_origin[0]-zhalf+1,top+24,3.1,"DIM")
    label(f"轴颈 d = {b.shaft_d_mm:g} mm",25,79,3.2,"DIM")
    label(f"轴瓦内孔 = {b.bore_d_mm:g} mm",25,72,3.2,"DIM")
    label(f"径向间隙 c = {b.radial_clearance_mm:g} mm",25,65,3.2,"DIM")
    label(f"轴瓦外径 D1 = {b.bush_od_mm:g} mm",25,58,3.2,"DIM")
    label(f"轴承座外径 D2 = {b.housing_od_mm:g} mm",25,51,3.2,"DIM")
    label("结构剖面取自 OCCT 实体 (y=0)",25,43,2.9,"NOTES","#61768b")

    # End view from exact B-Rep HLR, not handcrafted concentric SVG circles.
    combined = cq.Compound.makeCompound([models[n].val() for n in ("housing","bushing","shaft")])
    end = projector(combined, (0, 0, 1))
    end_origin = (306.0, 176.0)
    for layer, paths in (("hidden", end["hidden"]), ("visible", end["visible"])):
        for wire in paths:
            pts = [(end_origin[0]+x, end_origin[1]+y) for x,y in wire]
            if len(pts) < 2:
                continue
            ms.add_lwpolyline(pts, dxfattribs={"layer": layer.upper()})
            mapped = [point(x,y) for x,y in pts]
            svg.add(svg.polyline(mapped, fill="none", stroke="#94a5ba" if layer=="hidden" else "#2b4c68",
                                 stroke_width=1.7 if layer=="hidden" else 2.6,
                                 stroke_dasharray="8,7" if layer=="hidden" else "none"))
    R = b.housing_od_mm / 2
    seg(end_origin[0]-R-10, end_origin[1],end_origin[0]+R+10,end_origin[1],"CENTER","#bc6475",.35,"22,7,5,7")
    seg(end_origin[0],end_origin[1]-R-10,end_origin[0],end_origin[1]+R+10,"CENTER","#bc6475",.35,"22,7,5,7")
    label("端面视图",286,109,3.8,bold=True)

    # View legend, lubrication detail dimensions and drawing title block.
    seg(14, 35, 406, 35, "FRAME","#314b63",.7)
    label(f"径向供油孔: {f.oil_feed_hole_d_mm:g} mm" if f.oil_feed_hole_d_mm else "径向供油孔: 无",
          176, 82, 3.1)
    if f.annular_groove_width_mm is not None:
        label(f"内环槽: 宽 {f.annular_groove_width_mm:g} / 深 {f.annular_groove_depth_mm:g} mm",
              176, 75, 3.1)
    else:
        label("内环形油槽: 无",176,75,3.1)
    label("图示用于几何与方案复核；未指定配合公差、粗糙度或承载校核。",176,62,2.9,color="#6b7a8c")
    label("严禁作为已审核制造图使用",176,55,2.9,color="#a35359")
    for x in (264,337):
        seg(x,14,x,35,"FRAME","#314b63",.45)
    seg(264,25,406,25,"FRAME","#314b63",.45)
    label("图名  圆柱径向滑动轴承",272,28.5,3.5,bold=True)
    label("版本  参数化设计草图",272,18,3.1)
    label("比例  示意 / 单位 mm",341,28.5,3.0)
    label("状态  待工程校核",341,18,3.0,color="#a35359")
    label("自动生成 · 轴承 CAD 工作台",22,22,3.3)
    label("几何源: CadQuery / OpenCascade",22,16,2.7,color="#708297")

    svg.save()
    destination = output / "bearing_review_sheet.dxf"
    doc.saveas(destination)
    audit = ezdxf.readfile(destination).audit()
    if audit.has_errors or audit.fixes:
        raise ValueError(f"Engineering review DXF invalid: {len(audit.errors)} errors, {len(audit.fixes)} fixes")
    return {"section_plane": "Y=0; keep Y<=0",
            "section_face_counts": section_count,
            "end_visible_edges": len(end["visible"]),
            "status": "DRAFT_NOT_FOR_MANUFACTURE"}

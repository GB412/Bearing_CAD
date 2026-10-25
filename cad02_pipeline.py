#!/usr/bin/env python3
"""CAD-02 deterministic OCCT exports of a plain journal bearing (demo only).

Independent of browser visualization and V3.1 design approval. All files
have DRAFT provenance and must never be presented as released drawings.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from dataclasses import dataclass, fields
from decimal import Decimal

from generate_cad import Bearing

GENERATOR_VERSION = "CAD-02/0.2.0"
BASE_FIELDS = {f.name for f in fields(Bearing)}
FEATURE_FIELDS = {"oil_feed_hole_d_mm", "annular_groove_width_mm", "annular_groove_depth_mm"}
ALL_FIELDS = BASE_FIELDS | FEATURE_FIELDS


@dataclass(frozen=True)
class FeatureSpec:
    oil_feed_hole_d_mm: float | None = None
    annular_groove_width_mm: float | None = None
    annular_groove_depth_mm: float | None = None

    def validate(self, b: Bearing) -> None:
        for name, v in vars(self).items():
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f"{name} must be a finite number")
            if abs(v * 1000 - round(v * 1000)) > 1e-7:
                raise ValueError(f"{name}: precision must be 0.001 mm")
            if v <= 0:
                raise ValueError(f"{name} must be positive")
        if (self.annular_groove_width_mm is None) != (self.annular_groove_depth_mm is None):
            raise ValueError("Annular groove width and depth must be specified together")
        if self.annular_groove_width_mm is not None:
            if self.oil_feed_hole_d_mm is None:
                raise ValueError("Annular groove in this demo requires a radial oil feed hole")
            if self.annular_groove_width_mm >= b.length_mm - 4:
                raise ValueError("Annular groove requires >=2 mm material at each axial end")
            wall = (b.bush_od_mm - b.bore_d_mm) / 2
            if self.annular_groove_depth_mm >= wall - 2:
                raise ValueError("Annular groove must leave >2 mm radial wall")
        if self.oil_feed_hole_d_mm is not None:
            if self.oil_feed_hole_d_mm >= min(b.length_mm - 4, b.housing_length_mm - 4):
                raise ValueError("Oil feed hole exceeds axial stock margin")
            if self.oil_feed_hole_d_mm >= b.bush_od_mm / 2:
                raise ValueError("Oil feed hole is too large for the demo")


@dataclass(frozen=True)
class Design:
    bearing: Bearing
    features: FeatureSpec

    def validate(self) -> "Design":
        self.bearing.validate()
        self.features.validate(self.bearing)
        return self

    def normalized_geometry(self) -> dict:
        # 0.001 mm integer grid to avoid JSON floating-point hash drift.
        # Unknown approval fields are explicitly rejected in read_design().
        raw = {**vars(self.bearing),
               **{k: v for k, v in vars(self.features).items() if v is not None}}
        return {k: int(Decimal(str(v)) * 1000) for k, v in sorted(raw.items())}

    @property
    def geometry_hash(self) -> str:
        payload = json.dumps(self.normalized_geometry(), ensure_ascii=True,
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_design(data: dict) -> Design:
    """Parse untrusted JSON payloads, rejecting unknown approval/identity fields."""
    if not isinstance(data, dict):
        raise ValueError("Design parameters must be a JSON object")
    unknown, missing = set(data) - ALL_FIELDS, BASE_FIELDS - set(data)
    if unknown or missing:
        raise ValueError(f"Invalid input fields: missing={sorted(missing)} unknown={sorted(unknown)}")
    design = Design(Bearing(**{k: data[k] for k in BASE_FIELDS}),
                    FeatureSpec(**{k: data[k] for k in FEATURE_FIELDS if k in data}))
    return design.validate()


def read_design(path: Path) -> Design:
    return parse_design(json.loads(path.read_text(encoding="utf-8")))


def build_models(design: Design):
    """Authoritative three-part OCCT B-Rep, coaxial with Z."""
    import cadquery as cq
    from generate_cad import cad_models
    design.validate()
    b, f = design.bearing, design.features
    models = cad_models(b)
    if f.annular_groove_width_mm is not None:
        # Internal rectangular-profile annular recess, centred at z=0.
        groove = (cq.Workplane("XY")
                  .circle(b.bore_d_mm / 2 + f.annular_groove_depth_mm)
                  .circle(b.bore_d_mm / 2 - 0.5)
                  .extrude(f.annular_groove_width_mm)
                  .translate((0, 0, -f.annular_groove_width_mm / 2)))
        models["bushing"] = models["bushing"].cut(groove)
    if f.oil_feed_hole_d_mm is not None:
        # A single +X radial oil-feed hole. The shaft remains intact.
        start_x = b.shaft_d_mm / 2 - 0.5
        drill = (cq.Workplane("YZ").circle(f.oil_feed_hole_d_mm / 2)
                 .extrude(b.housing_od_mm / 2 - start_x + 2)
                 .translate((start_x, 0, 0)))
        for name in ("housing", "bushing"):
            models[name] = models[name].cut(drill)
    return models


def validate_models(design: Design, models: dict) -> dict:
    """Reject missing/multiple solids, invalid volumes, bounds or alignment."""
    if set(models) != {"housing", "bushing", "shaft"}:
        raise ValueError("Expected housing, bushing and shaft")
    b = design.bearing
    expected = {"housing": (b.housing_od_mm, b.housing_length_mm),
                "bushing": (b.bush_od_mm, b.length_mm),
                "shaft": (b.shaft_d_mm, b.shaft_length_mm)}
    from OCP.BRepCheck import BRepCheck_Analyzer
    out = {}
    for name, obj in models.items():
        solids = obj.solids().vals()
        if len(solids) != 1:
            raise ValueError(f"{name} must contain exactly one solid")
        solid = solids[0]
        if solid.Volume() <= 1e-6 or not solid.isValid() or not BRepCheck_Analyzer(solid.wrapped).IsValid():
            raise ValueError(f"{name} is not a valid closed positive-volume B-Rep")
        box = solid.BoundingBox()
        diameter, length = expected[name]
        for actual, target in ((box.xlen, diameter), (box.ylen, diameter), (box.zlen, length)):
            if abs(actual - target) > 1e-4:
                raise ValueError(f"{name} bounding box differs from expected geometry")
        if any(abs(v) > 1e-4 for v in ((box.xmin+box.xmax)/2,
                                      (box.ymin+box.ymax)/2, (box.zmin+box.zmax)/2)):
            raise ValueError(f"{name} is not centred at the origin")
        out[name] = {"volume_mm3": round(solid.Volume(), 6),
                     "bounds_mm": {"x": round(box.xlen, 5), "y": round(box.ylen, 5),
                                   "z": round(box.zlen, 5)},
                     "is_valid": True, "solid_count": 1}
    return out


def projection_edges(shape, direction=(0, 1, 0)):
    """Compute visible/hidden projected B-Rep edges using OCCT HLR.

    OCCT projector places edges in the projected XY camera coordinates.
    Curves are sampled to DXF/SVG polylines at <=0.25 mm arc step.
    """
    import cadquery as cq
    from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    from OCP.HLRAlgo import HLRAlgo_Projector
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.BRepLib import BRepLib

    hlr = HLRBRep_Algo()
    hlr.Add(shape.wrapped)
    hlr.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(), gp_Dir(*direction))))
    hlr.Update()
    hlr.Hide()
    projected = HLRBRep_HLRToShape(hlr)
    result = {"visible": [], "hidden": []}
    for layer, names in (("visible", ("VCompound", "Rg1LineVCompound", "OutLineVCompound")),
                         ("hidden", ("HCompound", "OutLineHCompound"))):
        for name in names:
            occ_shape = getattr(projected, name)()
            if occ_shape.IsNull():
                continue
            BRepLib.BuildCurves3d_s(occ_shape, 1e-6)
            for edge in cq.Shape(occ_shape).Edges():
                points = edge.sample(max(2, min(600, math.ceil(edge.Length() / 0.25))))[0]
                if len(points) > 1:
                    result[layer].append([(round(v.x, 6), round(v.y, 6)) for v in points])
    if not result["visible"]:
        raise ValueError("OCCT projection returned no visible edges")
    return result


def write_projections(models: dict, out: Path) -> dict:
    """Use the identical OCCT HLR edges for both SVG views and millimetre DXF."""
    import cadquery as cq
    import ezdxf
    import svgwrite
    assy = cq.Compound.makeCompound([models[name].val()
                                    for name in ("housing", "bushing", "shaft")])
    directions = {"side": (0, 1, 0), "end": (0, 0, 1)}
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    for name, color in (("VISIBLE", 7), ("HIDDEN", 8), ("CENTER", 1), ("NOTES", 2)):
        doc.layers.new(name, dxfattribs={"color": color})
    model = doc.modelspace()
    reports = {}
    for view, direction in directions.items():
        edges = projection_edges(assy, direction)
        reports[view] = {"visible_edges": len(edges["visible"]),
                         "hidden_edges": len(edges["hidden"])}
        svg = svgwrite.Drawing(str(out / f"occt_{view}.svg"),
                               size=("1200px", "800px"), viewBox="0 0 1200 800")
        svg.add(svg.rect(insert=(0, 0), size=(1200, 800), fill="white"))
        coords = [pt for layer in edges.values() for path in layer for pt in path]
        xmin, xmax = min(x for x,y in coords), max(x for x,y in coords)
        ymin, ymax = min(y for x,y in coords), max(y for x,y in coords)
        scale = 640 / max(xmax - xmin, ymax - ymin, 1)
        cx, cy = (xmin+xmax)/2, (ymin+ymax)/2
        offset = 0 if view == "side" else 350
        for layer in ("hidden", "visible"):
            for points in edges[layer]:
                mapped = [(600+(x-cx)*scale, 390-(y-cy)*scale) for x,y in points]
                svg.add(svg.polyline(mapped, fill="none",
                     stroke="#6a87a1" if layer == "hidden" else "#233a52",
                     stroke_width=1.2, stroke_dasharray="5,4" if layer == "hidden" else "none"))
                model.add_lwpolyline([(x+offset, y) for x,y in points],
                                    dxfattribs={"layer": layer.upper()})
        svg.add(svg.text(f"OCCT {view.upper()} HLR - DRAFT / UNVERIFIED / mm",
                         insert=(38, 46), font_size=23, fill="#203f5b"))
        svg.add(svg.text("Derived from actual B-Rep; not a dimensioned manufacturing drawing",
                         insert=(38, 75), font_size=15, fill="#6c7884"))
        svg.save()
    model.add_text("OCCT projected outlines, units mm; DRAFT / NOT MANUFACTURING DRAWING",
                   dxfattribs={"height": 3, "insert": (0, -115), "layer": "NOTES"})
    path = out / "occt_projection.dxf"
    doc.saveas(str(path))
    audit = ezdxf.readfile(str(path)).audit()
    if audit.has_errors or audit.fixes:
        raise RuntimeError(f"DXF audit: {len(audit.errors)} errors / {len(audit.fixes)} fixes")
    return reports


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify_bundle(directory: Path, geometry_hash: str) -> dict:
    manifest = json.loads((directory / "artifact_manifest.json").read_text(encoding="utf-8"))
    if (manifest["generator_version"] != GENERATOR_VERSION or
            manifest["geometry_hash_sha256"] != geometry_hash or
            manifest["approval_state"] != "DRAFT"):
        raise RuntimeError("CAD-02 cache manifest does not match requested DRAFT design")
    for filename, info in manifest["files"].items():
        path = directory / filename
        if not path.is_file() or _sha(path.read_bytes()) != info["sha256"]:
            raise RuntimeError(f"CAD-02 cache corrupted or incomplete: {filename}")
    return manifest


def generate(design: Design, out_root: Path) -> Path:
    """Content-addressed, no-overwrite CAD bundle; staged before publish."""
    design.validate()
    out_root.mkdir(parents=True, exist_ok=True)
    geometry_hash = design.geometry_hash
    key = _sha(f"{GENERATOR_VERSION}:{geometry_hash}".encode("utf-8"))[:24]
    dest = out_root / key
    if dest.exists():
        verify_bundle(dest, geometry_hash)
        return dest
    tmp = Path(tempfile.mkdtemp(prefix=".cad02-staging-", dir=out_root))
    try:
        import cadquery as cq
        models = build_models(design)
        checks = validate_models(design, models)
        from cad_workbench_drawing import make_sections, check_assembly, write_review_drawing, STL_TOLERANCE_MM, STL_ANGULAR_TOLERANCE_RAD
        assembly_checks = check_assembly(design, models)
        sections = make_sections(design, models)
        for name, solid in sections.items():
            solid.export(str(tmp / f"{name}_section.stl"),
                         tolerance=STL_TOLERANCE_MM, angularTolerance=STL_ANGULAR_TOLERANCE_RAD)
            solid.export(str(tmp / f"{name}_section.step"))
        assembly = cq.Assembly(name="PlainJournalBearingCAD02")
        for name, color in (("housing", cq.Color(.7, .77, .85)),
                            ("bushing", cq.Color(.2, .55, .85)),
                            ("shaft", cq.Color(.5, .75, .6))):
            assembly.add(models[name], name=name, color=color)
            models[name].export(str(tmp / f"{name}.step"))
            models[name].export(str(tmp / f"{name}.stl"), tolerance=STL_TOLERANCE_MM, angularTolerance=STL_ANGULAR_TOLERANCE_RAD)
        assembly.export(str(tmp / "bearing_assembly.step"))
        projections = write_projections(models, tmp)
        drawing = write_review_drawing(design, models, sections, tmp, projection_edges)
        (tmp / "design_snapshot.json").write_text(json.dumps(
            {"unit": "mm", "approval_state": "DRAFT",
             "bearing": vars(design.bearing), "features": vars(design.features)},
            ensure_ascii=False, indent=2), encoding="utf-8")
        files = {p.name: {"sha256": _sha(p.read_bytes()), "size_bytes": p.stat().st_size}
                 for p in sorted(tmp.iterdir()) if p.is_file()}
        manifest = {"generator_version": GENERATOR_VERSION,
                    "occt_version": getattr(cq, "__version__", "unknown"),
                    "approval_state": "DRAFT",
                    "geometry_hash_sha256": geometry_hash,
                    "cache_key": key, "unit": "mm",
                    "topology_checks": checks, "assembly_checks": assembly_checks,
                    "section_drawing_checks": drawing,
                    "projection_checks": projections, "files": files}
        (tmp / "artifact_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            tmp.rename(dest)
        except OSError:
            if dest.exists():
                verify_bundle(dest, geometry_hash)
                return dest
            raise
        return dest
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--params", required=True, help="JSON dimensions in mm")
    parser.add_argument("--out", default="artifacts/cad02")
    args = parser.parse_args()
    design = read_design(Path(args.params))
    output = generate(design, Path(args.out))
    print(json.dumps({"artifact_dir": str(output), "geometry_hash": design.geometry_hash}))


if __name__ == "__main__":
    main()

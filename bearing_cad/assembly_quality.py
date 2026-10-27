"""Narrow CAD assembly audit: exact instance locations and STEP roundtrip metrics.

This is a geometry integrity gate, NOT a bearing-design or manufacturing check.
"""
from __future__ import annotations

import math

import cadquery as cq

from .contracts import AssemblyModel, ContractError
from .geometry_checks import inspect_solid


def instance_location(instance) -> cq.Location:
    """One transform convention for OCCT STEP and the browser STL preview."""
    return cq.Location(
        cq.Vector(*instance.translation_mm),
        cq.Vector(0, 0, 1),
        float(instance.rotation_about_z_deg),
    )


def build_assembly(model: AssemblyModel) -> cq.Assembly:
    """Apply the full per-instance translation and rotation to B-Rep prototypes."""
    parts = {item.component_id: item.shape for item in model.components}
    assembly = cq.Assembly(name="bearing_assembly")
    for instance in model.instances:
        assembly.add(parts[instance.component_id], name=instance.instance_id,
                     loc=instance_location(instance))
    return assembly


def _bounds(shapes) -> list[float]:
    """Return (xmin, xmax, ymin, ymax, zmin, zmax) in mm."""
    boxes = [shape.BoundingBox() for shape in shapes]
    if not boxes:
        raise ValueError("Assembly contains no solids")
    return [min(b.xmin for b in boxes), max(b.xmax for b in boxes),
            min(b.ymin for b in boxes), max(b.ymax for b in boxes),
            min(b.zmin for b in boxes), max(b.zmax for b in boxes)]


# A Booleans-heavy radial pocket cage may change ~0.017% in OCCT STEP export
# even when both B-Reps pass BRepCheck; limit is geometry interchange, NOT tolerance.
STEP_VOLUME_RELATIVE_LIMIT = 5e-4
STEP_PRECISION_NOTICE = 1e-5
STEP_POSITION_ERROR_LIMIT_MM = 1e-3


def audit_step_roundtrip(model: AssemblyModel, assembly: cq.Assembly,
                         step_solids) -> dict:
    """Fail if valid imported STEP solids differ materially from source geometry."""
    imported = tuple(step_solids)
    if len(imported) != len(model.instances):
        raise RuntimeError("STEP solid count differs from CAD assembly instances")
    if any(not item.isValid() for item in imported):
        raise RuntimeError("STEP contains invalid solid")

    source_solids = tuple(assembly.toCompound().Solids())
    if len(source_solids) != len(model.instances):
        raise RuntimeError("Source CAD assembly contains unexpected solid count")

    component_reports = {part.component_id: inspect_solid(part.shape)
                         for part in model.components}
    if any(not item.valid for item in component_reports.values()):
        raise RuntimeError("Source assembly contains invalid B-Rep")

    # Solids may be reordered by a STEP reader, hence compare sorted volumes.
    source_volumes = sorted(float(shape.Volume()) for shape in source_solids)
    imported_volumes = sorted(float(shape.Volume()) for shape in imported)
    worst_relative_error = max(
        abs(before-after) / max(before, 1e-12)
        for before, after in zip(source_volumes, imported_volumes)
    )
    if worst_relative_error > STEP_VOLUME_RELATIVE_LIMIT:
        raise RuntimeError(
            "STEP solid volume deviation exceeds geometry interchange limit "
            f"({worst_relative_error:.6g} > {STEP_VOLUME_RELATIVE_LIMIT:.6g})"
        )
    src_bounds, step_bounds = _bounds(source_solids), _bounds(imported)
    worst_bbox_error_mm = max(abs(a-b) for a, b in zip(src_bounds, step_bounds))
    if worst_bbox_error_mm > 1e-3:
        raise RuntimeError("STEP assembly bounding box differs from CAD source")
    if not all(math.isfinite(x) for x in src_bounds + step_bounds):
        raise RuntimeError("Non-finite CAD bounds")

    # Global bbox + sorted volume can miss a part displaced inside the
    # unchanged envelope. STEP readers reorder parts, so match by compatible
    # volume first, then nearest center-of-mass, without trusting list indices.
    # Component volume may differ slightly after multi-cut STEP conversion.
    def describe(shapes):
        rows = []
        for solid in shapes:
            center = solid.Center()
            xyz = (float(center.x), float(center.y), float(center.z))
            volume = float(solid.Volume())
            if not all(math.isfinite(v) for v in (*xyz, volume)) or volume <= 0:
                raise RuntimeError("Non-finite or empty STEP part geometry")
            rows.append((xyz, volume))
        return rows

    source_centers = describe(source_solids)
    unmatched = describe(imported)
    worst_position_error_mm = 0.0
    # Larger, usually unique parts first; equivalent rolling elements then
    # match to their corresponding pitch-center, independent of STEP ordering.
    for source_xyz, source_volume in sorted(source_centers, key=lambda row: -row[1]):
        candidates = [
            (math.dist(source_xyz, other_xyz), index)
            for index, (other_xyz, other_volume) in enumerate(unmatched)
            if abs(source_volume - other_volume) / source_volume <= STEP_VOLUME_RELATIVE_LIMIT
        ]
        if not candidates:
            raise RuntimeError("STEP part has no volume-compatible source component")
        position_error, index = min(candidates)
        worst_position_error_mm = max(worst_position_error_mm, position_error)
        unmatched.pop(index)
    if worst_position_error_mm > STEP_POSITION_ERROR_LIMIT_MM:
        raise RuntimeError(
            "STEP part center of mass moved from CAD source "
            f"({worst_position_error_mm:.6g} mm)"
        )

    return {
        "scope": "GEOMETRY_ONLY_NOT_MANUFACTURING_APPROVAL",
        "instance_count": len(model.instances),
        "component_count": len(model.components),
        "component_metrics": [
            {"part_id": part.component_id, "volume_mm3": component_reports[part.component_id].volume_mm3,
             "extents_mm": list(component_reports[part.component_id].extents_mm)}
            for part in model.components
        ],
        "step_roundtrip": {
            "solid_count": len(imported),
            "source_summed_volume_mm3": sum(source_volumes),
            "imported_summed_volume_mm3": sum(imported_volumes),
            "worst_relative_solid_volume_error": worst_relative_error,
            "allowed_relative_volume_error": STEP_VOLUME_RELATIVE_LIMIT,
            "precision_notice": worst_relative_error > STEP_PRECISION_NOTICE,
            "worst_bbox_error_mm": worst_bbox_error_mm,
            "worst_part_centroid_error_mm": worst_position_error_mm,
            "allowed_part_centroid_error_mm": STEP_POSITION_ERROR_LIMIT_MM,
            "source_bounds_mm": src_bounds,
            "imported_bounds_mm": step_bounds,
        },
        "limitations": ["B-Rep/topology/volume/position checks only",
                        "Not a contact-stress, clearance, tolerance or manufacturing assessment"],
    }

"""CAD assembly and STEP interchange audit, scoped to geometric fidelity.

Source instance identity comes from AssemblyModel, never inferred by volume.
STEP readers can reorder and discard names, so imports are matched 1:1 by
strict geometry gates. This is not manufacturing or RoBAS equivalence approval.
"""
from __future__ import annotations

import math

import cadquery as cq

from .contracts import AssemblyModel, BearingType
from .geometry_checks import inspect_solid


def instance_location(instance) -> cq.Location:
    return cq.Location(cq.Vector(*instance.translation_mm),
                       cq.Vector(0, 0, 1), float(instance.rotation_about_z_deg))


def build_assembly(model: AssemblyModel) -> cq.Assembly:
    parts = {part.component_id: part.shape for part in model.components}
    assembly = cq.Assembly(name="bearing_assembly")
    for instance in model.instances:
        assembly.add(parts[instance.component_id], name=instance.instance_id,
                     loc=instance_location(instance))
    return assembly


STEP_VOLUME_RELATIVE_LIMIT = 5e-4
STEP_POSITION_ERROR_LIMIT_MM = 1e-3
STEP_BBOX_ERROR_LIMIT_MM = 1e-3
STEP_PRECISION_NOTICE = 1e-5
# Measured OCCT interchange deviation for the angular-contact radial window
# cage at 1x and 1.25x. Only that identified component receives exceptions.
RADIAL_WINDOW_CAGE_STEP_LIMIT = 1.2e-3
RADIAL_WINDOW_CAGE_POSITION_LIMIT_MM = 5e-3
# An individual complex Boolean cage can experience bbox tolerances distinct
# from the aggregate assembly. Keep the global envelope at 1e-3.
RADIAL_WINDOW_CAGE_BBOX_LIMIT_MM = 1e-2


def _bounds(shapes) -> list[float]:
    boxes = [shape.BoundingBox() for shape in shapes]
    if not boxes:
        raise ValueError("Assembly contains no solids")
    return [min(b.xmin for b in boxes), max(b.xmax for b in boxes),
            min(b.ymin for b in boxes), max(b.ymax for b in boxes),
            min(b.zmin for b in boxes), max(b.zmax for b in boxes)]


def _shape_record(shape) -> dict:
    solids = shape.Solids()
    if len(solids) != 1:
        raise RuntimeError("Expected exactly one solid for each CAD instance")
    solid = solids[0]
    center = solid.Center()
    bounds = _bounds([solid])
    volume = float(solid.Volume())
    xyz = (float(center.x), float(center.y), float(center.z))
    if volume <= 0 or any(not math.isfinite(v) for v in (volume, *xyz, *bounds)):
        raise RuntimeError("Invalid non-finite or empty STEP part geometry")
    return {"volume": volume, "center": xyz, "bounds": bounds}


def _source_records(model: AssemblyModel) -> list[dict]:
    components = {part.component_id: part for part in model.components}
    rows = []
    for instance in model.instances:
        shape = components[instance.component_id].shape
        prototype = shape.val() if isinstance(shape, cq.Workplane) else shape
        moved = prototype.moved(instance_location(instance))
        record = _shape_record(moved)
        is_radial_window_cage = (
            model.bearing_type == BearingType.ANGULAR_CONTACT
            and instance.component_id == "cage"
            and components[instance.component_id].role == "cage"
        )
        record.update({
            "instance_id": instance.instance_id,
            "part_id": instance.component_id,
            "volume_limit": RADIAL_WINDOW_CAGE_STEP_LIMIT
            if is_radial_window_cage else STEP_VOLUME_RELATIVE_LIMIT,
            "centroid_limit_mm": RADIAL_WINDOW_CAGE_POSITION_LIMIT_MM
            if is_radial_window_cage else STEP_POSITION_ERROR_LIMIT_MM,
            "bbox_limit_mm": RADIAL_WINDOW_CAGE_BBOX_LIMIT_MM
            if is_radial_window_cage else STEP_BBOX_ERROR_LIMIT_MM,
            "special_interchange_tolerance": is_radial_window_cage,
        })
        rows.append(record)
    return rows


def _compare(a: dict, b: dict) -> dict:
    return {
        "relative_volume_error": abs(a["volume"] - b["volume"]) / a["volume"],
        "centroid_error_mm": math.dist(a["center"], b["center"]),
        "bbox_error_mm": max(abs(x - y) for x, y in zip(a["bounds"], b["bounds"])),
    }


def _match_solids(source: list[dict], imported: list[dict]) -> list[dict]:
    """Find a full, one-to-one tolerance-compatible matching.

    A STEP reader may reorder solids. Each candidate is constrained by the
    *source component's* limits; a similarly-sized ring cannot inherit the
    cage's larger allowances. Ordinary components are considered first to
    avoid a permissive cage monopolizing a strict part's import candidate.
    """
    candidates = {}
    for i, row in enumerate(source):
        edges = []
        for j, target in enumerate(imported):
            error = _compare(row, target)
            if (error["relative_volume_error"] <= row["volume_limit"]
                    and error["centroid_error_mm"] <= row["centroid_limit_mm"]
                    and error["bbox_error_mm"] <= row["bbox_limit_mm"]):
                normalized = (
                    error["relative_volume_error"] / row["volume_limit"]
                    + error["centroid_error_mm"] / row["centroid_limit_mm"]
                    + error["bbox_error_mm"] / row["bbox_limit_mm"]
                )
                edges.append((normalized, j))
        candidates[i] = [j for _, j in sorted(edges)]
    # Augmenting paths rather than greedy nearest-only matching: two similar
    # rolling elements must not be paired to the same STEP solid.
    imported_owner: dict[int, int] = {}

    def augment(i: int, visited: set[int]) -> bool:
        for j in candidates[i]:
            if j in visited:
                continue
            visited.add(j)
            previous = imported_owner.get(j)
            if previous is None or augment(previous, visited):
                imported_owner[j] = i
                return True
        return False

    for i in sorted(range(len(source)),
                    key=lambda i: (source[i]["special_interchange_tolerance"],
                                   len(candidates[i]), source[i]["instance_id"])):
        if not augment(i, set()):
            raise RuntimeError(
                "STEP part identity/volume/center of mass/bounds mismatch at "
                + source[i]["instance_id"]
            )
    if len(imported_owner) != len(source):
        raise RuntimeError("STEP one-to-one instance matching incomplete")
    positions = {i: j for j, i in imported_owner.items()}
    records = []
    for i, row in enumerate(source):
        j = positions[i]
        imported_row = imported[j]
        error = _compare(row, imported_row)
        records.append({
            "instance_id": row["instance_id"],
            "part_id": row["part_id"],
            "imported_solid_index": j,
            "source_volume_mm3": row["volume"],
            "imported_volume_mm3": imported_row["volume"],
            "relative_volume_error": error["relative_volume_error"],
            "allowed_relative_volume_error": row["volume_limit"],
            "centroid_error_mm": error["centroid_error_mm"],
            "allowed_centroid_error_mm": row["centroid_limit_mm"],
            "bbox_error_mm": error["bbox_error_mm"],
            "allowed_bbox_error_mm": row["bbox_limit_mm"],
            "special_interchange_tolerance": row["special_interchange_tolerance"],
            "within_limits": True,
        })
    return records


def audit_step_roundtrip(model: AssemblyModel, assembly: cq.Assembly,
                         step_solids) -> dict:
    """Reject geometry exchange errors and report actually applied limits."""
    imported_shapes = tuple(step_solids)
    if len(imported_shapes) != len(model.instances):
        raise RuntimeError("STEP solid count differs from CAD assembly instances")
    if any(not shape.isValid() for shape in imported_shapes):
        raise RuntimeError("STEP contains invalid solid")

    parts = {part.component_id: inspect_solid(part.shape)
             for part in model.components}
    if any(not record.valid for record in parts.values()):
        raise RuntimeError("Source assembly contains invalid B-Rep")

    # Check the assembly-level geometry independently of instance matching.
    source_solids = tuple(assembly.toCompound().Solids())
    if len(source_solids) != len(model.instances):
        raise RuntimeError("Source CAD assembly contains unexpected solid count")
    src_bounds, step_bounds = _bounds(source_solids), _bounds(imported_shapes)
    worst_bbox_error_mm = max(abs(x-y) for x, y in zip(src_bounds, step_bounds))
    if worst_bbox_error_mm > STEP_BBOX_ERROR_LIMIT_MM:
        raise RuntimeError("STEP assembly bounding box differs from CAD source")
    if any(not math.isfinite(x) for x in (*src_bounds, *step_bounds)):
        raise RuntimeError("Non-finite CAD assembly bounds")

    source = _source_records(model)
    imported = [_shape_record(shape) for shape in imported_shapes]
    measurements = _match_solids(source, imported)
    worst_relative_error = max(r["relative_volume_error"] for r in measurements)
    worst_position_error_mm = max(r["centroid_error_mm"] for r in measurements)
    special = any(r["special_interchange_tolerance"] for r in measurements)
    return {
        "scope": "GEOMETRY_ONLY_NOT_MANUFACTURING_APPROVAL",
        "instance_count": len(model.instances),
        "component_count": len(model.components),
        "component_metrics": [
            {"part_id": part.component_id, "volume_mm3": parts[part.component_id].volume_mm3,
             "extents_mm": list(parts[part.component_id].extents_mm)}
            for part in model.components
        ],
        "step_roundtrip": {
            "matching_method": "source_instance_transform_to_unordered_step_1to1",
            "solid_count": len(imported),
            "source_summed_volume_mm3": sum(r["volume"] for r in source),
            "imported_summed_volume_mm3": sum(r["volume"] for r in imported),
            "worst_relative_solid_volume_error": worst_relative_error,
            # Aggregate limits are actual maxima, not a fake uniform threshold.
            "allowed_relative_volume_error": max(r["allowed_relative_volume_error"]
                                                  for r in measurements),
            "default_relative_volume_limit": STEP_VOLUME_RELATIVE_LIMIT,
            "radial_window_cage_relative_volume_limit":
                RADIAL_WINDOW_CAGE_STEP_LIMIT if special else None,
            "precision_notice": worst_relative_error > STEP_PRECISION_NOTICE,
            "worst_bbox_error_mm": worst_bbox_error_mm,
            "worst_part_centroid_error_mm": worst_position_error_mm,
            "allowed_part_centroid_error_mm": max(r["allowed_centroid_error_mm"]
                                                  for r in measurements),
            "default_centroid_limit_mm": STEP_POSITION_ERROR_LIMIT_MM,
            "radial_window_cage_centroid_limit_mm":
                RADIAL_WINDOW_CAGE_POSITION_LIMIT_MM if special else None,
            "per_instance_metrics": measurements,
            "all_instances_within_limits": all(r["within_limits"] for r in measurements),
            "source_bounds_mm": src_bounds,
            "imported_bounds_mm": step_bounds,
        },
        "limitations": [
            "Imported STEP solid identity is matched geometrically against labeled source instances",
            "STEP geometric validity/interchange is not contact-stress, clearance, or manufacturing approval",
        ],
    }

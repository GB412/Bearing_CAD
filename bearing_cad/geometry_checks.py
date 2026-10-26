"""Deterministic OCCT geometry diagnostics; not engineering sign-off."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SolidReport:
    valid: bool
    closed: bool
    solids: int
    volume_mm3: float
    extents_mm: tuple[float, float, float]


def inspect_solid(shape) -> SolidReport:
    """Inspect exactly one B-Rep solid without silently repairing invalid geometry."""
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer
    value = shape.val() if isinstance(shape, cq.Workplane) else shape
    if value is None or value.isNull():
        raise ValueError("Null or empty B-Rep")
    solids = value.Solids()
    if len(solids) != 1:
        raise ValueError(f"Expected one solid, found {len(solids)}")
    solid = solids[0]
    shells = solid.Shells()
    closed = bool(shells) and all(shell.Closed() for shell in shells)
    valid = bool(BRepCheck_Analyzer(solid.wrapped).IsValid()) and solid.isValid()
    volume = solid.Volume()
    bbox = solid.BoundingBox()
    sizes = (bbox.xlen, bbox.ylen, bbox.zlen)
    return SolidReport(valid and closed and math.isfinite(volume) and volume > 0,
                       closed, len(solids), volume, sizes)


def interference_volume(shape_a, shape_b) -> float:
    """Return intersecting volume in mm³; zero-volume contact is not penetration."""
    import cadquery as cq
    a = shape_a.val() if isinstance(shape_a, cq.Workplane) else shape_a
    b = shape_b.val() if isinstance(shape_b, cq.Workplane) else shape_b
    if not a.isValid() or not b.isValid():
        raise ValueError("Invalid input for interference test")
    return float(a.intersect(b).Volume())

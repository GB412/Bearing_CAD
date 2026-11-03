"""Reusable OCCT B-Rep primitives; dimensions in mm, axis along Z."""
from __future__ import annotations

import math
from collections.abc import Sequence


def _positive_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive (mm)")
    return float(value)


def annulus(bore_d_mm: float, outside_d_mm: float, width_mm: float):
    """Closed centered Z-axis ring; return a CadQuery Workplane."""
    import cadquery as cq
    d = _positive_number(bore_d_mm, "bore_d_mm")
    D = _positive_number(outside_d_mm, "outside_d_mm")
    B = _positive_number(width_mm, "width_mm")
    if d >= D:
        raise ValueError("bore_d_mm must be smaller than outside_d_mm")
    return cq.Workplane("XY").circle(D / 2).circle(d / 2).extrude(B).translate((0, 0, -B / 2))


def revolve_radial_profile(points: Sequence[tuple[float, float]]):
    """Revolve a closed (r_mm, z_mm) profile around Z.

    Geometric profile feasibility beyond nonzero radius belongs to builders.
    """
    import cadquery as cq
    if len(points) < 3:
        raise ValueError("Revolved profile needs at least three vertices")
    normalized = []
    for r, z in points:
        if (type(r) not in (int, float) or type(z) not in (int, float)
                or not math.isfinite(r) or not math.isfinite(z) or r <= 0):
            raise ValueError("Profile needs finite coordinates and positive radius")
        normalized.append((float(r), float(z)))
    return cq.Workplane("XZ").polyline(normalized).close().revolve(360, (0, 0), (0, 1))


def sphere(diameter_mm: float):
    import cadquery as cq
    d = _positive_number(diameter_mm, "diameter_mm")
    return cq.Workplane("XY").sphere(d / 2)


def cylindrical_roller(diameter_mm: float, length_mm: float):
    """Plain cylindrical roller centered along Z (no crown or chamfer)."""
    import cadquery as cq
    d = _positive_number(diameter_mm, "diameter_mm")
    length = _positive_number(length_mm, "length_mm")
    return cq.Workplane("XY").circle(d / 2).extrude(length).translate((0, 0, -length / 2))



def profiled_cylindrical_roller(
    diameter_mm: float, length_mm: float, *,
    profile: str = "plain",
    chamfer_mm: float = 0.0,
    crown_relief_mm: float = 0.0,
):
    """Create a continuous revolved roller with optional end chamfers/crown.

    The 'plain' branch reproduces original RoBAS CylinderRoller.Draw3DRoller
    (Eyeshot Solid.CreateCylinder). Chamfered/crowned branches are *new CAD
    enhancements*, not RoBAS certified correction profiles. crown_relief_mm
    is the radial reduction at each crown end relative to the center radius.
    The crowned branch uses a smooth interpolating spline, not tessellation.
    """
    d = _positive_number(diameter_mm, "diameter_mm")
    length = _positive_number(length_mm, "length_mm")
    if profile not in {"plain", "chamfered", "crowned"}:
        raise ValueError("Unsupported roller profile")
    for label, value in (("chamfer_mm", chamfer_mm),
                         ("crown_relief_mm", crown_relief_mm)):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(label + " must be finite and nonnegative")
    c = float(chamfer_mm)
    relief = float(crown_relief_mm)
    if profile == "plain":
        if c or relief:
            raise ValueError("Plain roller cannot have chamfer or crown relief")
        return cylindrical_roller(d, length)
    if not 0 < c < min(d / 8, length / 4):
        raise ValueError("Roller end chamfer is outside CAD-safe profile limits")
    if profile == "chamfered" and relief:
        raise ValueError("Chamfer-only roller cannot have crown relief")
    if profile == "crowned" and not 0 < relief < min(d / 20, c):
        raise ValueError("Roller crown relief is outside CAD-safe profile limits")

    import cadquery as cq
    radius, half = d / 2, length / 2
    active = half - c
    end_radius = radius - relief
    sketch = (cq.Workplane("XZ")
              .moveTo(0, -half)
              .lineTo(end_radius - c, -half)
              .lineTo(end_radius, -active))
    if profile == "crowned":
        # A symmetric quadratic relief law is sampled along a continuous
        # interpolated B-spline meridian; the center retains nominal diameter.
        meridian = [
            (radius - relief * (abs(z) / active) ** 2, z)
            for z in (-active + 2 * active * i / 24 for i in range(1, 25))
        ]
        sketch = sketch.spline(meridian, includeCurrent=True)
    else:
        sketch = sketch.lineTo(end_radius, active)
    sketch = (sketch.lineTo(end_radius - c, half)
                    .lineTo(0, half).close())
    return sketch.revolve(360, (0, 0), (0, 1))


def circular_positions(pitch_d_mm: float, count: int, z_mm: float = 0.) -> tuple[tuple[float, float, float], ...]:
    """Z distinct positions around the pitch circle (no duplicate endpoint)."""
    D = _positive_number(pitch_d_mm, "pitch_d_mm")
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError("count must be integer between 1 and 10000")
    if type(z_mm) not in (int, float) or not math.isfinite(z_mm):
        raise ValueError("z_mm must be finite")
    R = D / 2
    return tuple((R * math.cos(2 * math.pi * i / count),
                  R * math.sin(2 * math.pi * i / count), float(z_mm)) for i in range(count))

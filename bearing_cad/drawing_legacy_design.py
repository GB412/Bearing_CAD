"""Conservative RoBAS DGB drawing values from source-backed geometry/cage inputs.

References:
  RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs
  RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBOptimizer.cs
  RoBAS/BearingModel/Cage/StampingCage.cs
  RoBAS/Controls/DeepGrooveBallServer/DeepGrooveBallBearingServer.cs
  RoBAS/BearingModel/Race/{InnerRace,OuterRace}/SingleRowDeepGroove*.cs

Not the complete RoBAS Optimizer. No invented material/tolerance parameters.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .contracts import StampedCageSpec
from .drawing_legacy_chamfer import _chamfer_source
from .drawing_variables import DrawingDataError
from .robas_sizing import dgb_radial_clearance_mm


def _number(value, key):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise DrawingDataError("Expected finite positive RoBAS dimension: " + key)
    return float(value)


def _cage_diameter_tolerance(d: float) -> float:
    """StampingCage.DetermineDiameterTolerance, in mm."""
    for upper, value in (
        (18, .05), (30, .06), (50, .08), (80, .09),
        (120, .11), (180, .12), (250, .14), (math.inf, .14),
    ):
        if d <= upper:
            return value
    raise AssertionError("Unreachable")


def _pocket_tolerance(ball_d: float) -> float:
    """StampingCage.DetermineTolerance, in mm."""
    for upper, value in (
        (6, .03), (10, .04), (14, .05), (18, .06),
        (24, .07), (40, .08), (math.inf, .10),
    ):
        if ball_d <= upper:
            return value
    raise AssertionError("Unreachable")


def _rivet_tolerances(total_board_mm: float) -> tuple[float, float] | None:
    """StampingCage rivet-hole bounds; original has undefined thickness gaps."""
    if 1 <= total_board_mm <= 2.4:
        return (.15, .08)
    if 3 <= total_board_mm <= 7:
        return (.20, .10)
    return None


def _chamfer_radius(value: str) -> float | None:
    """Mirror the old numeric part of e.g. '0.2max', but reject ambiguity."""
    if not isinstance(value, str):
        return None
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    if len(numbers) != 1:
        return None
    parsed = float(numbers[0])
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _race_weights(p: dict, *, di: float, de: float, chamfer: list[str]) -> dict:
    """Original two CalculateWeight formulas, only with known chamfer data.

    Historical RoBAS assumes 7.8 g/cm^3 and old raceway profiles. These are
    RoBAS nominal *drawing mass estimates*, NOT exact new OCCT shape masses.
    """
    if len(chamfer) < 12:
        return {}
    r, r8 = _chamfer_radius(chamfer[2]), _chamfer_radius(chamfer[11])
    if r is None or r8 is None:
        return {}
    need = (
        "bore_d_mm", "outside_d_mm", "width_mm",
        "inner_shoulder_d_mm", "outer_shoulder_d_mm",
        "inner_groove_radius_mm", "outer_groove_radius_mm",
    )
    if any(key not in p for key in need):
        return {}
    d, D, B = (_number(p[k], k) for k in
               ("bore_d_mm", "outside_d_mm", "width_mm"))
    d2, D2 = (_number(p[k], k) for k in
              ("inner_shoulder_d_mm", "outer_shoulder_d_mm"))
    ri, re_ = (_number(p[k], k) for k in
               ("inner_groove_radius_mm", "outer_groove_radius_mm"))
    outer = 7.8 * (
        .785 * (D**2 - D2**2) * B -
        1.349 * D * r**2 - 2.245 * r8**2 * D2 -
        1.345 * de * re_**2 + .6176 * re_**3
    ) / 1_000_000
    inner = 7.8 * (
        .785 * (d2**2 - d**2) * B -
        1.349 * d * r**2 - 2.245 * r8**2 * d2 -
        1.345 * di * ri**2 + .6176 * ri**3
    ) / 1_000_000
    if not all(math.isfinite(x) and x > 0 for x in (outer, inner)):
        return {}
    return {"outer_race_weight_kg": outer, "inner_race_weight_kg": inner}


def derive_dgb_drawing_values(*, parameters: dict,
                              cage: StampedCageSpec | None = None,
                              resources: Path | None = None,
                              chamfer1_mm: float | None = None,
                              radial_clearance_group: str | None = None,
                              ) -> tuple[dict, dict]:
    """Return compatible 'legacy_values' for the existing SetCADTextValue port.

    Computes original DGB basic groove and stamping-cage labels using *actual
    confirmed request parameters*. A non-stamping preview cage never silently
    produces stamping engineering dimensions. Partial results are allowed.
    """
    p = parameters
    d = _number(p["bore_d_mm"], "bore_d_mm")
    Dpw = _number(p["pitch_d_mm"], "pitch_d_mm")
    Dw = _number(p["ball_d_mm"], "ball_d_mm")
    B = _number(p["width_mm"], "width_mm")
    count = p["ball_count"]
    if type(count) is not int or not 1 <= count <= 64 or Dpw <= Dw:
        raise DrawingDataError("Invalid RoBAS DGB count or pitch geometry")
    updates = {
        "inner_groove_d_mm": Dpw - Dw,
        "inner_groove_position_mm": B / 2,
    }
    warnings = []
    radial = dgb_radial_clearance_mm(d)
    if radial is None:
        warnings.append("DGB_OUTER_GROOVE_CLEARANCE_OUTSIDE_ROBAS_RANGE")
    elif radial_clearance_group not in (None, "C0"):
        # The original DGBGeometry applies a C0-like empirical clearance;
        # do not combine it with an explicitly selected C2/C3/C4/C5 group.
        warnings.append("DGB_OUTER_GROOVE_NEEDS_SOURCE_C0_CLEARANCE")
    else:
        updates["outer_groove_d_mm"] = Dpw + Dw + radial

    if isinstance(cage, StampedCageSpec):
        S = _number(cage.board_thickness_mm, "board_thickness_mm")
        Rc = Dw / 2 + _number(cage.pocket_clearance_mm, "pocket_clearance_mm")
        Dc = _number(cage.outside_d_mm, "cage.outside_d_mm")
        dc = _number(cage.inner_d_mm, "cage.inner_d_mm")
        if not dc < Dpw < Dc:
            raise DrawingDataError("Stamped cage must straddle ball pitch diameter")
        # The current 3D stamping shell explicitly uses Rc=Dw/2+pocket clearance.
        # RoBAS's *default* Rc=0.55 Dw is not silently applied to this model.
        updates.update({
            "cage_pitch_d_mm": Dpw,
            "cage_pitch_tolerance_mm": .025 if Dpw <= 80 else .05,
            "cage_outer_d_mm": Dc,
            "cage_outer_tolerance_mm": _cage_diameter_tolerance(Dc),
            "cage_inner_d_mm": dc,
            "cage_inner_tolerance_mm": _cage_diameter_tolerance(dc),
            "cage_board_thickness_mm": S,
            "cage_sphere_radius_mm": Rc,
            "cage_sphere_upper_tolerance_mm": _pocket_tolerance(Dw),
            "cage_pocket_spacing_mm": Dpw * math.sin(math.pi / count),
            "cage_pocket_rivet_spacing_mm": Dpw * math.sin(math.pi / (2 * count)),
            "cage_rivet_hole_d_mm": (
                _number(cage.rivet_shaft_d_mm, "rivet_shaft_d_mm") +
                2 * _number(cage.rivet_hole_clearance_mm, "rivet_hole_clearance_mm")
            ),
        })
        rivet_tol = _rivet_tolerances(2 * S)
        if rivet_tol:
            updates["rivet_hole_upper_tolerance_mm"] = rivet_tol[0]
            updates["rivet_hole_lower_tolerance_mm"] = rivet_tol[1]
        else:
            warnings.append("RIVET_HOLE_TOLERANCE_NOT_DEFINED_AT_BOARD_THICKNESS")
        # Original StampingCage.CalculateWeight nominal/empirical equation.
        cage_mass = (10.35 * (Dpw + .36388 * count * (Rc + .5 * S)) *
                     (Dc - dc) * S / 1_000_000)
        if cage_mass > 0 and math.isfinite(cage_mass):
            updates["half_cage_weight_kg"] = cage_mass
    else:
        warnings.append("STAMPING_CAGE_DIMENSIONS_NOT_AVAILABLE_FOR_SELECTED_CAGE")

    if resources is not None and chamfer1_mm is not None:
        chamfer = _chamfer_source(
            resources, "rolling.deep_groove_ball", chamfer1_mm)
        if chamfer is not None and "outer_groove_d_mm" in updates:
            weights = _race_weights(p,
                di=updates["inner_groove_d_mm"],
                de=updates["outer_groove_d_mm"], chamfer=chamfer)
            updates.update(weights)
            if not weights:
                warnings.append("RACE_WEIGHT_NEEDS_COMPLETE_ROBAS_CHAMFER_VALUES")
        else:
            warnings.append("RACE_WEIGHT_NEEDS_MATCHING_ROBAS_CHAMFER_AND_GROOVE")
    else:
        warnings.append("RACE_WEIGHT_NEEDS_EXPLICIT_CHAMFER_SELECTION")

    return updates, {
        "source": "RoBAS DGBGeometry/DGBOptimizer/StampingCage/SetCADTextValue",
        "autofilled_input_keys": sorted(updates),
        "warnings": warnings,
        "mass_basis": (
            "RoBAS empirical nominal formula, not OCCT volume-derived mass"
            if any(key.endswith("_weight_kg") for key in updates) else None
        ),
    }

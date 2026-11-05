"""Original RoBAS ACBGeometry 2D groove and lock-height calculations.

Source call chain:
  RoBAS/Frm/Dialog/FrmNewFile.cs:398 passes Deg2Rad(contactAngular).
  RoBAS/Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs:46-90
  RoBAS/Core/BallBearing/AngularContactBallBearing/
      AngularContactBallBearing.cs:279-296 CalculateLockHeight
  RoBAS/Controls/AngularContactBallServer/
      AngularContactBallBearingServer.cs:SetCADTextValue (De, di, a, ae, ai, t_SK).
Geometry inputs are explicit current CAD dimensions in millimetres.
Only auto-fill if the caller selected the actual original source curvature
factors (fi=.515, fe=.525); never silently mix a custom OCCT design with
RoBAS's original fixed-radius calculations.
"""
from __future__ import annotations

import math

from .drawing_variables import DrawingDataError


def _positive(p, key):
    value = p[key]
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise DrawingDataError("Invalid RoBAS ACB source dimension: " + key)
    return float(value)


def derive_acb_race_drawing_values(parameters: dict) -> tuple[dict, dict]:
    """Derive geometric labels and literal legacy lock-height only on source profile.

    Original getters round to 2 decimal mm before SetCADTextValue formats
    De/di with f3 and a with f1. Preserve that two-stage rounding.
    The original thermal-expansion constant is suspicious but intentionally
    copied *literally* for parity; this is not physical/engineering approval.
    """
    dw = _positive(parameters, "ball_d_mm")
    pw = _positive(parameters, "pitch_d_mm")
    b = _positive(parameters, "width_mm")
    d = _positive(parameters, "bore_d_mm")
    ri = _positive(parameters, "inner_groove_radius_mm")
    ro = _positive(parameters, "outer_groove_radius_mm")
    alpha = _positive(parameters, "contact_angle_deg")
    if not 0 < alpha < 90 or not 0 < dw < pw:
        raise DrawingDataError("Invalid RoBAS ACB angle/rolling-element geometry")

    evidence = {
        "source": "RoBAS ACBGeometry / SingleRowAngularContactRace / CalculateLockHeight",
        "autofilled_input_keys": [],
        "warnings": [],
        "scope": "SOURCE_SPECIFIC_GEOMETRIC_LABELS_NOT_EYESHOT_APPROVAL",
    }
    if not (math.isclose(ri, .515*dw, rel_tol=0, abs_tol=1e-8)
            and math.isclose(ro, .525*dw, rel_tol=0, abs_tol=1e-8)):
        evidence["warnings"].append("ACB_CUSTOM_CURVATURE_NOT_ORIGINAL_ROBAS_PROFILE")
        return {}, evidence

    a = math.radians(alpha)
    de = round(pw + 2*ro - (2*ro-dw)*math.cos(a), 2)
    di = round(pw - 2*ri + (2*ri-dw)*math.cos(a), 2)
    inner_pos = round(b/2 + (ri-dw/2)*math.sin(a), 2)
    outer_pos = round(b/2 + (ro-dw/2)*math.sin(a), 2)
    # Original .NET constant in CalculateLockHeight is 11800000 (literally),
    # NOT a presumed 1.18e-5. Do not "correct" C# without source approval.
    delta_t = .01 if d <= 30 else (.02 if d <= 80 else .03)
    kt = (.515+.525-1)*(1-math.cos(a))/(1+11800000*90)
    lock_height = .00053*de + kt*dw - .5*delta_t
    if lock_height <= 0:
        evidence["warnings"].append("ACB_SOURCE_LOCK_HEIGHT_NOT_POSITIVE")
    result = {
        "outer_groove_d_mm": de,
        "inner_groove_d_mm": di,
        "inner_groove_position_mm": inner_pos,
        "outer_groove_position_mm": outer_pos,
        "inner_race_groove_position_mm": inner_pos,
    }
    if lock_height > 0 and math.isfinite(lock_height):
        # The original LockHeight property rounds to 0.01 mm.
        result["lock_height_mm"] = round(lock_height, 2)
        evidence["warnings"].append("ACB_SOURCE_LOCK_HEIGHT_LITERAL_THERMAL_CONSTANT_UNREVIEWED")
    evidence["autofilled_input_keys"] = sorted(result)
    evidence["warnings"].append("ACB_GROOVE_SOURCE_GEOMETRY_NOT_EYESHOT_ENTITY_EQUIVALENCE")
    return result, evidence

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
from .drawing_standards import (
    StandardsLookupError, original_bearing_diameter_getter_mm,
    original_ball_diameter_getter_mm,
)


def _positive(p, key):
    value = p[key]
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise DrawingDataError("Invalid RoBAS ACB source dimension: " + key)
    return float(value)


def _source_getter(value, getter, label):
    try:
        return getter(value)
    except StandardsLookupError as error:
        raise DrawingDataError(f"{label}: {error}") from error


def derive_acb_race_drawing_values(parameters: dict) -> tuple[dict, dict]:
    """Derive geometric labels and literal legacy lock-height only on source profile.

    Original getters round to 2 decimal mm before SetCADTextValue formats
    De/di with f3 and a with f1. Preserve that two-stage rounding.
    The original thermal-expansion constant is suspicious but intentionally
    copied *literally* for parity; this is not physical/engineering approval.
    """
    # Keep raw geometry inputs for the original ACBGeometry formulas. The
    # C# getter values are applied only at the SetCADTextValue read points.
    dw = _positive(parameters, "ball_d_mm")
    dw_getter = _source_getter(dw, original_ball_diameter_getter_mm, "ball diameter")
    pw = _positive(parameters, "pitch_d_mm")
    b = _positive(parameters, "width_mm")
    d = _positive(parameters, "bore_d_mm")
    d_getter = _source_getter(d, original_bearing_diameter_getter_mm, "bore")
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
    de_raw = pw + 2*ro - (2*ro-dw)*math.cos(a)
    di_raw = pw - 2*ri + (2*ri-dw)*math.cos(a)
    inner_pos_raw = b/2 + (ri-dw/2)*math.sin(a)
    outer_pos_raw = b/2 + (ro-dw/2)*math.sin(a)
    de = _source_getter(de_raw, original_bearing_diameter_getter_mm, "outer groove diameter")
    di = _source_getter(di_raw, original_bearing_diameter_getter_mm, "inner groove diameter")
    inner_pos = _source_getter(inner_pos_raw, original_bearing_diameter_getter_mm,
                               "inner groove position")
    outer_pos = _source_getter(outer_pos_raw, original_bearing_diameter_getter_mm,
                               "outer groove position")
    # Original .NET constant in CalculateLockHeight is 11800000 (literally),
    # NOT a presumed 1.18e-5. Do not "correct" C# without source approval.
    delta_t = .01 if d_getter <= 30 else (.02 if d_getter <= 80 else .03)
    kt = (.515+.525-1)*(1-math.cos(a))/(1+11800000*90)
    lock_height_raw = .00053*de + kt*dw_getter - .5*delta_t
    if lock_height_raw <= 0:
        evidence["warnings"].append("ACB_SOURCE_LOCK_HEIGHT_NOT_POSITIVE")
        lock_height = lock_height_raw
    else:
        lock_height = _source_getter(lock_height_raw, original_bearing_diameter_getter_mm,
                                     "lock height")
    result = {
        "outer_groove_d_mm": de,
        "inner_groove_d_mm": di,
        "inner_groove_position_mm": inner_pos,
        "outer_groove_position_mm": outer_pos,
        "inner_race_groove_position_mm": inner_pos,
    }
    # RoBAS ACBGeometry / SingleRowAngularContactRace set the sidewall
    # diameters from the *unrounded* groove diameter, then expose the
    # millimetre getter rounded to 0.01. On the current OCCT assembly the
    # corresponding geometric boundaries are the high inner-shoulder and
    # low outer-shoulder diameters; compare before emitting old-DWG labels.
    factor = .35 if d <= 25 else .40
    source_outer = _source_getter(de_raw - factor*dw,
                                  original_bearing_diameter_getter_mm,
                                  "outer sidewall diameter")
    source_inner = _source_getter(di_raw + factor*dw,
                                  original_bearing_diameter_getter_mm,
                                  "inner sidewall diameter")
    for output_name, shoulder_name, source_value in (
        ("outer_sidewall_d_mm", "outer_shoulder_right_d_mm", source_outer),
        ("inner_sidewall_d_mm", "inner_shoulder_left_d_mm", source_inner),
    ):
        shoulder = _positive(parameters, shoulder_name)
        # Do not apply original source-only dimensions to arbitrary OCCT
        # geometry. An unmatched nominal shoulder remains open for expert
        # review or an explicitly supplied checked legacy field.
        if math.isclose(source_value, shoulder, rel_tol=0, abs_tol=1e-6):
            result[output_name] = source_value
        else:
            evidence["warnings"].append(
                "ACB_" + shoulder_name.upper() + "_DIFFERS_FROM_ROBAS_SOURCE")

    if lock_height > 0 and math.isfinite(lock_height):
        # LockHeight is a public 0.01-mm getter; lock_height is already that value.
        result["lock_height_mm"] = lock_height
        evidence["warnings"].append("ACB_SOURCE_LOCK_HEIGHT_LITERAL_THERMAL_CONSTANT_UNREVIEWED")
    evidence["autofilled_input_keys"] = sorted(result)
    evidence["warnings"].append("ACB_GROOVE_SOURCE_GEOMETRY_NOT_EYESHOT_ENTITY_EQUIVALENCE")
    return result, evidence

"""Source-backed ACB straight-pocket-cage labels for the original RoBAS DWGs.

Source: RoBAS/BearingModel/Cage/StraightPocketCage.cs
  CalculatePocketToPocketDistance, DetermineOutsideDiameterTolerance,
  DetermineWidthTolerance, DeterminePocketDiameterUpperDeviation.
Source: RoBAS/Controls/AngularContactBallServer/
  AngularContactBallBearingServer.cs:SetCADTextValue.

The current CAD request describes the *actual* OCCT cage dimensions. The
original RoBAS constructor (D2, B, Z, Dw, Dpw) has separate defaults and
is not silently substituted for the chosen 3D geometry. The new OCCT cage
has no chamfer: the old e_ dimension is therefore NOT invented here.
"""
from __future__ import annotations

import math

from .contracts import CageSpec
from .drawing_variables import DrawingDataError


def _number(value, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise DrawingDataError("Invalid explicit ACB cage dimension: " + label)
    return float(value)


def _outside_tolerance(diameter: float) -> float | None:
    """StraightPocketCage.DetermineOutsideDiameterTolerance.

    Original code returns 0 outside the table. Zero is an undefined branch,
    not evidence of zero manufacturing tolerance.
    """
    for hi, value in (
        (18, .043), (30, .052), (50, .062), (80, .074),
        (120, .087), (180, .100), (250, .115),
    ):
        lower = {18: 10, 30: 18, 50: 30, 80: 50, 120: 80, 180: 120, 250: 180}[hi]
        if lower < diameter <= hi:
            return value
    return None


def _width_tolerance(width: float) -> float | None:
    """StraightPocketCage.DetermineWidthTolerance; no out-of-range guess."""
    for hi, value in (
        (10, .090), (18, .110), (30, .130),
        (50, .160), (80, .190),
    ):
        if 0 < width <= hi:
            return value
    return None


def derive_acb_cage_drawing_values(*, parameters: dict,
                                  cage: CageSpec | None) -> tuple[dict, dict]:
    """Use existing 3D straight-pocket cage dimensions to fill old CAD TEXT.

    The source's diameter/width tolerance tables are valid only in their
    defined ranges. Out-of-range fields stay unfilled, even where the old
    C# method returned numeric 0 as an unhandled fallback.
    """
    warnings: list[str] = []
    values: dict[str, float] = {}
    if cage is None or cage.kind != "straight_pocket":
        warnings.append("ACB_STRAIGHT_POCKET_CAGE_NOT_SELECTED")
    else:
        d_out = _number(cage.outside_d_mm, "outside_d_mm")
        d_in = _number(cage.inner_d_mm, "inner_d_mm")
        width = _number(cage.width_mm, "width_mm")
        clearance = _number(cage.pocket_clearance_mm, "pocket_clearance_mm")
        pitch = _number(parameters["pitch_d_mm"], "pitch_d_mm")
        ball_d = _number(parameters["ball_d_mm"], "ball_d_mm")
        count = parameters["ball_count"]
        if type(count) is not int or not 2 <= count <= 256 or not d_in < pitch < d_out:
            raise DrawingDataError("Invalid explicit ACB cage envelope or pocket count")
        # Unlike the legacy constructor's optional default 1.004*Dw+0.12,
        # the actual current B-Rep pocket cutter is Dw+2*clearance.
        values = {
            "cage_pitch_d_mm": pitch,
            "cage_pocket_spacing_mm": d_out * math.sin(math.pi / count),
            "cage_outer_d_mm": d_out,
            "cage_inner_d_mm": d_in,
            "cage_width_mm": width,
            "cage_pocket_d_mm": ball_d + 2 * clearance,
            "cage_pocket_d_upper_tolerance_mm": .10 if ball_d <= 18 else .15,
        }
        outer_tol = _outside_tolerance(d_out)
        inner_tol = _outside_tolerance(d_in)  # Original also uses OUTSIDE table for Dc1.
        width_tol = _width_tolerance(width)
        if outer_tol is None:
            warnings.append("ACB_CAGE_OUTER_TOLERANCE_UNDEFINED_IN_ROBAS")
        else:
            values["cage_outer_d_tolerance_mm"] = outer_tol
        if inner_tol is None:
            warnings.append("ACB_CAGE_INNER_TOLERANCE_UNDEFINED_IN_ROBAS")
        else:
            values["cage_inner_d_tolerance_mm"] = inner_tol
        if width_tol is None:
            warnings.append("ACB_CAGE_WIDTH_TOLERANCE_UNDEFINED_IN_ROBAS")
        else:
            values["cage_width_tolerance_mm"] = width_tol
        warnings.append("ACB_CAGE_CHAMFER_NOT_PRESENT_IN_OCCT_CAGE")

    return values, {
        "source": "RoBAS StraightPocketCage/ACB SetCADTextValue",
        "autofilled_input_keys": sorted(values),
        "warnings": warnings,
        "scope": "SOURCE_TOLERANCES_ON_EXPLICIT_3D_CAGE_NOT_EYESHOT_EQUIVALENCE",
    }

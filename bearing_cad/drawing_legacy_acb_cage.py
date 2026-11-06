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
    getter_precision: dict[str, int] = {}
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
        # These are original RoBAS *public getter* values, NOT a mutation of
        # the unrounded OCCT dimensions. BaseCage gets D/D1/B at 0.01 mm;
        # StraightPocketCage gets Dcp and C at 0.001, Deltac at 0.1 mm.
        # The original constructor's 1.004*Dw+0.12 pocket is NOT substituted
        # for the actual B-Rep cutter Dw + 2*clearance.
        d_out_label = round(d_out, 2)
        d_in_label = round(d_in, 2)
        width_label = round(width, 2)
        pitch_label = round(pitch, 3)
        # CalculatePocketToPocketDistance reads the PUBLIC OutsideDiameter
        # getter, rounded to 0.01 mm, before the C_ getter rounds to 0.001.
        pocket_spacing_label = round(d_out_label * math.sin(math.pi / count), 3)
        pocket_d_label = round(ball_d + 2 * clearance, 1)
        ball_d_label = round(ball_d, 3)
        values = {
            "cage_pitch_d_mm": pitch_label,
            "cage_pocket_spacing_mm": pocket_spacing_label,
            "cage_outer_d_mm": d_out_label,
            "cage_inner_d_mm": d_in_label,
            "cage_width_mm": width_label,
            "cage_pocket_d_mm": pocket_d_label,
            "cage_pocket_d_upper_tolerance_mm": .10 if ball_d_label <= 18 else .15,
        }
        getter_precision = {
            "cage_pitch_d_mm": 3, "cage_pocket_spacing_mm": 3,
            "cage_outer_d_mm": 2, "cage_inner_d_mm": 2,
            "cage_width_mm": 2, "cage_pocket_d_mm": 1,
        }
        # RoBAS SetCADTextValue calls the tolerance tables with these
        # *rounded public getter* values. The 10/18/30/... boundary matters.
        outer_tol = _outside_tolerance(d_out_label)
        inner_tol = _outside_tolerance(d_in_label)  # Source uses OUTSIDE table for Dc1.
        width_tol = _width_tolerance(width_label)
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
        "source_getter_precision_decimals": getter_precision,
        "warnings": warnings,
        "scope": "SOURCE_TOLERANCES_ON_EXPLICIT_3D_CAGE_NOT_EYESHOT_EQUIVALENCE",
    }

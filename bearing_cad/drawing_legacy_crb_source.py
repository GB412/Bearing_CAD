"""Read-only original RoBAS CRBGeometry + CRBOptimizer drawing dimensions.

RoBAS/Core/RollerBearing/CylinderRollerBreaing/CRBGeometry.cs:53-101
RoBAS/Core/RollerBearing/CylinderRollerBreaing/CRBOptimizer.cs:417-468
RoBAS/Controls/CylinderRollerBearing/CylinderRollerBearingServer.cs:SetCADTextValue

Only assert original source equivalence when the existing explicit 3D design
actually has the same zero-gap pitch and relevant integral-flange diameters.
Otherwise leave source-dependent labels open for reviewed legacy input.
"""
from __future__ import annotations

import math
from .drawing_variables import DrawingDataError


def _number(p: dict, key: str, allow_zero: bool = False) -> float:
    val = p[key]
    if type(val) not in (int, float) or not math.isfinite(val) or val < 0 or (val == 0 and not allow_zero):
        raise DrawingDataError("Invalid RoBAS CRB source dimension: " + key)
    return float(val)


def _inner_coefficient(bore: float) -> float | None:
    if 0 < bore <= 50: return .425
    if 50 < bore <= 75: return .405
    if 75 < bore <= 200: return .365
    return None


def _outer_coefficient(outside: float) -> float | None:
    if 0 < outside <= 25: return .425
    if 25 < outside <= 50: return .405
    if 50 < outside <= 200: return .365
    return None


def derive_crb_source_drawing_values(parameters: dict) -> tuple[dict,dict]:
    d = _number(parameters,"bore_d_mm")
    D = _number(parameters,"outside_d_mm")
    pitch = _number(parameters,"pitch_d_mm")
    dw = _number(parameters,"roller_d_mm")
    gap = _number(parameters,"radial_clearance_mm",allow_zero=True)
    configuration = parameters["configuration"]
    if configuration not in {"N","NU","NJ","NF","NUP"} or d >= D:
        raise DrawingDataError("Invalid RoBAS CRB flange configuration")
    evidence = {
        "source":"RoBAS CRBGeometry / CRBOptimizer sidewall equations",
        "autofilled_input_keys": [],
        "warnings": [],
        "scope":"SOURCE_PROFILE_MATCH_ONLY_NOT_ANY_CAD_PROFILE",
    }
    if not math.isclose(gap,0.0,abs_tol=1e-10) or not math.isclose(
            pitch,(d+D)/2,abs_tol=1e-7):
        evidence["warnings"].append("CRB_CUSTOM_PITCH_OR_RADIAL_GAP_NOT_ORIGINAL_ROBAS")
        return {}, evidence

    inner_groove = round(pitch-dw,2)
    outer_groove = round(pitch+dw,2)
    values = {
        "inner_groove_d_mm": inner_groove,
        "outer_groove_d_mm": outer_groove,
    }
    ki = _inner_coefficient(d)
    ko = _outer_coefficient(D)
    if configuration in {"N","NJ","NF","NUP"}:
        if ki is None:
            evidence["warnings"].append("CRB_INNER_RIB_COEFFICIENT_OUTSIDE_SOURCE_RANGE")
        else:
            source_tip = inner_groove+ki*dw
            if math.isclose(source_tip,_number(parameters,"inner_rib_tip_d_mm"),abs_tol=1e-7):
                values["inner_sidewall_d_mm"]=round(source_tip,2)
            else:
                evidence["warnings"].append("CRB_INNER_RIB_DIFFERENT_FROM_ORIGINAL_SOURCE")
    if configuration in {"NU","NJ","NF","NUP"}:
        if ko is None:
            evidence["warnings"].append("CRB_OUTER_RIB_COEFFICIENT_OUTSIDE_SOURCE_RANGE")
        else:
            source_tip = outer_groove-ko*dw
            if math.isclose(source_tip,_number(parameters,"outer_rib_tip_d_mm"),abs_tol=1e-7):
                values["outer_sidewall_d_mm"]=round(source_tip,2)
            else:
                evidence["warnings"].append("CRB_OUTER_RIB_DIFFERENT_FROM_ORIGINAL_SOURCE")

    evidence["autofilled_input_keys"]=sorted(values)
    evidence["warnings"].append("CRB_NU_NJ_NF_NUP_TEMPLATE_COMPOSITION_REQUIRES_AUTOCAD_REVIEW")
    return values,evidence

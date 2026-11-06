"""Faithful RoBAS SetCADTextValue Cr/Cor calculations (N -> kN labels).

All three drawing servers call BaseOptimizer.SearchCoeffcient(gamma, out fc,
out fo). CRBOptimizer's separate one-out overload consults its own roller CSV
only in the optimizer path, not the drawing server. Missing original CSV rows
produce legacy zero *calculation* but never a certified or valid Cr label.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from .drawing_variables import DrawingDataError
from .drawing_legacy_dimensions import number, overlay
from .drawing_standards import (
    StandardsLookupError, original_ball_diameter_getter_mm,
    original_bearing_diameter_getter_mm, original_dotnet_math_round,
)

_BALL_TYPES = {"rolling.deep_groove_ball", "rolling.angular_contact_ball"}
_ROLLER = "rolling.cylindrical_roller"
_COEFFICIENT_FILENAME = "球轴承零件相关系数.csv"
_LOOKUP_SOURCE = "BaseOptimizer.SearchCoeffcient(double, out double, out double)"


def _getter(value, operation, label):
    try:
        return operation(value)
    except StandardsLookupError as error:
        raise DrawingDataError(f"Invalid RoBAS {label}: {error}") from error


def _coefficients(resources, gamma):
    # All three *drawing servers*, including CRB, call the two-out overload
    # inherited from BaseOptimizer. That overload reads the BALL coefficient
    # table, even for CRB (source quirk, not an engineering endorsement).
    file = Path(resources) / "Resource" / _COEFFICIENT_FILENAME
    if not file.is_file() or file.is_symlink():
        raise DrawingDataError("Missing original RoBAS coefficient CSV: " + file.name)
    if file.stat().st_size > 250_000:
        raise DrawingDataError("Oversized original coefficient CSV")
    try:
        with file.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not {"Dw/Dpw", "fc", "fo"}.issubset(reader.fieldnames):
                raise DrawingDataError("RoBAS coefficient table schema mismatch")
            for row in reader:
                source_gamma = float(row["Dw/Dpw"].strip())
                if not math.isfinite(source_gamma):
                    raise DrawingDataError("Non-finite RoBAS coefficient gamma")
                # Source C# calls double.Equals on parsed gamma, NOT epsilon
                # matching. Never silently select a nearby coefficient row.
                if source_gamma == gamma:
                    fc = float(row["fc"])
                    fo = float(row["fo"])
                    if not math.isfinite(fc) or not math.isfinite(fo):
                        raise DrawingDataError("Non-finite RoBAS coefficient")
                    return fc, fo, True
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        if isinstance(exc, DrawingDataError):
            raise
        raise DrawingDataError("RoBAS coefficient lookup failed") from exc
    return 0.0, 0.0, False


def calculate_robas_loads(*, resources, bearing_type, parameters):
    """Original drawing-server formulas in newtons; no engineering approval."""
    if bearing_type not in _BALL_TYPES | {_ROLLER}:
        raise DrawingDataError("Unsupported RoBAS bearing type")
    is_roller = bearing_type == _ROLLER
    raw_diameter = number(parameters["roller_d_mm" if is_roller else "ball_d_mm"], "Dw")
    diameter = (raw_diameter if is_roller else
                _getter(raw_diameter, original_ball_diameter_getter_mm, "ball diameter"))
    pitch = _getter(number(parameters["pitch_d_mm"], "Dpw"),
                    original_bearing_diameter_getter_mm, "pitch diameter")
    count = parameters["roller_count" if is_roller else "ball_count"]
    if diameter <= 0 or pitch <= 0 or type(count) is not int or count < 1:
        raise DrawingDataError("Invalid RoBAS rolling-element design")

    gamma = original_dotnet_math_round(diameter / pitch, 2)
    fc, fo, matched = _coefficients(resources, gamma)
    if is_roller:
        length = _getter(number(parameters["roller_length_mm"], "Lw"),
                         original_bearing_diameter_getter_mm, "roller length")
        cr = 1.89 * fc * length**(7 / 9) * count**(3 / 4) * diameter**(29 / 27)
        cor = 21.6 * count * length * diameter  # independent of coefficient
    elif bearing_type == "rolling.deep_groove_ball":
        bm = 1.3
        cr = bm * fc * count**(2 / 3) * diameter**1.8 * (
            1 if diameter <= 25.4 else 3.467)
        cor = fo * count * diameter**2
    else:
        alpha = math.radians(number(parameters["contact_angle_deg"], "alpha"))
        if not 0 < alpha < math.pi / 2:
            raise DrawingDataError("Invalid contact angle")
        cosine = math.cos(alpha)
        factor = 1.3 * fc * cosine**0.7 * count**(2 / 3)
        cr = factor * diameter**1.8 if diameter <= 25.4 else (
            3.647 * factor * diameter**1.4)
        cor = fo * count * diameter**2 * cosine

    dynamic_valid = matched and fc > 0
    static_valid = is_roller or (matched and fo > 0)
    if not math.isfinite(cr) or not math.isfinite(cor) or cr < 0 or cor < 0:
        raise DrawingDataError("Invalid RoBAS load calculation result")
    warnings = []
    if not matched:
        warnings.append("ROBAS_DRAWING_COEFFICIENT_UNMATCHED_LEGACY_ZERO_NOT_VALID")
    elif fc <= 0 or (not is_roller and fo <= 0):
        warnings.append("ROBAS_NONPOSITIVE_SOURCE_COEFFICIENT_NOT_VALID")
    if is_roller:
        warnings.append("ROBAS_CRB_DRAWING_USES_BASE_BALL_CSV_NOT_ROLLER_OPTIMIZER_CSV")
    return {
        "dynamic_load_n": cr, "static_load_n": cor, "gamma": gamma,
        "fc": fc, "fo": fo, "coefficient_found": matched,
        "dynamic_load_valid": dynamic_valid, "static_load_valid": static_valid,
        "coefficient_csv": _COEFFICIENT_FILENAME,
        "coefficient_lookup_source": _LOOKUP_SOURCE,
        "status": "ROBAS_LEGACY_CALCULATION_UNREVIEWED",
        "warning": "; ".join(warnings) if warnings else None,
        "warnings": warnings,
    }


def apply_robas_loads(*, report, resources, bearing_type, parameters):
    load = calculate_robas_loads(
        resources=resources, bearing_type=bearing_type, parameters=parameters)
    updates = {}
    if load["dynamic_load_valid"]:
        updates["Cr"] = f"{load['dynamic_load_n'] / 1000:.2f}"
    if load["static_load_valid"]:
        updates["Cor"] = f"{load['static_load_n'] / 1000:.2f}"
    revised = overlay(report, updates, "robas_SetCADTextValue_ratings")
    revised["legacy_load_evidence"] = {
        "gamma": load["gamma"], "fc": load["fc"], "fo": load["fo"],
        "coefficient_found": load["coefficient_found"],
        "dynamic_load_valid": load["dynamic_load_valid"],
        "static_load_valid": load["static_load_valid"],
        "coefficient_csv": load["coefficient_csv"],
        "coefficient_lookup_source": load["coefficient_lookup_source"],
        "drawing_fields_written": sorted(updates),
        "warning": load["warning"],
    }
    return revised

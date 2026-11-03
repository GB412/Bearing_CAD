"""Apply already-audited RoBAS standard lookups to the drawing variable table.

DataControl.GetRoughness, GetWidthDeviation and GetRadialClearance were
previously ported as standalone read-only lookups, but were never invoked by
the actual 2D DXF generation path. Each branch is independent: an unknown
optional clearance selection must not lead to a guessed value.
"""
from __future__ import annotations

from pathlib import Path

from .drawing_legacy_dimensions import overlay
from .drawing_standards import (
    get_radial_clearance, get_roughness, get_width_deviation, StandardsLookupError,
)


def apply_robas_drawing_standards(*, report: dict, resources: Path,
                                  bearing_type: str, bore_d_mm: float,
                                  accuracy_class: str | None = None,
                                  diameter_series: str | None = None,
                                  radial_clearance_group: str | None = None) -> dict:
    """Populate only existing design-selected RoBAS source-table values.

    The drawing is still not approved for manufacturing. Unsupported or
    unavailable source rows stay blank with an explicit warning; no filler
    values, inferred radial clearance groups, or new tolerance standards.
    """
    result = report
    evidence: list[dict] = []
    warnings: list[str] = []

    if accuracy_class is not None:
        try:
            roughness = get_roughness(
                resources=resources, bearing_type=bearing_type,
                bore_d_mm=bore_d_mm, accuracy_class=accuracy_class)
        except StandardsLookupError as error:
            warnings.append("ROUGHNESS_UNAVAILABLE: " + str(error))
        else:
            result = overlay(result, roughness["values"], "robas_GetRoughness")
            evidence.append({"kind": "roughness", "source": roughness["source"],
                             "accuracy_class": accuracy_class})

    if diameter_series is not None:
        try:
            width = get_width_deviation(
                resources=resources, bearing_type=bearing_type,
                bore_d_mm=bore_d_mm, size_series=diameter_series)
        except StandardsLookupError as error:
            warnings.append("WIDTH_DEVIATION_UNAVAILABLE: " + str(error))
        else:
            result = overlay(result, {
                "B_Upper": width["upper_mm"], "B_Lower": width["lower_mm"],
            }, "robas_GetWidthDeviation")
            evidence.append({"kind": "width_deviation", "source": width["source"],
                             "diameter_series": diameter_series})

    if radial_clearance_group is not None:
        if radial_clearance_group not in ("C2", "C0", "C3", "C4", "C5"):
            raise StandardsLookupError("Unknown radial clearance group")
        try:
            clearance = get_radial_clearance(
                resources=resources, bearing_type=bearing_type,
                bore_d_mm=bore_d_mm, group=radial_clearance_group)
        except StandardsLookupError as error:
            warnings.append("RADIAL_CLEARANCE_UNAVAILABLE: " + str(error))
        else:
            result = overlay(result, {
                "Cmin": format(clearance["minimum_mm"], ".15g"),
                "Cmax": format(clearance["maximum_mm"], ".15g"),
            }, "robas_GetRadialClearance")
            evidence.append({"kind": "radial_clearance", "source": clearance["source"],
                             "group": radial_clearance_group})

    result = dict(result)
    result["standard_lookup_evidence"] = evidence
    result["standard_lookup_warnings"] = warnings
    result["radial_clearance_group"] = radial_clearance_group
    return result

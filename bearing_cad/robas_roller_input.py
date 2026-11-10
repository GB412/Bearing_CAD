"""Prepare N-type cylindrical roller DATA from an explicit RoBAS reference."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
from typing import Mapping

from .contracts import BearingRequest, BearingType
from .robas_data import (
    COMMON_HEAD, COMMON_TAIL, DataDocument, DataValue, Field,
    check_geometry, dotnet_round, profile_overrides,
)


_RECORD_FIELDS = COMMON_HEAD + (
    ("rec 5B.1", ("bReDia", "bReCrn", "bReLen", "bReCenLen", "bCorRad1", "bCorRad2", "pitchDia", "freeIntCls")),
    ("rec 5B.2", ("raceLandLmt1", "raceCenLen1", "raceCrn1", "raceLandLmt2", "raceCenLen2", "raceCrn2", "rmsAspHt1", "rmsAspHt2")),
) + COMMON_TAIL

ROLLER_RECORD_LABELS = tuple(label for label, _ in _RECORD_FIELDS)


class RollerDataError(ValueError):
    """Invalid or unsupported N-type RoBAS input."""


@dataclass(frozen=True)
class RollerDataDocument(DataDocument):
    _fields = _RECORD_FIELDS
    _family = "roller"
    _bearing_code = 2
    _error = RollerDataError


def geometry_updates(request: BearingRequest) -> dict[Field, float | int]:
    """Map confirmed nominal geometry and the N-type SetAnalysisValue chain."""
    if request.bearing_type is not BearingType.CYLINDRICAL:
        raise RollerDataError("bearing_type must be rolling.cylindrical_roller")
    p = request.parameters
    if p["configuration"] != "N":
        raise RollerDataError("parameters.configuration must be N")
    if p.get("roller_profile", "plain") != "plain":
        raise RollerDataError("parameters.roller_profile must be plain")
    for field in ("roller_end_chamfer_mm", "roller_crown_relief_mm"):
        if p.get(field, 0) != 0:
            raise RollerDataError(f"parameters.{field} must be zero for the supported plain CAD roller")

    # CRBGeometry stores m. Its getters round to 0.01 mm before setting
    # the race, cage, and CylinderRoller model properties.
    def mm(metres: float) -> float:
        return dotnet_round(metres * 1000, 2)

    bore_m, od_m, width_m = (float(p[key]) / 1000 for key in ("bore_d_mm", "outside_d_mm", "width_mm"))
    pitch_m, roller_m, length_m = (float(p[key]) / 1000 for key in ("pitch_d_mm", "roller_d_mm", "roller_length_mm"))
    bore, od, width = mm(bore_m), mm(od_m), mm(width_m)
    pitch, roller, length = mm(pitch_m), mm(roller_m), mm(length_m)
    count = int(p["roller_count"])
    # SingleRowCylinderInnerRace sets OutsideDiameter from GrooveDiameter,
    # even for N with two inner flanges. It is independent of the flange tip.
    gap_m = float(p["radial_clearance_mm"]) / 1000
    inner_race_od = mm(pitch_m - roller_m - 2 * gap_m)
    # The N outer ring has no physical flange, but the source uses its
    # SidewallDiameter model value for cageCls1. CAD stores this design value.
    outer_sidewall = mm(float(p["outer_rib_tip_d_mm"]) / 1000)

    if request.cage is None:
        # CRBGeometry and CylinderPocketCage constructors. Cage dimensions
        # use the unrounded geometry values; the pocket uses rounded Dw.
        cage_outer = mm(pitch_m + 0.5 * roller_m)
        cage_inner = mm(pitch_m - 0.45 * roller_m)
        cage_width = mm(0.97 * width_m)
        pocket_d = (1.02 * roller / 1000) * 1000
        pocket_clearance = (pocket_d - roller) / 2
        pocket_length = 1.02 * length
    else:
        cage = request.cage
        if cage.kind != "cylindrical_window":
            raise RollerDataError("cage.kind must be cylindrical_window")
        cage_outer = mm(cage.outside_d_mm / 1000)
        cage_inner = mm(cage.inner_d_mm / 1000)
        cage_width = mm(cage.width_mm / 1000)
        pocket_clearance = cage.pocket_clearance_mm
        pocket_length = length + 2 * pocket_clearance
    if not bore < inner_race_od < cage_inner < pitch < cage_outer < outer_sidewall < od:
        raise RollerDataError("cage diameters or parameters.outer_rib_tip_d_mm conflict with the N race/pitch geometry")
    if not pocket_length < cage_width <= width:
        raise RollerDataError("cage.width_mm must exceed the window length and fit within width_mm")
    if count > 1 and pitch * math.sin(math.pi / count) <= roller + 2 * pocket_clearance:
        raise RollerDataError("parameters.roller_count or cage.pocket_clearance_mm makes adjacent windows intersect")

    return {
        (5, "nRe"): count,
        **{(6, f"kStaticConstraint{i}"): value for i, value in enumerate((1, 1, 0, 1, 1), 1)},
        **{(7, f"kPltElemInd{i}"): value for i, value in enumerate((1, count + 1, 0, 0, 0, 0), 1)},
        (9, "brgBore"): bore / 1000,
        (9, "brgOD"): od / 1000,
        (9, "shftID"): (bore / 5) / 1000,
        (9, "hsngOD"): (od * 1.14) / 1000,
        (9, "raceWidth1"): width / 1000,
        (9, "raceWidth2"): width / 1000,
        (10, "bReDia"): roller / 1000,
        (10, "bReCrn"): 1.0e10,
        (10, "bReLen"): length / 1000,
        (10, "bReCenLen"): length / 1000,
        (10, "pitchDia"): pitch / 1000,
        # Direct C# backing-field writes retain the mm getter magnitude.
        (11, "raceLandLmt1"): length,
        (11, "raceCenLen2"): length,
        (12, "kPoctype"): 0,
        **{(12, f"iCageGuide{i}"): value for i, value in enumerate((1, 1, 0, 0), 1)},
        (13, "cageDia1"): cage_outer / 1000,
        (13, "cageDia2"): cage_inner / 1000,
        (13, "cageWidth"): cage_width / 1000,
        (13, "cageCls1"): (outer_sidewall - cage_outer) / 1000,
        (13, "cageCls2"): (cage_inner - inner_race_od) / 1000,
        (13, "bPocCls1"): pocket_clearance,
        (14, "cageGsDia1"): cage_outer / 1000,
        (14, "cageGsWidth1"): cage_width / 1000,
        (14, "cageGsPos1"): (0.5 * cage_width) / 1000,
        (14, "cageGsCls1"): (od - cage_outer) / 1000,
        (15, "cageGsDia2"): cage_outer / 1000,
        (15, "cageGsWidth2"): cage_width / 1000,
        (15, "cageGsPos2"): (0.5 * cage_width) / 1000,
        (15, "cageGsCls2"): (od - cage_outer) / 1000,
    }


def update_roller_data(
    reference_data: str | Path, request: BearingRequest | None, *,
    reference_configuration: str, geometry_mode: str,
    operating_updates: Mapping[Field, DataValue],
    analysis_free_clearance_mm: float | None = None,
    allow_reference_geometry_mismatch: bool = False,
    solver_updates: Mapping[Field, DataValue] | None = None,
    material_updates: Mapping[Field, DataValue] | None = None,
    lubricant_updates: Mapping[Field, DataValue] | None = None,
) -> RollerDataDocument:
    """Reproduce a caller-verified N profile, or overlay confirmed N geometry.

    DATA does not identify the CAD flange arrangement. The caller supplies
    the original model's configuration. Explicit operating overrides use DATA
    units and the BaseBC speed linkage. Solver free clearance is an independent
    analysis input and is never inferred from CAD's one-sided radial gap.
    """
    if reference_configuration != "N":
        raise RollerDataError("reference_configuration must be N, from the source bearing model")
    base = RollerDataDocument.read(reference_data)
    for field in ("kFlngInd11", "kFlngInd12", "kFlngInd21", "kFlngInd22"):
        if float(base.value(5, field)) != 0:
            raise RollerDataError(f"rec 3.2.{field} must be zero for the audited N profile")
    if float(base.value(6, "kChrn")) != 0 or float(base.value(10, "bReCrn")) != 1.0e10:
        raise RollerDataError("rec 3.3.kChrn and rec 5B.1.bReCrn must match the audited plain N profile")
    if geometry_mode not in {"legacy_data", "cad_geometry"}:
        raise RollerDataError("geometry_mode must be legacy_data or cad_geometry")
    if geometry_mode == "legacy_data" and request is not None:
        raise RollerDataError("legacy_data mode must not receive a CAD request")
    if geometry_mode == "cad_geometry" and request is None:
        raise RollerDataError("cad_geometry mode requires a confirmed BearingRequest")

    values = profile_overrides(
        base, operating=operating_updates, solver=solver_updates,
        material=material_updates, lubricant=lubricant_updates,
    )
    steps = (0, "nStps")
    if steps in values:
        try:
            count = int(str(values[steps]))
        except ValueError:
            raise RollerDataError("rec 1.nStps must be a positive integer") from None
        if count <= 0:
            raise RollerDataError("rec 1.nStps must be a positive integer")
        values[steps] = count
    if analysis_free_clearance_mm is not None:
        if (type(analysis_free_clearance_mm) not in (int, float)
                or not math.isfinite(analysis_free_clearance_mm) or analysis_free_clearance_mm < 0):
            raise RollerDataError("analysis_free_clearance_mm must be a finite non-negative mm value")
        values[(10, "freeIntCls")] = format(analysis_free_clearance_mm / 1000, ".15G")
    if request is not None:
        derived = geometry_updates(request)
        if request.parameters["radial_clearance_mm"] != 0 and analysis_free_clearance_mm is None:
            raise RollerDataError("parameters.radial_clearance_mm requires an explicit analysis_free_clearance_mm")
        check_geometry(base, derived, allow_mismatch=allow_reference_geometry_mismatch)
        # RoBAS's .NET Framework writer emits doubles with 15 significant
        # digits. Keep binary noise out of otherwise identical solver inputs.
        values.update({key: format(value, ".15G") for key, value in derived.items()})
    return replace(base.with_updates(values), geometry_mode=geometry_mode)

"""Read and update original RoBAS ball-bearing DATA.txt files safely.

The original DATA document is the configuration baseline. This module edits a
parsed copy and never guesses missing operating, material, lubricant, or cage
values. Lengths exposed by BearingRequest are millimetres; DATA geometry uses m.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
from typing import Mapping

from .contracts import BearingRequest, BearingType
from .robas_data import (
    COMMON_HEAD, COMMON_TAIL, DataDocument, check_geometry, profile_overrides,
    dotnet_round as _dotnet_round,
)


_RECORD_FIELDS = COMMON_HEAD + (
    ("rec 5A", ("bReDia", "pitchDia", "freeConAngDeg", "freeIntCls", "raceCurFac1", "raceCurFac2", "shoulderDia1", "shoulderDia2", "shimThickness1", "shimThickness2", "rmsAspHt1", "rmsAspHt2")),
) + COMMON_TAIL

BALL_RECORD_LABELS = tuple(label for label, _ in _RECORD_FIELDS)


class BallDataError(ValueError):
    """Invalid source DATA or a field that cannot be safely migrated."""


@dataclass(frozen=True)
class BallDataDocument(DataDocument):
    _fields = _RECORD_FIELDS
    _family = "ball"
    _bearing_code = 1
    _error = BallDataError


def _straight_pocket_reference(*, ball_d_mm: float, width_mm: float,
                               outer_sidewall_mm: float) -> dict[str, float]:
    """Reproduce the original property getter/setter chain in source order."""
    ball_d_mm = _dotnet_round(ball_d_mm, 3)       # BallRoller.BallDiameter
    pocket_d_mm = _dotnet_round(1.004 * ball_d_mm + 0.12, 1)  # PocketDiameter getter
    guide_gap_mm = 0.6 * (pocket_d_mm - ball_d_mm)
    cage_outer_mm = _dotnet_round(outer_sidewall_mm - guide_gap_mm, 2)  # BaseCage getter
    cage_inner_mm = _dotnet_round(cage_outer_mm - 0.6 * ball_d_mm, 2)
    cage_width_mm = width_mm - (0.6 * ball_d_mm + 0.5)
    if cage_width_mm - pocket_d_mm < 2.5:
        cage_width_mm = pocket_d_mm + 2.5
    cage_width_mm = _dotnet_round(cage_width_mm, 2)
    return {
        "ball_d_mm": ball_d_mm,
        "pocket_d_mm": pocket_d_mm,
        "guide_gap_mm": guide_gap_mm,
        "cage_outer_mm": cage_outer_mm,
        "cage_inner_mm": cage_inner_mm,
        "cage_width_mm": cage_width_mm,
        "pocket_clearance_mm": (pocket_d_mm - ball_d_mm) / 2,
        "guide_width_mm": 0.22 * cage_width_mm,
        "guide_position_mm": 0.5 * cage_width_mm,
    }


def geometry_updates(request: BearingRequest, *,
                    analysis_shoulder_diameters_mm: tuple[float, float] | None = None,
                    analysis_inner_race_outside_diameter_mm: float) -> dict[tuple[int, str], float | int]:
    """Map CAD geometry and the source-order RoBAS cage formula into DATA."""
    if request.bearing_type not in (BearingType.DEEP_GROOVE, BearingType.ANGULAR_CONTACT):
        raise BallDataError("Only DGB and ACB requests are supported by PR-SOLVER-02")
    p = request.parameters
    if request.bearing_type is BearingType.DEEP_GROOVE:
        groove_inner = float(p["inner_groove_radius_mm"])
        groove_outer = float(p["outer_groove_radius_mm"])
        angle = 0.0
        shoulder_inner = float(p["inner_shoulder_d_mm"])
        shoulder_outer = float(p["outer_shoulder_d_mm"])
        if analysis_shoulder_diameters_mm is not None:
            if (len(analysis_shoulder_diameters_mm) != 2 or
                    any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                        for value in analysis_shoulder_diameters_mm)):
                raise BallDataError("Analysis sidewall diameters must be two finite positive mm values")
            shoulder_inner, shoulder_outer = analysis_shoulder_diameters_mm
    else:
        groove_inner = float(p["inner_groove_radius_mm"])
        groove_outer = float(p["outer_groove_radius_mm"])
        angle = _dotnet_round(float(p["contact_angle_deg"]), 2)
        if analysis_shoulder_diameters_mm is None:
            raise BallDataError("ACB DATA has one shoulder diameter per race; supply the two RoBAS-analysis sidewall diameters explicitly")
        if (len(analysis_shoulder_diameters_mm) != 2 or
                any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                    for value in analysis_shoulder_diameters_mm)):
            raise BallDataError("Analysis sidewall diameters must be two finite positive mm values")
        shoulder_inner, shoulder_outer = analysis_shoulder_diameters_mm
    ball_d = float(p["ball_d_mm"])
    width = float(p["width_mm"])
    od = float(p["outside_d_mm"])
    bore = float(p["bore_d_mm"])
    if (type(analysis_inner_race_outside_diameter_mm) not in (int, float) or
            not math.isfinite(analysis_inner_race_outside_diameter_mm) or
            analysis_inner_race_outside_diameter_mm <= 0):
        raise BallDataError("RoBAS analysis inner-race outside diameter must be provided as finite positive mm")
    # These dimensions are supplied by the original analysis object's public
    # geometry properties, whose units are mm.
    ball_d = _dotnet_round(ball_d, 3)  # BallRoller.BallDiameter getter
    pitch_d = _dotnet_round(float(p["pitch_d_mm"]), 2)  # BallRoller.PitchDiameter getter
    width = _dotnet_round(width, 2)  # BearingWidth getter
    shoulder_outer = _dotnet_round(shoulder_outer, 2)  # Race sidewall getter
    shoulder_inner = _dotnet_round(
        shoulder_inner,
        1 if request.bearing_type is BearingType.ANGULAR_CONTACT else 2,
    )  # ACB inner-race sidewall getter uses 0.1 mm precision
    bore = _dotnet_round(bore, 2)  # InnerRace.InsideDiameter getter
    od = _dotnet_round(od, 2)  # OuterRace.OutsideDiameter getter
    pocket = _straight_pocket_reference(ball_d_mm=ball_d, width_mm=width,
                                        outer_sidewall_mm=shoulder_outer)
    cage_outer = pocket["cage_outer_mm"]
    cage_inner = pocket["cage_inner_mm"]
    cage_width = pocket["cage_width_mm"]
    cage_inner_race_d = _dotnet_round(analysis_inner_race_outside_diameter_mm, 2)
    return {
        (5, "kBrg"): 1,
        (5, "nRe"): int(p["ball_count"]),
        (7, "kPltElemInd1"): 1,
        (7, "kPltElemInd2"): int(p["ball_count"]) + 1,
        (7, "kPltElemInd3"): 0,
        (7, "kPltElemInd4"): 0,
        (7, "kPltElemInd5"): 0,
        (7, "kPltElemInd6"): 0,
        (11, "kPoctype"): 0,
        (9, "brgBore"): bore / 1000,
        (9, "brgOD"): od / 1000,
        (9, "shftID"): bore / 5000,
        (9, "hsngOD"): od * 1.14 / 1000,
        (9, "raceWidth1"): width / 1000,
        (9, "raceWidth2"): width / 1000,
        (10, "bReDia"): ball_d / 1000,
        (10, "pitchDia"): pitch_d / 1000,
        (10, "freeConAngDeg"): angle,
        (10, "raceCurFac1"): groove_outer / ball_d,
        (10, "raceCurFac2"): groove_inner / ball_d,
        (10, "shoulderDia1"): shoulder_outer / 1000,
        (10, "shoulderDia2"): shoulder_inner / 1000,
        (12, "cageDia1"): cage_outer / 1000,
        (12, "cageDia2"): cage_inner / 1000,
        (12, "cageWidth"): cage_width / 1000,
        (12, "cageCls1"): (shoulder_outer - cage_outer) / 1000,
        (12, "cageCls2"): (cage_inner - (shoulder_inner if request.bearing_type is BearingType.DEEP_GROOVE else cage_inner_race_d)) / 1000,
        # DGB assigns the public BPocCls1 setter (mm -> m); the original ACB
        # SetAnalysisValue assigns the backing field directly, retaining mm.
        (12, "bPocCls1"): (pocket["pocket_clearance_mm"] / 1000
                            if request.bearing_type is BearingType.DEEP_GROOVE
                            else pocket["pocket_clearance_mm"]),
        (13, "cageGsDia1"): cage_inner / 1000,
        (13, "cageGsWidth1"): pocket["guide_width_mm"] / 1000,
        (13, "cageGsPos1"): pocket["guide_position_mm"] / 1000,
        (13, "cageGsCls1"): (cage_inner - cage_inner_race_d) / 1000,
        (14, "cageGsDia2"): cage_inner / 1000,
        (14, "cageGsWidth2"): pocket["guide_width_mm"] / 1000,
        (14, "cageGsPos2"): pocket["guide_position_mm"] / 1000,
        (14, "cageGsCls2"): (cage_inner - cage_inner_race_d) / 1000,
    }


def update_ball_data(reference_data: str | Path, request: BearingRequest | None, *,
                     geometry_mode: str,
                     operating_updates: Mapping[tuple[int, str], str | int | float],
                     analysis_shoulder_diameters_mm: tuple[float, float] | None = None,
                     analysis_inner_race_outside_diameter_mm: float | None = None,
                     allow_reference_geometry_mismatch: bool = False,
                     analysis_parameters_mm: Mapping[str, int | float] | None = None,
                     solver_updates: Mapping[tuple[int, str], str | int | float] | None = None,
                     material_updates: Mapping[tuple[int, str], str | int | float] | None = None,
                     lubricant_updates: Mapping[tuple[int, str], str | int | float] | None = None) -> BallDataDocument:
    """Update a caller-selected original DATA profile without touching its file.

    `legacy_data` reproduces source DATA geometry without any CAD request.
    `cad_geometry` overlays confirmed CAD geometry onto a deliberately selected
    source profile for materials, lubricant and operating conditions. A mismatch
    requires explicit acknowledgement. ACB analysis sidewalls and both families'
    inner-race outside diameter must come from the analysis model.

    Operating values use DATA units. Ring speed updates also set the matching
    scan endpoints as in BaseBC, unless the caller explicitly sets an endpoint.
    """
    base = BallDataDocument.read(reference_data)
    if geometry_mode not in {"legacy_data", "cad_geometry"}:
        raise BallDataError("geometry_mode must be legacy_data or cad_geometry")
    if geometry_mode == "legacy_data" and request is not None:
        raise BallDataError("legacy_data mode must not receive a CAD request; use cad_geometry for an explicit geometry overlay")
    if geometry_mode == "cad_geometry" and request is None:
        raise BallDataError("cad_geometry mode requires a confirmed BearingRequest")
    values = profile_overrides(
        base, operating=operating_updates, solver=solver_updates,
        material=material_updates, lubricant=lubricant_updates,
    )
    analysis_parameter_fields = {
        "freeIntCls", "shimThickness1", "shimThickness2", "rmsAspHt1", "rmsAspHt2",
    }
    analysis_parameters_mm = analysis_parameters_mm or {}
    unknown_analysis_parameters = set(analysis_parameters_mm) - analysis_parameter_fields
    if unknown_analysis_parameters:
        raise BallDataError(
            f"analysis_parameters_mm accepts only {sorted(analysis_parameter_fields)}; "
            f"got {sorted(unknown_analysis_parameters)}")
    for field, millimetres in analysis_parameters_mm.items():
        if (type(millimetres) not in (int, float) or not math.isfinite(millimetres)
                or millimetres < 0):
            raise BallDataError(f"analysis_parameters_mm.{field} must be a finite non-negative mm value")
        values[(10, field)] = millimetres / 1000
    if geometry_mode == "cad_geometry":
        if analysis_inner_race_outside_diameter_mm is None:
            raise BallDataError("cad_geometry mode requires analysis_inner_race_outside_diameter_mm")
        derived = geometry_updates(
            request, analysis_shoulder_diameters_mm=analysis_shoulder_diameters_mm,
            analysis_inner_race_outside_diameter_mm=analysis_inner_race_outside_diameter_mm)
        check_geometry(base, derived, allow_mismatch=allow_reference_geometry_mismatch)
        values.update(derived)
    return replace(base.with_updates(values), geometry_mode=geometry_mode)

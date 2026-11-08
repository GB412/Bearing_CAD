"""Read and update original RoBAS ball-bearing DATA.txt files safely.

The original DATA document is the configuration baseline. This module edits a
parsed copy and never guesses missing operating, material, lubricant, or cage
values. Lengths exposed by BearingRequest are millimetres; DATA geometry uses m.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import math
from pathlib import Path
from typing import Mapping

from .contracts import BearingRequest, BearingType


_RECORD_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rec 1", ("Mode", "kDCR", "kDOF", "klcOpt", "kFnOpt", "kPrtOpt", "kPrtFreq", "kPltFreq", "kAGraf", "kLifeFreq", "kTherm", "maxStps", "nStps", "intMet")),
    ("rec 2.1", ("stpInit", "stpMin", "stpMax", "fTime", "Tol", "qFac")),
    ("rec 2.2", ("kFD11", "kFD21", "kFD31", "kFD12", "kFD22", "kFD32", "kMD11", "kMD21", "kMD31", "kMD12", "kMD22", "kMD32")),
    ("rec 2.3", ("finName", "pltNames1", "pltNames2", "pltNames3", "pltNames4", "pltNames5", "pltNames6", "pltNames7", "pltNames8", "pltNames9")),
    ("rec 3.1", ("runId",)),
    ("rec 3.2", ("kUnit", "kBrg", "nRe", "nCseg", "kRaceFlex", "kReGeoImp", "kRaceGeoImp1", "kRaceGeoImp2", "kFlngInd11", "kFlngInd12", "kFlngInd21", "kFlngInd22")),
    ("rec 3.3", ("kStaticConstraint1", "kStaticConstraint2", "kStaticConstraint3", "kStaticConstraint4", "kStaticConstraint5", "kAngVel", "kStif", "kChrn", "kReMat", "kRaceMat1", "kRaceMat2", "kHsngMat", "kShftMat", "kLifeCons")),
    ("rec 3.4", ("kRotLoad", "kRotFrame", "kReIP", "kRaceIP1", "kRaceIP2", "kNumPltElem", "kPltElemInd1", "kPltElemInd2", "kPltElemInd3", "kPltElemInd4", "kPltElemInd5", "kPltElemInd6")),
    ("rec 3.5", ("kCoolant", "kBaseTemp", "kHTC", "kGeoMod", "kMatPropMod")),
    ("rec 4", ("brgBore", "brgOD", "shftID", "hsngOD", "raceWidth1", "raceWidth2")),
    ("rec 5A", ("bReDia", "pitchDia", "freeConAngDeg", "freeIntCls", "raceCurFac1", "raceCurFac2", "shoulderDia1", "shoulderDia2", "shimThickness1", "shimThickness2", "rmsAspHt1", "rmsAspHt2")),
    ("rec 7.0", ("kPoctype", "kCagePocImp", "kCageGsImp", "kRaceGsImp", "kPocHydro", "kGsHydro", "kCageMat", "kCageIP", "nGL", "iCageGuide1", "iCageGuide2", "iCageGuide3", "iCageGuide4")),
    ("rec 7.1", ("cageDia1", "cageDia2", "cageWidth", "cageCls1", "cageCls2", "bPocCls1", "bPocCls2", "cageAngCut", "cageConeAng")),
    ("rec 7.2.x", ("cageGsDia1", "cageGsWidth1", "cageGsPos1", "cageGsCls1")),
    ("rec 7.2.x", ("cageGsDia2", "cageGsWidth2", "cageGsPos2", "cageGsCls2")),
    ("rec 8.1", ("density", "elasticModules", "poissonRatio", "thermalExpansion", "specificHeat", "conductivity", "strainLimit", "hardness", "wearCoeff", "misis")),
    ("rec 8.2.1", ("density", "elasticModules", "poissonRatio", "thermalExpansion", "specificHeat", "conductivity", "strainLimit", "hardness", "wearCoeff", "misis")),
    ("rec 8.2.2", ("density", "elasticModules", "poissonRatio", "thermalExpansion", "specificHeat", "conductivity", "strainLimit", "hardness", "wearCoeff", "misis")),
    ("rec 8.3", ("density", "elasticModules", "poissonRatio", "thermalExpansion", "conductivity")),
    ("rec 8.4", ("density", "elasticModules", "poissonRatio", "thermalExpansion", "conductivity")),
    ("rec 8.5", ("density", "elasticModules", "poissonRatio", "thermalExpansion", "specificHeat", "conductivity", "strainLimit", "hardness", "wearCoeff", "misis")),
    ("rec 8.6.0", ("sProb", "brgWbDis")),
    ("rec 8.6.1", ("fcO1", "fcLP1", "shExLP1", "depExLP1", "fcGZ1", "shExGZ1", "fcIH1", "shExIH1", "depExIH1", "wbDis1")),
    ("rec 8.6.2", ("fcO1", "fcLP1", "shExLP1", "depExLP1", "fcGZ1", "shExGZ1", "fcIH1", "shExIH1", "depExIH1", "wbDis1")),
    ("rec 8.6.3", ("fcO1", "fcLP1", "shExLP1", "depExLP1", "fcGZ1", "shExGZ1", "fcIH1", "shExIH1", "depExIH1", "wbDis1")),
    ("rec 8.6.4", ("rmsAspSlp1", "shearLmt1", "aspTrac1", "facMat1", "facCont1", "facProc1", "facMatLF1", "facProcLF1", "hardnessLF1")),
    ("rec 8.6.5", ("rmsAspSlp1", "shearLmt1", "aspTrac1", "facMat1", "facCont1", "facProc1", "facMatLF1", "facProcLF1", "hardnessLF1")),
    ("rec 8.6.6", ("facMatRe", "facContRe", "facProcRe", "facMatLFre", "facProcLFre", "hardnessLFre")),
    ("rec 9.0", ("roomTemp", "raceFit1", "raceFit2", "angVelOrt", "resStress1", "resStress2", "facStrLimit")),
    ("rec 9.1.1", ("appLoadX", "appLoadY", "appLoadZ", "appDispX", "appDispY", "appDispZ")),
    ("rec 9.1.2", ("appMomY", "appMomZ", "appMis11", "appMis21", "appMis12", "appMis22", "rpm1", "rpm2")),
    ("rec 9.1.3", ("hsngTemp", "shftTemp", "raceTemp1", "raceTemp2", "reTemp", "cageTemp")),
    ("rec 9.2", ("pctDisp", "rpmRange11", "rpmRange21", "rpmRange12", "rpmRange22")),
    ("rec 9.5", ("pocLubFilm", "wvRatio", "avRatio", "cageGcPosX", "cageGcPosY", "cageGcPosZ", "cageAngPosX", "cageAngPosY", "cageAngPosZ")),
    ("rec 9.6", ("baseTemp", "cFlowRate", "cPres", "reHTC", "cageHTC", "aveTime", "skipTime")),
    ("rec 9.7", ("xRo", "xMu", "xCp", "xK")),
    ("rec 10.0", ("kTrac", "kTracType", "kCPTrac", "kCPTracType", "kCRTrac", "kCRTracType", "kRFTrac", "kRFTracType", "kRRTrac", "kRRTracType", "iTherm")),
    ("rec 10.1C", ("reRaceTC1", "reRaceTC2", "reRaceTC3", "reRaceTC4")),
    ("rec 10.3", ("reRaceFilm", "strParam")),
    ("rec 10.5.1B", ("reCageTC1", "reCageTC2", "reCageTC3", "reCageTC4", "reCageFilm")),
    ("rec 10.5.2B", ("cageRaceTC1", "cageRaceTC2", "cageRaceTC3", "cageRaceTC4", "cageRaceFilm")),
    ("rec 10.6", ("pocVis", "gsVis")),
    ("rec 11", ("gravityVecX", "gravityVecY", "gravityVecZ")),
)

BALL_RECORD_LABELS = tuple(label for label, _ in _RECORD_FIELDS)
_TEXT_RECORDS = {3, 4}
class BallDataError(ValueError):
    """Invalid source DATA or a field that cannot be safely migrated."""


@dataclass(frozen=True)
class BallDataDocument:
    rows: tuple[tuple[str, ...], ...]

    @classmethod
    def parse(cls, text: str) -> "BallDataDocument":
        if "\x00" in text:
            raise BallDataError("DATA.txt contains NUL bytes")
        parsed = list(csv.reader(io.StringIO(text, newline=""), skipinitialspace=True))
        expected_count = len(_RECORD_FIELDS)
        if len(parsed) != expected_count:
            raise BallDataError(f"Expected {expected_count} ball records, got {len(parsed)}")
        rows: list[tuple[str, ...]] = []
        for index, ((label, fields), row) in enumerate(zip(_RECORD_FIELDS, parsed), 1):
            if not row or row[0].strip().strip("'").strip('"') != label:
                actual = row[0] if row else "<empty>"
                raise BallDataError(f"Record {index} must be '{label}', got {actual!r}")
            if len(row) != len(fields) + 1:
                raise BallDataError(f"Record {index} '{label}' expects {len(fields)} values, got {len(row)-1}")
            for value in row[1:]:
                normalized = value.strip().strip("'").strip('"')
                if index - 1 in _TEXT_RECORDS:
                    if not normalized:
                        raise BallDataError(f"Record {index} '{label}' contains empty text")
                else:
                    try:
                        number = float(value)
                    except ValueError:
                        raise BallDataError(f"Record {index} '{label}' contains a non-numeric value") from None
                    if not math.isfinite(number):
                        raise BallDataError(f"Record {index} '{label}' contains a non-finite value")
            rows.append(tuple(cell.strip() for cell in row))
        if rows[0][1] != "-1":
            raise BallDataError("Ball DATA must use Mode=-1 (quasi-static)")
        return cls(tuple(rows))

    @classmethod
    def read(cls, path: str | Path) -> "BallDataDocument":
        return cls.parse(Path(path).read_text(encoding="utf-8-sig"))

    def render(self) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        for row in self.rows:
            writer.writerow(row)
        return buffer.getvalue()

    def value(self, record_index: int, field: str) -> str:
        """Return a field value using zero-based record indices."""
        label, fields = _RECORD_FIELDS[record_index]
        try:
            column = fields.index(field) + 1
        except ValueError:
            raise BallDataError(f"Unknown field {field!r} in {label}") from None
        return self.rows[record_index][column]

    def with_updates(self, updates: Mapping[tuple[int, str], str | int | float]) -> "BallDataDocument":
        rows = [list(row) for row in self.rows]
        for (record_index, field), raw_value in updates.items():
            if not 0 <= record_index < len(_RECORD_FIELDS):
                raise BallDataError(f"Unknown record index: {record_index}")
            label, fields = _RECORD_FIELDS[record_index]
            if field not in fields:
                raise BallDataError(f"Unknown field {field!r} in {label}")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
                raise BallDataError(f"Invalid value type for {label}.{field}")
            if isinstance(raw_value, str):
                if not raw_value or any(c in raw_value for c in ",\r\n\x00"):
                    raise BallDataError(f"Invalid text value for {label}.{field}")
                if record_index not in _TEXT_RECORDS:
                    try:
                        number = float(raw_value)
                    except ValueError:
                        raise BallDataError(f"Expected numeric value for {label}.{field}") from None
                    if not math.isfinite(number):
                        raise BallDataError(f"Non-finite value for {label}.{field}")
            elif isinstance(raw_value, float) and not math.isfinite(raw_value):
                raise BallDataError(f"Non-finite value for {label}.{field}")
            rows[record_index][fields.index(field) + 1] = str(raw_value)
        return BallDataDocument.parse("\n".join(",".join(row) for row in rows))


def geometry_updates(request: BearingRequest, *,
                    analysis_shoulder_diameters_mm: tuple[float, float] | None = None) -> dict[tuple[int, str], float | int]:
    """Map confirmed CAD geometry and audited RoBAS cage equations into DATA."""
    if request.bearing_type not in (BearingType.DEEP_GROOVE, BearingType.ANGULAR_CONTACT):
        raise BallDataError("Only DGB and ACB requests are supported by PR-SOLVER-02")
    p = request.parameters
    if request.bearing_type is BearingType.DEEP_GROOVE:
        groove_inner = float(p["inner_groove_radius_mm"])
        groove_outer = float(p["outer_groove_radius_mm"])
        angle = 0.0
        shoulder_inner = float(p["inner_shoulder_d_mm"])
        shoulder_outer = float(p["outer_shoulder_d_mm"])
    else:
        groove_inner = float(p["inner_groove_radius_mm"])
        groove_outer = float(p["outer_groove_radius_mm"])
        angle = float(p["contact_angle_deg"])
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
    # The legacy constructor receives millimetres through public getters. Its
    # constants (.12, .5, 2.5) are therefore millimetres as well.
    pocket_d = 1.004 * ball_d + 0.12
    guide_gap = 0.6 * (pocket_d - ball_d)
    cage_outer = shoulder_outer - guide_gap
    cage_inner = cage_outer - 0.6 * ball_d
    cage_width = width - (0.6 * ball_d + 0.5)
    if cage_width - pocket_d < 2.5:
        cage_width = pocket_d + 2.5
    cage_guide_width = 0.22 * cage_width
    return {
        (5, "nRe"): int(p["ball_count"]),
        (7, "kPltElemInd1"): 1,
        (7, "kPltElemInd2"): int(p["ball_count"]) + 1,
        (9, "brgBore"): bore / 1000,
        (9, "brgOD"): od / 1000,
        (9, "shftID"): bore / 5000,
        (9, "hsngOD"): od * 1.14 / 1000,
        (9, "raceWidth1"): width / 1000,
        (9, "raceWidth2"): width / 1000,
        (10, "bReDia"): ball_d / 1000,
        (10, "pitchDia"): float(p["pitch_d_mm"]) / 1000,
        (10, "freeConAngDeg"): angle,
        (10, "raceCurFac1"): groove_outer / ball_d,
        (10, "raceCurFac2"): groove_inner / ball_d,
        (10, "shoulderDia1"): shoulder_outer / 1000,
        (10, "shoulderDia2"): shoulder_inner / 1000,
        (12, "cageDia1"): cage_outer / 1000,
        (12, "cageDia2"): cage_inner / 1000,
        (12, "cageWidth"): cage_width / 1000,
        (12, "cageCls1"): (shoulder_outer - cage_outer) / 1000,
        (12, "cageCls2"): (cage_inner - shoulder_inner) / 1000,
        (12, "bPocCls1"): ((pocket_d - ball_d) / 2) / 1000,
        (12, "bPocCls2"): 0,
        (12, "cageAngCut"): 0,
        (12, "cageConeAng"): 0,
        (13, "cageGsDia1"): cage_inner / 1000,
        (13, "cageGsWidth1"): cage_guide_width / 1000,
        (13, "cageGsPos1"): (0.5 * cage_width) / 1000,
        (13, "cageGsCls1"): (cage_inner - shoulder_inner) / 1000,
        (14, "cageGsDia2"): cage_inner / 1000,
        (14, "cageGsWidth2"): cage_guide_width / 1000,
        (14, "cageGsPos2"): (0.5 * cage_width) / 1000,
        (14, "cageGsCls2"): (cage_inner - shoulder_inner) / 1000,
    }


def update_ball_data(reference_data: str | Path, request: BearingRequest, *,
                     operating_updates: Mapping[tuple[int, str], str | int | float],
                     analysis_shoulder_diameters_mm: tuple[float, float] | None = None,
                     cage_updates: Mapping[tuple[int, str], str | int | float] | None = None,
                     solver_updates: Mapping[tuple[int, str], str | int | float] | None = None,
                     material_updates: Mapping[tuple[int, str], str | int | float] | None = None,
                     lubricant_updates: Mapping[tuple[int, str], str | int | float] | None = None) -> BallDataDocument:
    """Update a caller-selected original DATA profile without touching its file.

    `reference_data` must be an original RoBAS-generated ball DATA.txt. Cage
    dimensions are regenerated from the source `StraightPocketCage` equations.
    ACB callers supply the two analysis-sidewall diameters because the CAD
    contract exposes two shoulders per race while the DATA record exposes one.
    Operating values are mandatory as an explicit mapping; use an original
    DATA profile only after deliberately choosing to preserve its conditions.
    """
    base = BallDataDocument.read(reference_data)
    def check_group(name: str, updates: Mapping[tuple[int, str], str | int | float],
                    allowed: set[tuple[int, str]]) -> None:
        invalid = sorted(set(updates) - allowed)
        if invalid:
            raise BallDataError(f"{name} updates target fields outside their mapped scope: {invalid}")

    check_group("operating", operating_updates,
                {(index, field) for index in (*range(28, 35), 42)
                 for field in _RECORD_FIELDS[index][1]})
    check_group("solver", solver_updates or {}, {(0, "nStps")})
    check_group("material", material_updates or {},
                {(index, field) for index in range(15, 28)
                 for field in _RECORD_FIELDS[index][1]})
    check_group("lubricant", lubricant_updates or {},
                {(index, field) for index in range(35, 42)
                 for field in _RECORD_FIELDS[index][1]})
    check_group("cage", cage_updates or {},
                {(index, field) for index in range(11, 15)
                 for field in _RECORD_FIELDS[index][1]})
    values = dict(operating_updates)
    values.update(geometry_updates(request,
                                   analysis_shoulder_diameters_mm=analysis_shoulder_diameters_mm))
    if cage_updates:
        values.update(cage_updates)
    for updates in (solver_updates or {}, material_updates or {}, lubricant_updates or {}):
        values.update(updates)
    return base.with_updates(values)

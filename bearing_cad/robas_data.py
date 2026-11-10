"""Record layout, validation and lossless numeric tokens shared by RoBAS inputs."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
from typing import ClassVar, Mapping, Self


RecordFields = tuple[tuple[str, tuple[str, ...]], ...]
Field = tuple[int, str]
DataValue = str | int | float


COMMON_HEAD: RecordFields = (
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
)

COMMON_TAIL: RecordFields = (
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

_TEXT_RECORDS = {3, 4}


@dataclass(frozen=True)
class DataDocument:
    """Shared row codec for the original quasi-static DATA layouts."""

    _fields: ClassVar[RecordFields]
    _family: ClassVar[str]
    _bearing_code: ClassVar[int]
    _error: ClassVar[type[ValueError]]

    rows: tuple[tuple[str, ...], ...]
    geometry_mode: str = "unclassified"
    reference_data_sha256: str | None = None

    @classmethod
    def parse(cls, text: str) -> Self:
        if "\x00" in text:
            raise cls._error("DATA.txt contains NUL bytes")
        parsed = list(csv.reader(io.StringIO(text, newline=""), skipinitialspace=True))
        expected_count = len(cls._fields)
        if len(parsed) != expected_count:
            raise cls._error(f"Expected {expected_count} {cls._family} records, got {len(parsed)}")
        rows: list[tuple[str, ...]] = []
        for index, ((label, fields), row) in enumerate(zip(cls._fields, parsed), 1):
            if not row or row[0].strip().strip("'").strip('"') != label:
                actual = row[0] if row else "<empty>"
                raise cls._error(f"Record {index} must be '{label}', got {actual!r}")
            if len(row) != len(fields) + 1:
                raise cls._error(f"Record {index} '{label}' expects {len(fields)} values, got {len(row)-1}")
            for field, value in zip(fields, row[1:]):
                normalized = value.strip().strip("'").strip('"')
                if index - 1 in _TEXT_RECORDS:
                    if not normalized:
                        raise cls._error(f"Record {index} '{label}'.{field} contains empty text")
                else:
                    try:
                        number = float(value)
                    except ValueError:
                        raise cls._error(f"Record {index} '{label}'.{field} contains a non-numeric value") from None
                    if not math.isfinite(number):
                        raise cls._error(f"Record {index} '{label}'.{field} contains a non-finite value")
            rows.append(tuple(cell.strip() for cell in row))
        if rows[0][1] != "-1":
            raise cls._error(f"{cls._family} DATA must use Mode=-1 (quasi-static)")
        if float(rows[5][1]) != 1 or float(rows[5][2]) != cls._bearing_code:
            raise cls._error(f"{cls._family} DATA requires rec 3.2 kUnit=1 and kBrg={cls._bearing_code}")
        return cls(tuple(rows))

    @classmethod
    def read(cls, path: str | Path) -> Self:
        payload = Path(path).read_bytes()
        parsed = cls.parse(payload.decode("utf-8-sig"))
        return cls(parsed.rows, "legacy_data", hashlib.sha256(payload).hexdigest())

    def render(self) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
        for row in self.rows:
            writer.writerow(row)
        return buffer.getvalue()

    def value(self, record_index: int, field: str) -> str:
        """Return a field value using zero-based record indices."""
        label, fields = self._fields[record_index]
        try:
            column = fields.index(field) + 1
        except ValueError:
            raise self._error(f"Unknown field {field!r} in {label}") from None
        return self.rows[record_index][column]

    def with_updates(self, updates: Mapping[tuple[int, str], str | int | float]) -> Self:
        rows = [list(row) for row in self.rows]
        for (record_index, field), raw_value in updates.items():
            if not 0 <= record_index < len(self._fields):
                raise self._error(f"Unknown record index: {record_index}")
            label, fields = self._fields[record_index]
            if field not in fields:
                raise self._error(f"Unknown field {field!r} in {label}")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
                raise self._error(f"Invalid value type for {label}.{field}")
            if isinstance(raw_value, str):
                if not raw_value or any(c in raw_value for c in ",\r\n\x00"):
                    raise self._error(f"Invalid text value for {label}.{field}")
                if record_index not in _TEXT_RECORDS:
                    try:
                        number = float(raw_value)
                    except ValueError:
                        raise self._error(f"Expected numeric value for {label}.{field}") from None
                    if not math.isfinite(number):
                        raise self._error(f"Non-finite value for {label}.{field}")
            elif isinstance(raw_value, float) and not math.isfinite(raw_value):
                raise self._error(f"Non-finite value for {label}.{field}")
            rows[record_index][fields.index(field) + 1] = str(raw_value)
        parsed = self.parse("\n".join(",".join(row) for row in rows))
        return type(self)(parsed.rows, self.geometry_mode, self.reference_data_sha256)


def dotnet_round(value: float, digits: int) -> float:
    """Match Math.Round(double, digits)' scaled ties-to-even behavior."""
    scale = 10 ** digits
    scaled = value * scale
    if not math.isfinite(scaled) or abs(scaled) >= 1e16:
        return value
    return round(scaled) / scale


def profile_overrides(
    doc: DataDocument, *,
    operating: Mapping[Field, DataValue],
    solver: Mapping[Field, DataValue] | None,
    material: Mapping[Field, DataValue] | None,
    lubricant: Mapping[Field, DataValue] | None,
) -> dict[Field, DataValue]:
    """Validate override ownership and preserve the BaseBC speed setter links."""
    fields = doc._fields
    indices = {label: index for index, (label, _) in enumerate(fields)}
    groups = (
        ("operating", operating, (*range(indices["rec 9.0"], indices["rec 9.7"]), indices["rec 11"])),
        ("material", material or {}, range(indices["rec 8.1"], indices["rec 9.0"])),
        ("lubricant", lubricant or {}, range(indices["rec 9.7"], indices["rec 11"])),
    )
    updates: dict[Field, DataValue] = {}
    for group, values, records in groups:
        allowed = {(record, field) for record in records for field in fields[record][1]}
        invalid = sorted(set(values) - allowed)
        if invalid:
            raise doc._error(f"{group} updates target fields outside their mapped scope: {invalid}")
        updates.update(values)
    invalid = sorted(set(solver or {}) - {(0, "nStps")})
    if invalid:
        raise doc._error(f"solver updates target fields outside their mapped scope: {invalid}")
    updates.update(solver or {})

    speed_record, scan_record = indices["rec 9.1.2"], indices["rec 9.2"]
    for speed_field, endpoint in (("rpm1", "rpmRange21"), ("rpm2", "rpmRange12")):
        speed = speed_record, speed_field
        if speed in updates:
            updates.setdefault((scan_record, endpoint), updates[speed])
    return updates


def check_geometry(
    doc: DataDocument, derived: Mapping[Field, float | int], *, allow_mismatch: bool,
) -> None:
    if allow_mismatch:
        return
    mismatches = [
        f"{doc._fields[record][0]}.{field}"
        for (record, field), value in derived.items()
        if not math.isclose(float(doc.value(record, field)), value, rel_tol=1e-9, abs_tol=1e-12)
    ]
    if mismatches:
        examples = ", ".join(mismatches[:4])
        raise doc._error(
            f"reference DATA geometry differs from CAD geometry at {examples}; "
            "explicitly set allow_reference_geometry_mismatch=True to overlay CAD geometry"
        )

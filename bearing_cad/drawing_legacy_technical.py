"""RoBAS SetCADTextValue: original four technical-condition SQLite table mappings.

Source: DataControl.GetGeneralMapInnerRaceTechnicalCondition,
GetGeneralMapOuterRaceTechnicalCondition, GetInnerRaceTechnicalCondition,
GetOuterRaceTechnicalCondition. This is drawing data, not geometry redesign.
"""
from __future__ import annotations

import math
from pathlib import Path
import sqlite3

from .drawing_variables import DB_BY_TYPE, DrawingDataError

_GRADES = {"P0": "B", "P6": "C", "P5": "D", "P4": "E", "P2": "G"}
_SERIES = set("01234789")


def _choose(series: str, mapping: dict[str, int], default: int | None = None):
    for allowed, idx in mapping.items():
        if series in allowed:
            return idx
    return default


def _entry(key: str, row: tuple, index: int | None, source: str):
    # Only *_Upper is explicitly 0 in the original. Unselected series
    # branches remain DBNull (empty), rather than being silently set to 0.
    value = ("0" if key in ("d_Upper", "Dd_Upper") else None) if index is None else row[index]
    return {"name": key, "value": "" if value is None else str(value),
            "source": source}


def _general_inner(row: tuple, series: str, table: str):
    pairs = [
        ("d_Upper", None), ("d_Lower", 1),
        ("ZVdp", _choose(series, {"9": 2, "01": 3, "234": 4})),
        ("ZVdmp", 5), ("Zkia", 6), ("ZVBs", 11), ("ZSd", 7), ("Zsia", 8),
    ]
    return [_entry(k, row, i, table) for k, i in pairs]


def _general_outer(row: tuple, series: str, table: str):
    pairs = [
        ("Dd_Upper", None), ("Dd_Lower", 1),
        ("ZVDdp", _choose(series, {"89": 2, "01": 3, "234": 4}, 5)),
        ("ZVDdmp", 6), ("Zkea", 7), ("Zsea", 9), ("ZVCs", 10), ("ZSDd", 8),
    ]
    return [_entry(k, row, i, table) for k, i in pairs]


def _inner(row: tuple, series: str, table: str, roller: bool):
    pairs = [
        ("d_Upper", None), ("d_Lower", 1),
        ("Vdp", _choose(series, {"9": 2, "01": 3, "234": 4})),
        ("Vdmp", 5),
    ]
    if roller:
        pairs += [
            ("VBs", 7), ("Sd", 8), ("Ki", 9), ("VB2s", 10),
            ("Li", 11), ("dimp_dimpa", 12), ("Sdi", 13), ("Vdip", 14),
        ]
    else:
        pairs += [
            ("Si", 6), ("Sd", 7), ("Ki", 8), ("VBs", 10),
            ("Cir_d", 11 if series in "7891" else 12), ("Cur_d", 13),
        ]
    return [_entry(k, row, i, table) for k, i in pairs]


def _outer(row: tuple, series: str, table: str, roller: bool):
    pairs = [
        ("Dd_Upper", None), ("Dd_Lower", 1),
        ("VDdp", _choose(series, {"9": 2, "01": 3, "234": 4})),
        ("VDdmp", 5),
    ]
    if roller:
        pairs += [("VCs", 6), ("SDd", 7), ("Ke", 8), ("VDep", 11)]
    else:
        pairs += [
            ("Se", 6), ("SDd", 7), ("Ke", 8), ("VCs", 9),
            ("Cir_Dd", 10 if series in "7891" else 11), ("Cur_Dd", 12),
        ]
    entries = [_entry(k, row, i, table) for k, i in pairs]
    if roller:
        entries.extend({"name": key, "value": "---", "source": table}
                       for key in ("Le", "Sde"))
    return entries


def _dimension(value: object, label: str):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise DrawingDataError(f"{label} must be finite positive millimetres")
    return float(value)


def technical_condition_rows(*, resources: Path, bearing_type: str,
                             bore_d_mm: float, outside_d_mm: float,
                             accuracy_class: str, diameter_series: str) -> list[dict]:
    """Return condition values in the original C# overwriting order.

    Uses the C# first-matching query WHERE d >= ? LIMIT 1, without
    introducing a different sort order, formula or geometric calculation.
    """
    if bearing_type not in DB_BY_TYPE:
        raise DrawingDataError("Unknown bearing type")
    if accuracy_class not in _GRADES or diameter_series not in _SERIES:
        raise DrawingDataError("Unknown RoBAS accuracy class or diameter series")
    bore = _dimension(bore_d_mm, "bore_d_mm")
    outside = _dimension(outside_d_mm, "outside_d_mm")
    if bore >= outside:
        raise DrawingDataError("Outside diameter must exceed bore")
    path = Path(resources) / "Data" / DB_BY_TYPE[bearing_type]
    if not path.is_file() or path.is_symlink():
        raise DrawingDataError(f"RoBAS source database unavailable: {path.name}")
    grade = _GRADES[accuracy_class] + "级"
    tasks = (
        ("总图外圈技术条件", outside, _general_outer),
        ("总图内圈技术条件", bore, _general_inner),
        ("外圈技术条件", outside, _outer),
        ("内圈技术条件", bore, _inner),
    )
    result = []
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            for suffix, diameter, converter in tasks:
                table = grade + suffix
                row = db.execute(
                    f'SELECT * FROM "{table}" WHERE d >= ? LIMIT 1',
                    (diameter,)
                ).fetchone()
                if row is None:
                    continue  # Original C# DataTable stays empty.
                if converter in (_inner, _outer):
                    entries = converter(
                        row, diameter_series, table,
                        bearing_type == "rolling.cylindrical_roller")
                else:
                    entries = converter(row, diameter_series, table)
                result.extend(entries)
    except (sqlite3.Error, IndexError) as exc:
        raise DrawingDataError("RoBAS technical table query/schema mismatch") from exc
    return result


def apply_technical_conditions(report: dict, technical_rows: list[dict]) -> dict:
    """Overlay tables in original C# column-match order, preserving duplicates."""
    if report.get("schema_version") != "robas.drawing.variables.v1":
        raise DrawingDataError("Invalid RoBAS drawing-variable report")
    values = [dict(item) for item in report["variables"]]
    for item in technical_rows:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise DrawingDataError("Invalid technical-condition mapping")
        for row in values:
            if row["name"] == item["name"]:
                row["value"] = item["value"]
                row["source"] = "robas_technical:" + item["source"]
    result = dict(report)
    result["variables"] = values
    result["technical_rows_applied"] = len(technical_rows)
    result["unresolved_names"] = sorted({v["name"] for v in values if not v["value"]})
    result["unresolved_count"] = len(result["unresolved_names"])
    result["unresolved_ratings"] = [
        key for key in ("Cr", "Cor") if key in result["unresolved_names"]]
    result["status"] = ("DRAFT_INCOMPLETE" if result["unresolved_count"]
                        else "VARIABLES_POPULATED_UNREVIEWED")
    return result

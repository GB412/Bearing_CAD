"""RoBAS GetChamferSize and SetCADTextValue corner-radius text mapping.

Original DWG text only. No parametric geometry, new shape or tolerance standard.
"""
from __future__ import annotations

import math
from pathlib import Path
import sqlite3

from .drawing_variables import DB_BY_TYPE, DrawingDataError

_SPECS = (("rs_r", 2), ("rs_a", 5), ("r3", 8), ("r8", 11))
_SECONDARY = (("r1s_r", 2), ("r1s_a", 5))
_EXTRA_ROLLER = (("r2", 14), ("r5", 17))


def _text(value):
    return "" if value is None else str(value)


def _chamfer_source(resources: Path, bearing_type: str, rmin: float):
    if bearing_type not in DB_BY_TYPE:
        raise DrawingDataError("Unsupported bearing type")
    if type(rmin) not in (int, float) or not math.isfinite(rmin) or rmin <= 0:
        raise DrawingDataError("Chamfer radius must be finite positive mm")
    path = Path(resources) / "Data" / DB_BY_TYPE[bearing_type]
    if not path.is_file() or path.is_symlink():
        raise DrawingDataError(f"RoBAS chamfer database missing: {path.name}")
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            # RoBAS DataControl.GetChamferSize selects the FIRST matching rsmin
            # row; its two branches both accept that first row. Do not invent
            # another diameter selection strategy.
            row = db.execute(
                'SELECT * FROM "倒角尺寸表" WHERE rsmin = ? LIMIT 1',
                (float(rmin),)).fetchone()
    except sqlite3.Error as error:
        raise DrawingDataError("RoBAS chamfer table lookup failed") from error
    # DataControl.GetChamferSize creates a new DataTable and copies SQL
    # columns 2..21 into DataRow columns 0..19; do not use raw SQL offsets.
    return [_text(value) for value in row[2:22]] if row else None


def _raw(chamfer, pairs):
    result = {}
    for base, index in pairs:
        if index+2 >= len(chamfer):
            raise DrawingDataError("Unexpected RoBAS chamfer table schema")
        result[base] = chamfer[index]
        result[base+"_Upper"] = chamfer[index+1]
        result[base+"_Lower"] = chamfer[index+2]
    return result


def apply_robas_chamfer(*, report: dict, resources: Path, bearing_type: str,
                        chamfer1_mm: float, chamfer2_mm: float | None = None) -> dict:
    """Copy original rowwise formatting (including zero-placeholder variations).

    Deep-groove and angular-contact ball cages use the +/- compacting logic,
    while cylindrical roller drawings use direct value/upper/lower text.
    """
    if report.get("schema_version") != "robas.drawing.variables.v1":
        raise DrawingDataError("Invalid drawing-variable report")
    first = _chamfer_source(resources, bearing_type, chamfer1_mm)
    second = None
    if bearing_type != "rolling.deep_groove_ball":
        if chamfer2_mm is None:
            raise DrawingDataError("This RoBAS bearing type requires chamfer2_mm")
        second = _chamfer_source(resources, bearing_type, chamfer2_mm)
    values = [dict(row) for row in report["variables"]]
    if first is None or (bearing_type != "rolling.deep_groove_ball" and second is None):
        # C# catches missing Rows[0] per variable and preserves its previous
        # DataTable entries. We record the failure rather than fabricate data.
        result = dict(report)
        result["chamfer_lookup_warning"] = "NO_RS_MIN_MATCH_IN_ORIGINAL_DATABASE"
        return result
    is_roller = bearing_type == "rolling.cylindrical_roller"
    parts = _SPECS + (_EXTRA_ROLLER if is_roller else ())
    if is_roller:
        mapping = _raw(first, parts)
        mapping.update(_raw(second, _SECONDARY))
    else:
        # Mutate the original data-row deviations in the same variable-table
        # order as the original SetCADTextValue if a tolerance becomes '±'.
        sources = {}
        for prefix, index in _SPECS:
            sources[prefix] = (first, index)
        if second is not None:
            for prefix, index in _SECONDARY:
                sources[prefix] = (second, index)
        mapping = {}
    for target in values:
        key = target["name"]
        replacement = None
        if is_roller:
            replacement = mapping.get(key)
        else:
            for prefix, (source, idx) in sources.items():
                if key == prefix:
                    upper, lower = source[idx+1], source[idx+2]
                    # The original checks Substring(1) equality; only avoid
                    # crashing when the old resource contains empty deviations.
                    symmetric = (len(upper) > 1 and len(lower) > 1
                                 and upper[1:] == lower[1:])
                    if symmetric:
                        replacement = source[idx] + "±" + upper[1:]
                        source[idx+1] = ""
                        source[idx+2] = ""
                    else:
                        replacement = source[idx]
                    break
                if key == prefix + "_Upper":
                    replacement = source[idx+1] if source[idx+1] != "0" else None
                    break
                if key == prefix + "_Lower":
                    replacement = source[idx+2] if source[idx+2] != "0" else None
                    break
                if key == prefix + "_Upper1":
                    replacement = "0" if source[idx+1] == "0" else None
                    break
                if key == prefix + "_Lower1":
                    replacement = "0" if source[idx+2] == "0" else None
                    break
        if replacement is not None:
            target["value"] = replacement
            target["source"] = "robas_chamfer"
    result = dict(report)
    result["variables"] = values
    result["chamfer_lookup_warning"] = None
    result["unresolved_names"] = sorted({row["name"] for row in values if not row["value"]})
    result["unresolved_count"] = len(result["unresolved_names"])
    result["unresolved_ratings"] = [
        name for name in ("Cr", "Cor") if name in result["unresolved_names"]]
    result["status"] = ("DRAFT_INCOMPLETE" if result["unresolved_count"]
                        else "VARIABLES_POPULATED_UNREVIEWED")
    return result

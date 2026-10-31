"""Read-only RoBAS drawing variables; preserves SQLite row order and duplicate keys.

Data preparation is deliberately separate from geometry generation and
CADImport. Values that require RoBAS engineering/standard calculations remain
unresolved; this module cannot authorize manufacturing drawings.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import math
import sqlite3

DB_BY_TYPE = {
    "rolling.deep_groove_ball": "DGBData.db",
    "rolling.angular_contact_ball": "ACBData.db",
    "rolling.cylindrical_roller": "CRBData.db",
}
_COMMON = {"Dd": "outside_d_mm", "d": "bore_d_mm", "B_": "width_mm"}
_BALL = {"Dw": "ball_d_mm", "Z": "ball_count"}
_ROLLER = {"Dw": "roller_d_mm", "Lw": "roller_length_mm", "Z": "roller_count"}


class DrawingDataError(ValueError):
    pass


@dataclass(frozen=True)
class VariableRow:
    name: str
    value: str | None
    row_index: int
    source: str


def _text(value: object) -> str:
    if type(value) is int:
        return str(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise DrawingDataError("Non-finite geometry dimension")
        return format(value, ".15g")
    if isinstance(value, str) and value and not any(char in value for char in ("\r", "\n", "\x00")):
        return value
    raise DrawingDataError("Unsafe or unsupported drawing variable value")


def read_variable_rows(resources: Path, bearing_type: str) -> tuple[list[VariableRow], str]:
    """Read RoBAS's 变量表 in row order without deduplicating variable names."""
    if bearing_type not in DB_BY_TYPE:
        raise DrawingDataError(f"Unknown bearing type: {bearing_type}")
    db_file = Path(resources) / "Data" / DB_BY_TYPE[bearing_type]
    if not db_file.is_file() or db_file.is_symlink():
        raise DrawingDataError(f"Missing or invalid RoBAS database: {db_file}")
    data = db_file.read_bytes()
    if not data.startswith(b"SQLite format 3\x00"):
        raise DrawingDataError("Invalid SQLite database")
    digest = sha256(data).hexdigest()
    try:
        with sqlite3.connect(db_file.resolve().as_uri() + "?mode=ro", uri=True) as db:
            results = db.execute('SELECT "变量名", "变量值" FROM "变量表" ORDER BY rowid').fetchall()
    except sqlite3.DatabaseError as error:
        raise DrawingDataError("Could not read RoBAS 变量表") from error
    if not results or len(results) > 2000:
        raise DrawingDataError("Empty or unusually large RoBAS 变量表")
    rows = []
    for index, (name, value) in enumerate(results):
        if not isinstance(name, str) or not name or "\x00" in name:
            raise DrawingDataError(f"Invalid variable name at row {index}")
        if value is not None and not isinstance(value, str):
            value = str(value)
        rows.append(VariableRow(name, value, index, "sqlite_default"))
    return rows, digest


def prepare_variables(*, resources: Path, bearing_type: str,
                      parameters: dict[str, object],
                      model: str | None = None,
                      accuracy_class: str | None = None,
                      checked_values: dict[str, str] | None = None) -> dict:
    """Populate only known geometry keys and explicitly supplied drawing values.

    checked_values must come from an engineering-approved source and are tagged;
    neither performance results nor tolerance limits are guessed. The output is
    NOT an export-ready manufacturing drawing.
    """
    rows, digest = read_variable_rows(resources, bearing_type)
    expected = dict(_COMMON)
    expected.update(_ROLLER if bearing_type == "rolling.cylindrical_roller" else _BALL)
    if bearing_type == "rolling.angular_contact_ball":
        expected["alfa1"] = "contact_angle_deg"
    assignments: dict[str, tuple[str, str]] = {}
    for tag, parameter_name in expected.items():
        if parameter_name not in parameters:
            raise DrawingDataError(f"Missing confirmed geometry parameter: {parameter_name}")
        value = _text(parameters[parameter_name])
        if tag == "alfa1":
            value += "°"
        assignments[tag] = (value, "confirmed_geometry")
    if model is not None:
        if bearing_type in ("rolling.deep_groove_ball", "rolling.angular_contact_ball"):
            if accuracy_class is None:
                raise DrawingDataError("RoBAS model label needs verified accuracy class")
            label = _text(model) + "/" + _text(accuracy_class)
        else:
            label = _text(model)
        assignments["model"] = (label, "explicit_drawing_context")
    names = {row.name for row in rows}
    if checked_values:
        for key, value in checked_values.items():
            if key not in names:
                raise DrawingDataError(f"Unknown RoBAS variable: {key}")
            if key in assignments:
                raise DrawingDataError(f"Cannot override confirmed geometry: {key}")
            assignments[key] = (_text(value), "explicit_drawing_context")
    absent = sorted(set(expected) - names)
    if absent:
        raise DrawingDataError(f"Unexpected RoBAS variable table: {absent}")
    populated = [
        VariableRow(row.name, assignments[row.name][0], row.row_index, assignments[row.name][1])
        if row.name in assignments else row
        for row in rows
    ]
    duplicates = {name: count for name, count in Counter(r.name for r in rows).items() if count > 1}
    unresolved = sorted({r.name for r in populated if not r.value})
    return {
        "schema_version": "robas.drawing.variables.v1",
        "bearing_type": bearing_type,
        "database": DB_BY_TYPE[bearing_type],
        "database_sha256": digest,
        "status": "DRAFT_INCOMPLETE" if unresolved else "VARIABLES_POPULATED_UNREVIEWED",
        "variables": [{"name": r.name, "value": r.value, "row_index": r.row_index,
                       "source": r.source} for r in populated],
        "duplicates": duplicates,
        "unresolved_count": len(unresolved),
        "unresolved_names": unresolved,
        "unresolved_ratings": [key for key in ("Cr", "Cor") if key in unresolved],
        "warning": "No DXF generated; no manufacturing/tolerance certification",
    }


def bridge_values(report: dict) -> list[dict[str, str]]:
    """Ordered non-null pairs, compatible with RoBAS's TEXT loop semantics."""
    if report.get("schema_version") != "robas.drawing.variables.v1":
        raise DrawingDataError("Unsupported variable contract")
    return [{"name": row["name"], "value": row["value"]}
            for row in report["variables"] if row["value"] is not None]

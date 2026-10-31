"""Read-only RoBAS standards table lookups for drawing preparation.

The source is RoBAS DataControl.GetRadialClearance/GetRoughness/GetWidthDeviation.
No manufacturing certification; missing '--' entries fail closed.
"""
from __future__ import annotations

import math
from pathlib import Path
import sqlite3

DB = {
    "rolling.deep_groove_ball": "DGBData.db",
    "rolling.angular_contact_ball": "ACBData.db",
    "rolling.cylindrical_roller": "CRBData.db",
}
ROUGHNESS = {
    "P0": "B级粗糙度表", "P6": "C级粗糙度表",
    "P5": "D级粗糙度表", "P4": "E级粗糙度表",
    "P2": "G级粗糙度表",
}
CLEARANCE = {
    "C2": (1,2), "C0": (3,4), "C3": (5,6),
    "C4": (7,8), "C5": (9,10),
}
_BALL_LABELS = ("@Dds", "@Dde", "@Dd", "@ds", "@di", "@d")
_ROLLER_LABELS = _BALL_LABELS + ("@dis", "@d2s", "@Dd2s", "@Ddis")


class StandardsLookupError(ValueError):
    pass


def _connection(resources, bearing_type):
    if bearing_type not in DB:
        raise StandardsLookupError("Unsupported bearing type")
    file = Path(resources) / "Data" / DB[bearing_type]
    if not file.is_file() or file.is_symlink():
        raise StandardsLookupError("Missing RoBAS standards database")
    return sqlite3.connect(file.resolve().as_uri() + "?mode=ro", uri=True)


def _positive_diameter(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise StandardsLookupError("Expected positive diameter in mm")
    return float(value)


def _first_range(resources, bearing_type, table, column, diameter):
    # Identifiers are hard-coded from an allowlist, not interpolated user input.
    diameter = _positive_diameter(diameter)
    with _connection(resources, bearing_type) as db:
        try:
            row = db.execute(
                f'SELECT * FROM "{table}" WHERE CAST("{column}" AS REAL) >= ? '
                f'ORDER BY CAST("{column}" AS REAL), rowid LIMIT 1',
                (diameter,)).fetchone()
        except sqlite3.Error as error:
            raise StandardsLookupError("RoBAS standards table missing or corrupt") from error
    if row is None:
        raise StandardsLookupError(f"No matching range in {table}")
    return row


def _known(value):
    if value is None or str(value).strip() in ("", "--", "None"):
        raise StandardsLookupError("Undefined RoBAS standard value")
    return str(value)


def get_radial_clearance(*, resources, bearing_type, bore_d_mm, group):
    if group not in CLEARANCE:
        raise StandardsLookupError("Unsupported radial clearance group")
    row = _first_range(resources, bearing_type, "游隙", "d", bore_d_mm)
    first, second = CLEARANCE[group]
    low = float(_known(row[first])) / 1000
    high = float(_known(row[second])) / 1000
    if low > high:
        raise StandardsLookupError("Inconsistent clearance limits")
    return {"source": "RoBAS 游隙", "status": "LOOKUP_ONLY",
            "group": group, "minimum_mm": low, "maximum_mm": high}


def get_roughness(*, resources, bearing_type, bore_d_mm, accuracy_class):
    if accuracy_class not in ROUGHNESS:
        raise StandardsLookupError("Unsupported accuracy grade")
    is_roller = bearing_type == "rolling.cylindrical_roller"
    table = "粗糙度表" if is_roller else ROUGHNESS[accuracy_class]
    row = _first_range(resources, bearing_type, table, "套圈直径", bore_d_mm)
    names = _ROLLER_LABELS if is_roller else _BALL_LABELS
    return {"source": table, "status": "LOOKUP_ONLY",
            "accuracy_class": accuracy_class,
            "values": {name: _known(row[i]) for i, name in enumerate(names, 1)}}


def get_width_deviation(*, resources, bearing_type, bore_d_mm, size_series):
    if size_series not in ("0", "2", "3"):
        raise StandardsLookupError("Unsupported size series")
    row = _first_range(resources, bearing_type, "轴承宽度公差", "d", bore_d_mm)
    if bearing_type == "rolling.cylindrical_roller":
        first, second = 1, 2
    else:
        first, second = {"0": (1, 2), "2": (3, 4), "3": (5, 6)}[size_series]
    return {"source": "轴承宽度公差", "status": "LOOKUP_ONLY",
            "size_series": size_series,
            "upper_mm": _known(row[first]), "lower_mm": _known(row[second])}


def prepare_standard_variables(*, resources, bearing_type, bore_d_mm,
                               accuracy_class, clearance_group, size_series):
    """Produce exact RoBAS database variable keys, for separate expert review.

    Explicit selections are mandatory. The returned values are not certified
    for manufacture; caller must retain the lookup context and approvals.
    """
    radial = get_radial_clearance(resources=resources, bearing_type=bearing_type,
                                  bore_d_mm=bore_d_mm, group=clearance_group)
    surface = get_roughness(resources=resources, bearing_type=bearing_type,
                            bore_d_mm=bore_d_mm, accuracy_class=accuracy_class)
    width = get_width_deviation(resources=resources, bearing_type=bearing_type,
                                bore_d_mm=bore_d_mm, size_series=size_series)
    fields = dict(surface["values"])
    fields.update({
        "Cmin": format(radial["minimum_mm"], ".15g"),
        "Cmax": format(radial["maximum_mm"], ".15g"),
        "B_Upper": width["upper_mm"],
        "B_Lower": width["lower_mm"],
    })
    return {
        "status": "LOOKUP_ONLY_REQUIRES_APPROVAL",
        "values": fields,
        "sources": {
            "clearance": radial["source"],
            "roughness": surface["source"],
            "width_deviation": width["source"],
        },
        "selections": {
            "accuracy_class": accuracy_class,
            "clearance_group": clearance_group,
            "size_series": size_series,
        },
    }

"""Test faithful RoBAS C# field-index, series and table-overlay behaviour."""
import sqlite3

import pytest

from bearing_cad.drawing_legacy_technical import (
    technical_condition_rows, apply_technical_conditions,
)
from bearing_cad.drawing_variables import (
    DrawingDataError, prepare_variables,
)

DBS = {
    "rolling.deep_groove_ball": "DGBData.db",
    "rolling.angular_contact_ball": "ACBData.db",
    "rolling.cylindrical_roller": "CRBData.db",
}
_PARAMS = {
    "outside_d_mm": 68, "bore_d_mm": 40, "width_mm": 15,
    "ball_d_mm": 8.3, "ball_count": 11, "contact_angle_deg": 25,
    "roller_d_mm": 8, "roller_length_mm": 12, "roller_count": 12,
}


@pytest.fixture
def source_tables(tmp_path):
    data = tmp_path / "Data"
    data.mkdir()
    all_names = ["Dd", "d", "B_", "Dw", "Z", "Lw", "alfa1", "d_Upper",
                 "Dd_Upper", "Vdp", "ZVDdp", "Sd", "VDdp", "VBs",
                 "Le", "Sde", "Cr", "Cor"]
    for kind, filename in DBS.items():
        with sqlite3.connect(data / filename) as db:
            db.execute('CREATE TABLE "变量表" ("变量名" TEXT, "变量值" TEXT)')
            db.executemany('INSERT INTO "变量表" VALUES (?,NULL)',
                           [(name,) for name in all_names])
            db.execute('INSERT INTO "变量表" VALUES ("Vdp",NULL)')
            for suffix in ("总图外圈技术条件", "总图内圈技术条件",
                           "外圈技术条件", "内圈技术条件"):
                table = "D级" + suffix
                cols = ", ".join(f'"a{i}" TEXT' for i in range(1, 22))
                db.execute(f'CREATE TABLE "{table}" ("d" REAL, {cols})')
                # First-match row and stable source index are observable.
                db.execute(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in range(22))})',
                           [100] + [str(i) for i in range(1, 22)])
    return tmp_path


@pytest.mark.parametrize("bearing_type", list(DBS))
@pytest.mark.parametrize("diameter_series, expected_vdp", [
    ("9", "2"), ("0", "3"), ("2", "4"),
])
def test_original_index_branches(source_tables, bearing_type, diameter_series, expected_vdp):
    entries = technical_condition_rows(
        resources=source_tables, bearing_type=bearing_type,
        bore_d_mm=40, outside_d_mm=68,
        accuracy_class="P5", diameter_series=diameter_series)
    # The C# general and component tables both contribute.
    assert len(entries) > 20
    assert next(e["value"] for e in entries if e["name"] == "Vdp") == expected_vdp
    assert [e["value"] for e in entries if e["name"] == "d_Upper"] == ["0", "0"]
    assert next(e["value"] for e in entries if e["name"] == "ZVDdp") == (
        "2" if diameter_series == "9" else
        "3" if diameter_series == "0" else "4")
    if bearing_type == "rolling.cylindrical_roller":
        assert next(e["value"] for e in entries if e["name"] == "Le") == "---"
    else:
        assert next(e["value"] for e in entries if e["name"] == "Si") == "6"


@pytest.mark.parametrize("bearing_type", list(DBS))
def test_report_overlay_keeps_duplicate_rows(source_tables, bearing_type):
    base = prepare_variables(resources=source_tables, bearing_type=bearing_type,
                             parameters=_PARAMS)
    before = [dict(row) for row in base["variables"]]
    entries = technical_condition_rows(
        resources=source_tables, bearing_type=bearing_type,
        bore_d_mm=40, outside_d_mm=68, accuracy_class="P5",
        diameter_series="0")
    revised = apply_technical_conditions(base, entries)
    assert [r for r in revised["variables"] if r["name"] == "Vdp"] == [
        {"name": "Vdp", "value": "3", "row_index": 9,
         "source": "robas_technical:D级内圈技术条件"},
        {"name": "Vdp", "value": "3", "row_index": 18,
         "source": "robas_technical:D级内圈技术条件"},
    ]
    assert base["variables"] == before  # No mutation.
    assert "Cr" in revised["unresolved_names"]


def test_invalid_grade_series_dimension(source_tables):
    params = dict(resources=source_tables, bearing_type="rolling.deep_groove_ball",
                  bore_d_mm=40, outside_d_mm=68,
                  accuracy_class="P5", diameter_series="0")
    for key, value in (("accuracy_class", "P7"), ("diameter_series", "6"),
                       ("bore_d_mm", 0), ("outside_d_mm", 5)):
        with pytest.raises(DrawingDataError):
            technical_condition_rows(**{**params, key: value})


def test_unknown_fields_not_inserted_in_variable_table(source_tables):
    base = prepare_variables(resources=source_tables,
        bearing_type="rolling.deep_groove_ball", parameters=_PARAMS)
    rows = [{"name": "NOT_IN_TEMPLATE", "value": "123", "source": "test"}]
    revised = apply_technical_conditions(base, rows)
    assert all(r["name"] != "NOT_IN_TEMPLATE" for r in revised["variables"])

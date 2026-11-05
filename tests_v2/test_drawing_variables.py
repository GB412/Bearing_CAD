"""SQLite drawing variables are never allowed to manufacture unverified values."""
import math
import sqlite3
import pytest

from bearing_cad.drawing_variables import (
    DrawingDataError, read_variable_rows, prepare_variables, bridge_values,
    restore_checked_values,
)

FIELDS = {
 "rolling.deep_groove_ball": ("DGBData.db", ["model","d","Dw","Z","B_","Dd","d","Dw","Cr","Cor"]),
 "rolling.angular_contact_ball": ("ACBData.db", ["model","d","Dw","Z","B_","Dd","alfa1","Cr","Cor"]),
 "rolling.cylindrical_roller": ("CRBData.db", ["model","d","Dw","Z","Lw","B_","Dd","Cr","Cor"]),
}
PARAMS = {"bore_d_mm":40, "outside_d_mm":68, "width_mm":15,
          "ball_d_mm":8.2, "ball_count":11, "contact_angle_deg":25,
          "roller_d_mm":8.0, "roller_length_mm":12.0, "roller_count":12}


@pytest.fixture
def mock_resources(tmp_path):
    root = tmp_path / "Data"
    root.mkdir()
    for _, (database, names) in FIELDS.items():
        con=sqlite3.connect(root/database)
        con.execute('CREATE TABLE "变量表" ("变量名" TEXT, "变量值" TEXT)')
        con.executemany('INSERT INTO "变量表" VALUES (?,?)',
                        [(name, "original" if name=="model" else None) for name in names])
        con.commit()
        con.close()
    return tmp_path


@pytest.mark.parametrize("bearing_type", list(FIELDS))
def test_read_and_fill_preserve_duplicate_rows(mock_resources, bearing_type):
    rows, checksum = read_variable_rows(mock_resources, bearing_type)
    assert len(checksum) == 64
    assert len(rows) == len(FIELDS[bearing_type][1])
    report = prepare_variables(resources=mock_resources,
        bearing_type=bearing_type, parameters=PARAMS, model="TEST",
        accuracy_class="P5")
    assert report["status"] == "DRAFT_INCOMPLETE"
    assert report["unresolved_ratings"] == ["Cr", "Cor"]
    assignments = bridge_values(report)
    assert assignments
    assert [r["value"] for r in assignments if r["name"]=="d"] == (
        ["40", "40"] if bearing_type=="rolling.deep_groove_ball" else ["40"])
    if bearing_type=="rolling.deep_groove_ball":
        assert report["duplicates"]["d"]==2
        assert report["duplicates"]["Dw"]==2
    assert [r["value"] for r in assignments if r["name"]=="model"] == [
        "TEST" if bearing_type=="rolling.cylindrical_roller" else "TEST/P5"]


def test_cannot_override_confirmed_geometry(mock_resources):
    with pytest.raises(DrawingDataError,match="override confirmed geometry"):
        prepare_variables(resources=mock_resources, bearing_type="rolling.deep_groove_ball",
                          parameters=PARAMS, checked_values={"d":"999"})


def test_invalid_floating_point_rejected(mock_resources):
    with pytest.raises(DrawingDataError,match="Non-finite"):
        prepare_variables(resources=mock_resources, bearing_type="rolling.angular_contact_ball",
                          parameters={**PARAMS, "contact_angle_deg":math.nan})


def test_missing_geometry_or_class_rejected(mock_resources):
    with pytest.raises(DrawingDataError, match="Missing confirmed geometry"):
        prepare_variables(resources=mock_resources,bearing_type="rolling.deep_groove_ball",
                          parameters={"bore_d_mm":40})
    with pytest.raises(DrawingDataError, match="accuracy class"):
        prepare_variables(resources=mock_resources,bearing_type="rolling.deep_groove_ball",
                          parameters=PARAMS, model="TEST")


def test_read_only_database(mock_resources):
    db=mock_resources/"Data"/"DGBData.db"
    before=db.read_bytes()
    read_variable_rows(mock_resources,"rolling.deep_groove_ball")
    assert db.read_bytes()==before


def test_forbidden_or_unrecognised_data(mock_resources):
    with pytest.raises(DrawingDataError):
        read_variable_rows(mock_resources,"rolling.typo")
    with pytest.raises(DrawingDataError):
        prepare_variables(resources=mock_resources,bearing_type="rolling.deep_groove_ball",
                          parameters=PARAMS,checked_values={"NOT_A_VARIABLE":"42"})
    with pytest.raises(DrawingDataError):
        bridge_values({"schema_version":"wrong","variables":[]})

def test_robas_null_rows_become_blank_replacements(mock_resources):
    """RoBAS DataRow DBNull.ToString() -> '' and every row participates."""
    report = prepare_variables(resources=mock_resources,
        bearing_type="rolling.deep_groove_ball", parameters=PARAMS,
        model="6008", accuracy_class="P5")
    rows = bridge_values(report)
    assert len(rows) == len(FIELDS["rolling.deep_groove_ball"][1])
    assert [row for row in rows if row["name"] == "Cr"] == [
        {"name": "Cr", "value": ""}]
    assert [row["value"] for row in rows if row["name"] == "Dw"] == ["8.2", "8.2"]
    assert [row["name"] for row in rows] == FIELDS["rolling.deep_groove_ball"][1]


def test_approved_drawing_labels_have_final_precedence(mock_resources):
    from bearing_cad.drawing_legacy_dimensions import overlay
    before = prepare_variables(
        resources=mock_resources, bearing_type="rolling.deep_groove_ball",
        parameters=PARAMS, checked_values={"Cr": "26.50", "Cor": "24.75"})
    calculated = overlay(before, {"Cr": "0.00", "Cor": "13.00"}, "robas_loads")
    final = restore_checked_values(calculated, before, {"Cr": "26.50", "Cor": "24.75"})
    fields = {r["name"]: r["value"] for r in final["variables"]}
    assert fields["Cr"] == "26.50"
    assert fields["Cor"] == "24.75"
    assert final["checked_value_names"] == ["Cor", "Cr"]
    assert "Cr" not in final["unresolved_names"]
    assert all(r["source"] == "explicit_checked_value"
               for r in final["variables"] if r["name"] in ("Cr", "Cor"))
    assert bridge_values(final)[-2:] == [
        {"name": "Cr", "value": "26.50"}, {"name": "Cor", "value": "24.75"}]


def test_checked_values_cannot_bypass_original_approval_validation(mock_resources):
    before = prepare_variables(
        resources=mock_resources, bearing_type="rolling.deep_groove_ball",
        parameters=PARAMS)
    for wrong in ({"d": "999"}, {"Cr": "123"}):
        with pytest.raises(DrawingDataError, match="not validated"):
            restore_checked_values(before, before, wrong)
    assert restore_checked_values(before, before, None) is before


def test_duplicate_sqlite_rows_preserved_by_final_overrides(mock_resources):
    from bearing_cad.drawing_legacy_dimensions import overlay
    before = prepare_variables(
        resources=mock_resources, bearing_type="rolling.deep_groove_ball",
        parameters=PARAMS, checked_values={"Cr": "28.12"})
    calculated = overlay(before, {"Cr": "0"}, "auto")
    final = restore_checked_values(calculated, before, {"Cr": "28.12"})
    assert [r["name"] for r in final["variables"]] == [
        r["name"] for r in before["variables"]]
    assert {r["name"]: r["value"] for r in final["variables"]}["Cr"] == "28.12"

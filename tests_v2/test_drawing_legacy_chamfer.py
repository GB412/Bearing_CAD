"""Original RoBAS chamfer formatting: matched rsmin and row-order side effects."""
import sqlite3

import pytest

from bearing_cad.drawing_legacy_chamfer import apply_robas_chamfer
from bearing_cad.drawing_variables import prepare_variables, DrawingDataError

KINDS = {
    "rolling.deep_groove_ball": "DGBData.db",
    "rolling.angular_contact_ball": "ACBData.db",
    "rolling.cylindrical_roller": "CRBData.db",
}
PARAMS = {
    "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
    "ball_d_mm": 8, "ball_count": 11, "contact_angle_deg": 25,
    "roller_d_mm": 8, "roller_length_mm": 12, "roller_count": 12,
}


@pytest.fixture
def resources(tmp_path):
    folder = tmp_path / "Data"
    folder.mkdir()
    names = [
        "Dd", "d", "B_", "Dw", "Z", "Lw", "alfa1", "rs_r",
        "rs_r_Upper", "rs_r_Lower", "rs_a", "rs_a_Upper",
        "rs_a_Upper1", "rs_a_Lower", "r3", "r3_Upper",
        "r8", "r8_Upper", "r1s_r", "r1s_r_Upper",
        "r1s_a", "r1s_a_Lower", "r2", "r5", "Cr", "Cor",
    ]
    for filename in KINDS.values():
        with sqlite3.connect(folder / filename) as db:
            db.execute('CREATE TABLE "变量表" ("变量名" TEXT,"变量值" TEXT)')
            db.executemany('INSERT INTO "变量表" VALUES (?,NULL)',
                           [(name,) for name in names])
            cols = ",".join(f'"x{i}" TEXT' for i in range(1, 22))
            db.execute(f'CREATE TABLE "倒角尺寸表" ("rsmin" REAL,{cols})')
            rows = [
                [0.3, "0", "0.4", "0.8", "1.2", "+0.1", "-0.1",
                 "2.2", "0", "-0.2", "3.2", "+0.2", "-0.3",
                 "4.2", "+0.2", "-0.2", "5.2", "+0.3", "-0.3",
                 "6.2", "+0.4", "-0.4"],
                [0.5, "0", "1.4", "1.8", "7.2", "+0.5", "-0.5",
                 "8.2", "+0.6", "-0.6", "9.2", "+0.7", "-0.7",
                 "10.2", "+0.8", "-0.8", "11.2", "+0.9", "-0.9",
                 "12.2", "+1.0", "-1.0"],
            ]
            placeholders = ",".join("?" for _ in range(22))
            db.executemany(
                f'INSERT INTO "倒角尺寸表" VALUES ({placeholders})',
                rows)
    return tmp_path


@pytest.mark.parametrize("kind", list(KINDS))
def test_original_chamfer_mapping(resources, kind):
    base = prepare_variables(resources=resources, bearing_type=kind,
                             parameters=PARAMS)
    revised = apply_robas_chamfer(
        report=base, resources=resources, bearing_type=kind,
        chamfer1_mm=.3,
        chamfer2_mm=.5 if kind != "rolling.deep_groove_ball" else None)
    v = {row["name"]: row["value"] for row in revised["variables"]}
    if kind == "rolling.cylindrical_roller":
        assert v["rs_r"] == "1.2"
        assert v["rs_r_Upper"] == "+0.1"
        assert v["r1s_r"] == "7.2"
        assert v["r2"] == "5.2"
    else:
        assert v["rs_r"] == "1.2±0.1"
        # Original C# empties the upper/lower fields once nominal is compacted.
        assert v["rs_r_Upper"] == ""
        assert v["rs_a_Upper1"] == "0"
        if kind == "rolling.angular_contact_ball":
            assert v["r1s_r"] == "7.2±0.5"
    assert "Cr" in revised["unresolved_names"]
    assert not revised["chamfer_lookup_warning"]


def test_missing_rsmin_does_not_fabricate_value(resources):
    base = prepare_variables(resources=resources,
        bearing_type="rolling.deep_groove_ball", parameters=PARAMS)
    result = apply_robas_chamfer(
        report=base, resources=resources,
        bearing_type="rolling.deep_groove_ball", chamfer1_mm=0.4)
    assert result["chamfer_lookup_warning"]
    assert result["variables"] == base["variables"]


def test_bad_chamfer_or_missing_second_rejected(resources):
    base = prepare_variables(resources=resources,
        bearing_type="rolling.angular_contact_ball", parameters=PARAMS)
    with pytest.raises(DrawingDataError, match="requires chamfer2"):
        apply_robas_chamfer(report=base, resources=resources,
            bearing_type="rolling.angular_contact_ball", chamfer1_mm=.3)
    with pytest.raises(DrawingDataError, match="positive"):
        apply_robas_chamfer(report=base, resources=resources,
            bearing_type="rolling.angular_contact_ball",
            chamfer1_mm=-1, chamfer2_mm=.5)

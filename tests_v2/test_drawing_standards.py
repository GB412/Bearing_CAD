"""Tests use synthetic standards tables; genuine RoBAS tables audited separately."""
import sqlite3
import pytest

from bearing_cad.drawing_standards import (
    StandardsLookupError, get_radial_clearance, get_roughness, get_width_deviation,
)

DATABASES=("DGBData.db","ACBData.db","CRBData.db")

@pytest.fixture
def resources(tmp_path):
    path=tmp_path/"Data"
    path.mkdir()
    for name in DATABASES:
        with sqlite3.connect(path/name) as db:
            db.execute('CREATE TABLE "游隙" (d REAL,"2_B" TEXT,"2_S" TEXT,"0_B" TEXT,"0_S" TEXT,"3_B" TEXT,"3_S" TEXT,"4_B" TEXT,"4_S" TEXT,"5_B" TEXT,"5_S" TEXT)')
            db.executemany('INSERT INTO "游隙" VALUES (?,?,?,?,?,?,?,?,?,?,?)',[
                (50,"3","9","8","14","10","22","--","--","--","--"),
                (80,"4","11","9","17","11","25","14","29","20","37"),
            ])
            db.execute('CREATE TABLE "轴承宽度公差" (d REAL,"0B_Upper" TEXT,"0B_Lower" TEXT,"2B_Upper" TEXT,"2B_Lower" TEXT,"3B_Upper" TEXT,"3B_Lower" TEXT)')
            db.execute('INSERT INTO "轴承宽度公差" VALUES (50,"0","-0.3","0","-0.4","0","-0.5")')
            table="粗糙度表" if name=="CRBData.db" else "D级粗糙度表"
            values=[(f"_{i}", "0.5") for i in range(1,11 if name=="CRBData.db" else 7)]
            columns=", ".join('"'+c+'" TEXT' for c,_ in values)
            db.execute(f'CREATE TABLE "{table}" ("套圈直径" REAL,{columns})')
            names=",".join("?" for i in range(len(values)+1))
            db.execute(f'INSERT INTO "{table}" VALUES ({names})',[50]+[v for _,v in values])
    return tmp_path

@pytest.mark.parametrize("kind",["rolling.deep_groove_ball","rolling.angular_contact_ball","rolling.cylindrical_roller"])
def test_clearance_and_missing_group(resources,kind):
    report=get_radial_clearance(resources=resources,bearing_type=kind,bore_d_mm=40,group="C0")
    assert report["minimum_mm"]==pytest.approx(0.008)
    assert report["maximum_mm"]==pytest.approx(0.014)
    with pytest.raises(StandardsLookupError,match="Undefined"):
        get_radial_clearance(resources=resources,bearing_type=kind,bore_d_mm=40,group="C5")

@pytest.mark.parametrize("kind",["rolling.deep_groove_ball","rolling.angular_contact_ball","rolling.cylindrical_roller"])
def test_roughness_reads_source_table(resources,kind):
    r=get_roughness(resources=resources,bearing_type=kind,bore_d_mm=40,accuracy_class="P5")
    assert r["status"]=="LOOKUP_ONLY"
    assert len(r["values"]) == (10 if kind.endswith("cylindrical_roller") else 6)

def test_width_deviation_by_series(resources):
    value=get_width_deviation(resources=resources,bearing_type="rolling.deep_groove_ball",
                              bore_d_mm=40,size_series="2")
    assert value["lower_mm"]=="-0.4"
    with pytest.raises(StandardsLookupError):
        get_width_deviation(resources=resources,bearing_type="rolling.deep_groove_ball",
                            bore_d_mm=40,size_series="7")

def test_reject_out_of_range_and_invalid_diameter(resources):
    with pytest.raises(StandardsLookupError):
        get_radial_clearance(resources=resources,bearing_type="rolling.deep_groove_ball",bore_d_mm=200,group="C0")
    with pytest.raises(StandardsLookupError):
        get_radial_clearance(resources=resources,bearing_type="rolling.deep_groove_ball",bore_d_mm=0,group="C0")


def test_explict_standard_values_are_not_approved(resources):
    from bearing_cad.drawing_standards import prepare_standard_variables
    report=prepare_standard_variables(
        resources=resources, bearing_type="rolling.deep_groove_ball",
        bore_d_mm=40, accuracy_class="P5", clearance_group="C0",
        size_series="2")
    assert report["status"] == "LOOKUP_ONLY_REQUIRES_APPROVAL"
    assert report["values"]["Cmin"] == "0.008"
    assert report["values"]["Cmax"] == "0.014"
    assert report["values"]["B_Lower"] == "-0.4"
    assert report["values"]["@Dds"] == "0.5"


def _blank_report(names):
    return {
        "schema_version": "robas.drawing.variables.v1",
        "variables": [{"name": name, "value": None, "source": "sqlite_default",
                       "row_index": i} for i, name in enumerate(names)],
    }


def test_standard_lookups_are_applied_to_real_drawing_values(resources):
    from bearing_cad.drawing_standard_fill import apply_robas_drawing_standards
    original = _blank_report(["@Dds", "@di", "B_Upper", "B_Lower",
                              "Cmin", "Cmax", "KEEP_UNSET", "@Dds"])
    result = apply_robas_drawing_standards(
        report=original, resources=resources,
        bearing_type="rolling.deep_groove_ball", bore_d_mm=40,
        accuracy_class="P5", diameter_series="2",
        radial_clearance_group="C0")
    def value(key):
        return [r["value"] for r in result["variables"] if r["name"] == key]
    assert value("@Dds") == ["0.5", "0.5"]
    assert value("@di") == ["0.5"]
    assert value("B_Upper") == ["0"]
    assert value("B_Lower") == ["-0.4"]
    assert value("Cmin") == ["0.008"]
    assert value("Cmax") == ["0.014"]
    assert value("KEEP_UNSET") == [None]
    assert len(result["standard_lookup_evidence"]) == 3
    assert result["standard_lookup_warnings"] == []
    assert original["variables"][0]["value"] is None


def test_optional_clearance_never_defaults_to_a_guess(resources):
    from bearing_cad.drawing_standard_fill import apply_robas_drawing_standards
    result = apply_robas_drawing_standards(
        report=_blank_report(["Cmin", "Cmax", "B_Lower"]),
        resources=resources, bearing_type="rolling.deep_groove_ball",
        bore_d_mm=40, accuracy_class="P5", diameter_series="2")
    assert [r["value"] for r in result["variables"]] == [None, None, "-0.4"]
    assert result["radial_clearance_group"] is None
    assert len(result["standard_lookup_evidence"]) == 2


def test_unknown_original_ball_width_series_and_missing_clearance_are_reported(resources):
    from bearing_cad.drawing_standard_fill import apply_robas_drawing_standards
    result = apply_robas_drawing_standards(
        report=_blank_report(["B_Upper", "Cmin"]),
        resources=resources, bearing_type="rolling.deep_groove_ball",
        bore_d_mm=40, diameter_series="7",
        radial_clearance_group="C5")
    assert [r["value"] for r in result["variables"]] == [None, None]
    assert any(s.startswith("WIDTH_DEVIATION_UNAVAILABLE")
               for s in result["standard_lookup_warnings"])
    assert any(s.startswith("RADIAL_CLEARANCE_UNAVAILABLE")
               for s in result["standard_lookup_warnings"])


def test_original_roller_width_is_independent_of_ball_diameter_series(resources):
    from bearing_cad.drawing_standard_fill import apply_robas_drawing_standards
    result = apply_robas_drawing_standards(
        report=_blank_report(["B_Lower"]),
        resources=resources, bearing_type="rolling.cylindrical_roller",
        bore_d_mm=40, diameter_series="7")
    assert result["variables"][0]["value"] == "-0.3"


def test_unsorted_source_table_uses_first_matching_row_not_sorted_minimum(resources):
    from bearing_cad.drawing_standards import get_width_deviation
    import sqlite3
    db = resources / "Data" / "DGBData.db"
    with sqlite3.connect(db) as con:
        con.execute('DELETE FROM "轴承宽度公差"')
        con.executemany('INSERT INTO "轴承宽度公差" VALUES (?,?,?,?,?,?,?)', [
            (80, "0", "-0.8", "0", "-0.81", "0", "-0.82"),
            (50, "0", "-0.5", "0", "-0.51", "0", "-0.52"),
        ])
    assert get_width_deviation(resources=resources,
                               bearing_type="rolling.deep_groove_ball",
                               bore_d_mm=40, size_series="2")["lower_mm"] == "-0.81"



@pytest.mark.parametrize("kind", [
    "rolling.deep_groove_ball", "rolling.angular_contact_ball",
    "rolling.cylindrical_roller",
])
def test_real_source_0p01_bearing_getter_selects_correct_standard_range(
        resources, kind):
    """All three C# bearing getters round before GetRadialClearance,
    GetRoughness and GetWidthDeviation. The source first-row order remains.
    """
    from bearing_cad.drawing_standard_fill import apply_robas_drawing_standards
    from bearing_cad.drawing_standards import original_bearing_diameter_getter_mm
    assert original_bearing_diameter_getter_mm(30.004) == 30.0
    assert original_bearing_diameter_getter_mm(30.006) == 30.01
    path = resources / "Data" / {
        "rolling.deep_groove_ball": "DGBData.db",
        "rolling.angular_contact_ball": "ACBData.db",
        "rolling.cylindrical_roller": "CRBData.db",
    }[kind]
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM "游隙"')
        db.executemany('INSERT INTO "游隙" VALUES (?,?,?,?,?,?,?,?,?,?,?)', [
            (30, "1","2","3","5","7","9","--","--","--","--"),
            (50, "2","3","8","11","12","14","--","--","--","--"),
        ])
        db.execute('DELETE FROM "轴承宽度公差"')
        if kind == "rolling.cylindrical_roller":
            # Fixture initially has the ball schema. Source CRB width table
            # has just B_Upper/B_Lower; maintain the fixture columns and
            # apply the first pair exactly as the original CRB data does.
            db.executemany('INSERT INTO "轴承宽度公差" VALUES (?,?,?,?,?,?,?)', [
                (30,"0","-0.1","0","-0.1","0","-0.1"),
                (50,"0","-0.2","0","-0.2","0","-0.2"),
            ])
        else:
            db.executemany('INSERT INTO "轴承宽度公差" VALUES (?,?,?,?,?,?,?)', [
                (30,"0","-0.1","0","-0.1","0","-0.1"),
                (50,"0","-0.2","0","-0.2","0","-0.2"),
            ])
        roughness_table = ("粗糙度表" if kind == "rolling.cylindrical_roller"
                           else "D级粗糙度表")
        db.execute(f'DELETE FROM "{roughness_table}"')
        columns = 10 if kind == "rolling.cylindrical_roller" else 6
        marks = ",".join("?" for _ in range(columns+1))
        db.executemany(f'INSERT INTO "{roughness_table}" VALUES ({marks})', [
            (30, *("0.1",)*columns),
            (50, *("0.2",)*columns),
        ])
    for original, bound, radial, width, roughness in [
        (30.004, 30, "0.003", "-0.1", "0.1"),
        (30.006, 50, "0.008", "-0.2", "0.2"),
    ]:
        got = apply_robas_drawing_standards(
            report=_blank_report(["Cmin","Cmax","B_Lower","@Dds"]),
            resources=resources,bearing_type=kind,bore_d_mm=original,
            accuracy_class="P5", diameter_series="2",radial_clearance_group="C0")
        by_key={x["name"]:x["value"] for x in got["variables"]}
        assert by_key["Cmin"] == radial
        assert by_key["B_Lower"] == width
        assert by_key["@Dds"] == roughness
        assert {row["source_range_upper_mm"] for row in got["standard_lookup_evidence"]} == {bound}
        assert {row["lookup_diameter_mm"] for row in got["standard_lookup_evidence"]} == {round(original,2)}
        assert got["standard_lookup_warnings"] == []


def test_source_getter_diameter_that_rounds_to_zero_is_rejected(resources):
    from bearing_cad.drawing_standard_fill import apply_robas_drawing_standards
    from bearing_cad.drawing_standards import original_bearing_diameter_getter_mm
    with pytest.raises(StandardsLookupError, match="rounded bearing diameter"):
        original_bearing_diameter_getter_mm(0.004)
    with pytest.raises(StandardsLookupError, match="rounded bearing diameter"):
        apply_robas_drawing_standards(
            report=_blank_report(["Cmin"]),resources=resources,
            bearing_type="rolling.deep_groove_ball",bore_d_mm=0.004,
            radial_clearance_group="C0")

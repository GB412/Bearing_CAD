"""CRB RoBAS original width and E1/E2 truncation semantics."""
import sqlite3
import pytest
from bearing_cad.drawing_legacy_roller import (
    apply_cylindrical_roller_dimensions,roller_groove_width_deviation,
)
from bearing_cad.drawing_variables import DrawingDataError

P={"bore_d_mm":40,"outside_d_mm":80,"width_mm":18,"roller_d_mm":8,
   "roller_length_mm":12,"roller_count":12,"pitch_d_mm":60}

def report():
    names=["E","E_Upper","E_Lower","E1","E2","a","a2","De","di",
           "Dd2","d2","Cr","Cor","MISSING"]
    return {"schema_version":"robas.drawing.variables.v1",
            "variables":[{"name":name,"value":None,"row_index":i,"source":"db"}
                         for i,name in enumerate(names)]}

@pytest.fixture
def resources(tmp_path):
    db=tmp_path/"Data"
    db.mkdir()
    with sqlite3.connect(db/"CRBData.db") as con:
        con.execute('CREATE TABLE "滚道宽度公差" ("rollerLength" INTEGER,"上偏差" TEXT,"下偏差" TEXT)')
        con.executemany('INSERT INTO "滚道宽度公差" VALUES (?,?,?)',
                        [(10,"+0.07","-0.03"),(30,"+0.09","-0.03"),(120,"+0.1","-0.04")])
    return tmp_path

def test_roll_width_source_table_range(resources):
    assert roller_groove_width_deviation(resources,12)=={"E_Upper":"+0.09","E_Lower":"-0.03"}
    assert roller_groove_width_deviation(resources,150)=={}

def test_original_crb_drawings(resources):
    old={"inner_groove_position_mm":5.1,"outer_groove_d_mm":60.2,
         "inner_groove_d_mm":58.3,"outer_sidewall_d_mm":73,
         "inner_sidewall_d_mm":49,"dynamic_load_n":26500,
         "static_load_n":25000}
    changed=apply_cylindrical_roller_dimensions(report=report(),
        parameters=P,legacy_values=old,resources=resources)
    v={row["name"]:row["value"] for row in changed["variables"]}
    assert v["E"]=="12" and v["E_Upper"]=="+0.09"
    assert v["a"]=="3±0.025"
    assert v["a2"]=="2.6"
    # (5.1 - 0.05*8)/0.5 = 9.4, C# int cast -> 9 -> 4.5
    assert v["E1"]=="9" and v["E2"]=="8.4"
    assert v["De"]=="60.200±0.015" and v["di"]=="58.300±0.015"
    assert v["Dd2"]=="73.0" and v["d2"]=="49.0"
    assert v["Cr"]=="26.50" and v["Cor"]=="25.00"
    assert v["MISSING"] is None

def test_crb_without_old_inner_position_does_not_guess(resources):
    r=apply_cylindrical_roller_dimensions(report=report(),parameters=P,resources=resources)
    v={row["name"]:row["value"] for row in r["variables"]}
    assert v["E1"] is None and v["E2"] is None
    assert v["E"]=="12"
    assert v["E_Upper"]=="+0.09"

def test_crb_invalid_inputs(resources):
    with pytest.raises(DrawingDataError):
        apply_cylindrical_roller_dimensions(report=report(),parameters=P,legacy_values={"inner_groove_position_mm":float("nan")})
    with pytest.raises(DrawingDataError):
        roller_groove_width_deviation(resources,-1)

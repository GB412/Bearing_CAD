"""DGB RoBAS drawing text regression, not a CAD shape parity test."""
import math
import pytest
from bearing_cad.drawing_legacy_dimensions import (
    apply_deep_groove_dimensions,groove_d_tolerance,groove_position_tolerance,
    groove_radius_tolerance,sidewall_d_tolerance,
)
from bearing_cad.drawing_variables import DrawingDataError

P={"bore_d_mm":40,"outside_d_mm":68,"width_mm":15,
   "ball_d_mm":8,"ball_count":11,"pitch_d_mm":54,
   "inner_groove_radius_mm":4.2,"outer_groove_radius_mm":4.4,
   "inner_shoulder_d_mm":46,"outer_shoulder_d_mm":62}

def report(names):
    return {"schema_version":"robas.drawing.variables.v1",
            "variables":[{"name":k,"value":None,"source":"sqlite_default",
                          "row_index":i} for i,k in enumerate(names)]}

def test_tolerance_source_boundaries():
    assert groove_d_tolerance(30)==.01
    assert groove_d_tolerance(40)==.015
    assert groove_position_tolerance(40)==.025
    assert groove_radius_tolerance(8)==.04
    assert sidewall_d_tolerance(40)==.25
    assert groove_position_tolerance(4000)==0

def test_dgb_robas_labels_are_formatted_and_preserve_order():
    names=["Ri","Ri_Upper","Re","De","di","a","Dd2","Dd2_Upper",
           "d2","d2_Lower","C_","Dcp","W04","W04Z","W01","W02",
           "W07","W07Z","W","Cr","Cor","NO_FIELD","Ri"]
    legacy={"inner_groove_d_mm":53.1,"outer_groove_d_mm":55.2,
            "inner_groove_position_mm":7.2,"cage_pocket_spacing_mm":15.5,
            "cage_pitch_d_mm":54,"cage_pitch_tolerance_mm":.015,
            "outer_race_weight_kg":.08,"inner_race_weight_kg":.05,
            "half_cage_weight_kg":.01,"dynamic_load_n":12456,
            "static_load_n":9865}
    original=report(names)
    updated=apply_deep_groove_dimensions(report=original,parameters=P,legacy_values=legacy)
    def allv(key):return [r["value"] for r in updated["variables"] if r["name"]==key]
    assert allv("Ri")==["4.20","4.20"]
    assert allv("Ri_Upper")==["+0.04"]
    assert allv("Re")==["4.40"]
    assert allv("De")==["55.200±0.015"]
    assert allv("di")==["53.100±0.015"]
    assert allv("a")==["7.2±0.025"]
    assert allv("Dd2")==["62.0"]
    assert allv("d2_Lower")==["-0.25"]
    assert allv("C_")==["15.5±0.025"]
    assert allv("Dcp")==["54±0.015"]
    expected=round(math.pi*8**3*7.8/6_000_000,5)
    assert allv("W04")==[format(expected,".15g")]
    assert allv("W07Z")==["0.02000"]
    assert allv("W")==[f"{.08+.05+.02+11*expected:.3f}"]
    assert allv("Cr")==["12.46"]
    assert allv("Cor")==["9.87"]
    assert allv("NO_FIELD")==[None]
    assert original["variables"][0]["value"] is None

def test_missing_legacy_groove_positions_stay_empty():
    r=apply_deep_groove_dimensions(report=report(["a","De","Ri"]),parameters=P)
    assert [row["value"] for row in r["variables"]] == [None,None,"4.20"]

def test_bad_values_rejected():
    with pytest.raises(DrawingDataError):
        apply_deep_groove_dimensions(report=report(["Cr"]),parameters=P,
                                   legacy_values={"dynamic_load_n":math.inf})
    with pytest.raises(DrawingDataError):
        apply_deep_groove_dimensions(report=report(["Cr"]),parameters=P,
                                   legacy_values="bad")

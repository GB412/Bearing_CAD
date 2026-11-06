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
           "W07","W07Z","W09","W09Z","W","Cr","Cor","NO_FIELD","Ri"]
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
    assert allv("W09")==[None]
    assert allv("W09Z")==[None]
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


def test_acb_lock_height_width_and_non_symmetric_cage():
    from bearing_cad.drawing_legacy_dimensions import apply_angular_contact_dimensions
    p={**P,"contact_angle_deg":25}
    names=["Ri","Re","De","di","a","ae","ai","Dd2","d2","t_SK",
           "t_SK_Upper","t_SK_Lower","T_","T_Lower","Dcp","C_",
           "Dc","Dc_Lower","Bc","Bca","Bca_Lower","Deltac",
           "Deltac_Upper","e_Upper","Cr","Cor","UNSET"]
    old={"inner_groove_d_mm":54,"outer_groove_d_mm":56,
         "inner_groove_position_mm":6,"outer_groove_position_mm":7,
         "inner_race_groove_position_mm":6.5,"outer_sidewall_d_mm":60,
         "inner_sidewall_d_mm":47,"lock_height_mm":.15,
         "cage_pitch_d_mm":54,"cage_pocket_spacing_mm":15,
         "cage_outer_d_mm":58,"cage_outer_d_tolerance_mm":.2,
         "cage_width_mm":10,"cage_width_tolerance_mm":.1,
         "cage_pocket_d_mm":8.5,"cage_pocket_d_upper_tolerance_mm":.05,
         "cage_chamfer_upper_text":"——","dynamic_load_n":12600,
         "static_load_n":12500}
    r=apply_angular_contact_dimensions(report=report(names),parameters=p,legacy_values=old)
    v={row["name"]:row["value"] for row in r["variables"]}
    assert v["Ri"]=="4.20"
    assert v["a"]=="6.0±0.03"  # RoBAS angular uses outside diameter.
    assert v["ae"]=="7±0.03"
    assert v["t_SK_Lower"]=="-0.02"
    assert v["T_Lower"]=="-0.3"
    assert v["Dcp"]=="54±0.015"
    assert v["C_"]=="15±0.05"
    assert v["Dc_Lower"]=="-0.2"
    assert v["Bca"]=="5"
    assert v["Bca_Lower"]=="-0.1"
    assert v["Deltac_Upper"]=="+0.05"  # original RoBAS text includes explicit +
    assert v["Cr"]=="12.60" and v["Cor"]=="12.50"
    assert v["e_Upper"] is None and v["UNSET"] is None

def test_acb_lock_height_breakpoints():
    from bearing_cad.drawing_legacy_dimensions import lock_height_deviation,acb_width_deviation
    assert lock_height_deviation(.07)=="-0.01"
    assert lock_height_deviation(.1)=="-0.015"
    assert lock_height_deviation(.29)=="-0.03"
    assert lock_height_deviation(.5)=="-0.05"
    assert acb_width_deviation(10)=="0.2"
    assert acb_width_deviation(40)=="0.3"
    assert acb_width_deviation(100)=="0.5"


def test_dgb_geometry_tolerances_use_original_public_getter_precision():
    # C# passes BearingInsideDia (0.01 mm) and BallRoller.BallDiameter
    # (0.001 mm) getters to its tolerance functions before formatting.
    p = {**P, "bore_d_mm": 30.004, "ball_d_mm": 6.0005,
         "inner_groove_radius_mm": 3.004, "outer_groove_radius_mm": 3.004}
    old = {
        "inner_groove_d_mm": 30.004,
        "outer_groove_d_mm": 30.004,
        "inner_groove_position_mm": 30.004,
        "outer_sidewall_d_mm": 30.004,
        "inner_sidewall_d_mm": 30.004,
    }
    result = apply_deep_groove_dimensions(
        report=report(["Ri", "Ri_Upper", "Re", "De", "di", "a",
                       "Dd2", "Dd2_Upper", "d2", "d2_Lower"]),
        parameters=p, legacy_values=old,
    )
    values = {row["name"]: row["value"] for row in result["variables"]}
    assert values["Ri"] == "3.00"
    assert values["Ri_Upper"] == "+0.03"
    assert values["Re"] == "3.00"
    assert values["De"] == "30.000±0.01"
    assert values["di"] == "30.000±0.01"
    assert values["a"] == "30.0±0.02"
    assert values["Dd2"] == "30.0"
    assert values["Dd2_Upper"] == "+0.21"
    assert values["d2_Lower"] == "-0.21"


def test_acb_width_and_position_tolerances_use_original_diameter_getters():
    from bearing_cad.drawing_legacy_dimensions import apply_angular_contact_dimensions
    p = {**P, "bore_d_mm": 10.004, "outside_d_mm": 50.005, "width_mm": 10.004,
         "contact_angle_deg": 25}
    old = {
        "inner_groove_d_mm": 50.005,
        "outer_groove_d_mm": 50.005,
        "inner_groove_position_mm": 50.005,
        "outer_groove_position_mm": 50.005,
        "inner_race_groove_position_mm": 50.005,
        "lock_height_mm": 0.104,
    }
    result = apply_angular_contact_dimensions(
        report=report(["De", "di", "a", "ae", "ai", "T_", "T_Lower",
                       "t_SK", "t_SK_Lower"]),
        parameters=p, legacy_values=old,
    )
    values = {row["name"]: row["value"] for row in result["variables"]}
    assert values["De"] == "50.000±0.01"
    assert values["di"] == "50.000±0.01"
    assert values["a"] == "50.0±0.025"
    assert values["ae"] == "50±0.025"
    assert values["ai"] == "50±0.025"
    assert values["T_"] == "10"
    assert values["T_Lower"] == "-0.2"
    assert values["t_SK"] == "0.1"
    assert values["t_SK_Lower"] == "-0.015"


def test_ball_mass_rounds_ball_diameter_public_getter_before_formula():
    # BallRoller.BallDiameter getter: 2.0465 mm -> 2.046 mm.
    # The unrounded source value would produce W04 4e-05, not 3e-05.
    params = {**P, "ball_d_mm": 2.0465, "ball_count": 2}
    r = apply_deep_groove_dimensions(
        report=report(["W04", "W04Z", "W09", "W09Z", "W16", "W46"]),
        parameters=params)
    values = {row["name"]: row["value"] for row in r["variables"]}
    assert values["W04"] == "3e-05"
    assert values["W04Z"] == "6e-05"
    assert all(values[name] is None for name in ("W09", "W09Z", "W16", "W46"))

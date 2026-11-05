"""RoBAS ACB 2D groove dimensions and literal lock-height source parity."""
import math
import pytest

from bearing_cad.drawing_legacy_acb_race import derive_acb_race_drawing_values
from bearing_cad.drawing_legacy_dimensions import apply_angular_contact_dimensions

P = {
 "bore_d_mm": 40., "outside_d_mm": 68., "width_mm": 15.,
 "pitch_d_mm": 54., "ball_d_mm": 8., "ball_count": 11,
 "inner_groove_radius_mm": 4.12, "outer_groove_radius_mm": 4.2,
 "contact_angle_deg": 25.,
 "inner_shoulder_left_d_mm": 49., "inner_shoulder_right_d_mm": 47.,
 "outer_shoulder_left_d_mm": 61., "outer_shoulder_right_d_mm": 59.,
}


def test_acb_source_race_matches_source_equations_and_signed_labels():
    values, evidence = derive_acb_race_drawing_values(P)
    alpha=math.radians(P["contact_angle_deg"])
    assert values["outer_groove_d_mm"] == round(54 + 2*4.2 - .4*math.cos(alpha), 2)
    assert values["inner_groove_d_mm"] == round(54 - 2*4.12 + .24*math.cos(alpha), 2)
    assert values["inner_groove_position_mm"] == round(7.5 + .12*math.sin(alpha), 2)
    assert values["outer_groove_position_mm"] == round(7.5 + .2*math.sin(alpha), 2)
    assert values["inner_race_groove_position_mm"] == values["inner_groove_position_mm"]
    assert values["lock_height_mm"] == .02
    assert evidence["warnings"]

    fields=["De","di","a","ae","ai","t_SK","t_SK_Upper","t_SK_Lower"]
    report={"schema_version":"robas.drawing.variables.v1","variables":[
        {"name":k,"value":None,"row_index":i,"source":"sqlite_default"}
        for i,k in enumerate(fields)]}
    output=apply_angular_contact_dimensions(report=report,parameters=P,legacy_values=values)
    names={row["name"]:row["value"] for row in output["variables"]}
    assert names["De"] == "62.040±0.015"
    assert names["di"] == "45.980±0.015"
    assert names["a"] == f'{values["inner_groove_position_mm"]:.1f}±0.03'
    assert names["ae"] == str(values["outer_groove_position_mm"])+"±0.03"
    assert names["ai"] == str(values["inner_groove_position_mm"])+"±0.03"
    assert names["t_SK"] == "0.02"
    assert names["t_SK_Upper"] == "0"
    assert names["t_SK_Lower"] == "-0.01"


@pytest.mark.parametrize("angle", [15.,25.,40.])
def test_acb_original_source_profile_angles(angle):
    values, evidence=derive_acb_race_drawing_values(
        {**P, "contact_angle_deg":angle})
    assert values["outer_groove_d_mm"] > values["inner_groove_d_mm"]
    assert values["inner_groove_position_mm"] >= 7.5
    assert "ACB_CUSTOM_CURVATURE_NOT_ORIGINAL_ROBAS_PROFILE" not in evidence["warnings"]


def test_different_acb_curvature_is_not_mislabeled_as_original_profile():
    values, evidence=derive_acb_race_drawing_values(
        {**P, "inner_groove_radius_mm":4.14})
    assert values == {}
    assert "ACB_CUSTOM_CURVATURE_NOT_ORIGINAL_ROBAS_PROFILE" in evidence["warnings"]

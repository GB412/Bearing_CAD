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


def test_original_acb_shoulder_labels_only_when_actual_cad_geometry_matches():
    angle = math.radians(P["contact_angle_deg"])
    dw = P["ball_d_mm"]
    de = P["pitch_d_mm"] + 2*P["outer_groove_radius_mm"] - (
        2*P["outer_groove_radius_mm"] - dw) * math.cos(angle)
    di = P["pitch_d_mm"] - 2*P["inner_groove_radius_mm"] + (
        2*P["inner_groove_radius_mm"] - dw) * math.cos(angle)
    # Original ACBGeometry and 3D race constructors use .40*Dw when d>25.
    matched = {
        **P, "outer_shoulder_right_d_mm": round(de - .40*dw, 2),
        "inner_shoulder_left_d_mm": round(di + .40*dw, 2),
    }
    values, evidence = derive_acb_race_drawing_values(matched)
    assert values["outer_sidewall_d_mm"] == matched["outer_shoulder_right_d_mm"]
    assert values["inner_sidewall_d_mm"] == matched["inner_shoulder_left_d_mm"]
    assert not any("DIFFERS_FROM_ROBAS_SOURCE" in w for w in evidence["warnings"])

    report = {"schema_version": "robas.drawing.variables.v1", "variables": [
        {"name": k, "value": None, "source": "sqlite_default", "row_index": i}
        for i,k in enumerate(["Dd2", "Dd2_Upper", "Dd2_Lower",
                              "d2", "d2_Upper", "d2_Lower"])
    ]}
    filled = apply_angular_contact_dimensions(
        report=report, parameters=matched, legacy_values=values)
    fields = {row["name"]: row["value"] for row in filled["variables"]}
    assert fields["Dd2"] == f'{matched["outer_shoulder_right_d_mm"]:.1f}'
    assert fields["d2"] == f'{matched["inner_shoulder_left_d_mm"]:.1f}'
    assert fields["Dd2_Upper"].startswith("+")
    assert fields["d2_Upper"] == "0"

    # The standard UI example has deliberately different shoulder sizes;
    # source-derived old-model text must not be attached to that 3D model.
    custom, warnings = derive_acb_race_drawing_values(P)
    assert "outer_sidewall_d_mm" not in custom
    assert "inner_sidewall_d_mm" not in custom
    assert any("DIFFERS_FROM_ROBAS_SOURCE" in w for w in warnings["warnings"])


def test_original_acb_small_bore_shoulder_coefficient_035():
    # The original source switches from 0.35*Dw to 0.40*Dw at d=25 mm.
    small = {**P, "bore_d_mm": 25.0}
    alpha = math.radians(small["contact_angle_deg"])
    dw = small["ball_d_mm"]
    de = (small["pitch_d_mm"] + 2*small["outer_groove_radius_mm"]
          - (2*small["outer_groove_radius_mm"] - dw) * math.cos(alpha))
    di = (small["pitch_d_mm"] - 2*small["inner_groove_radius_mm"]
          + (2*small["inner_groove_radius_mm"] - dw) * math.cos(alpha))
    matched = {
        **small, "outer_shoulder_right_d_mm": round(de - .35*dw, 2),
        "inner_shoulder_left_d_mm": round(di + .35*dw, 2),
    }
    values, evidence = derive_acb_race_drawing_values(matched)
    assert values["outer_sidewall_d_mm"] == matched["outer_shoulder_right_d_mm"]
    assert values["inner_sidewall_d_mm"] == matched["inner_shoulder_left_d_mm"]
    assert not any("DIFFERS_FROM_ROBAS_SOURCE" in w for w in evidence["warnings"])


def test_custom_acb_shoulder_not_replaced_even_if_legacy_groove_matches():
    # Explicitly chosen OCCT shoulder geometry remains the source of truth;
    # a different historical RoBAS shoulder is not a manufactured tolerance.
    values, evidence = derive_acb_race_drawing_values(P)
    assert "outer_sidewall_d_mm" not in values
    assert "inner_sidewall_d_mm" not in values
    assert any("DIFFERS_FROM_ROBAS_SOURCE" in w for w in evidence["warnings"])

 
def test_acb_lock_height_uses_original_diameter_and_ball_getters():
    params = {
        **P,
        "bore_d_mm": 30.004,
        "ball_d_mm": 8.0005,
        "inner_groove_radius_mm": .515 * 8.0005,
        "outer_groove_radius_mm": .525 * 8.0005,
    }
    values, evidence = derive_acb_race_drawing_values(params)
    assert values["lock_height_mm"] == 0.03
    assert "ACB_SOURCE_LOCK_HEIGHT_LITERAL_THERMAL_CONSTANT_UNREVIEWED" in evidence["warnings"]

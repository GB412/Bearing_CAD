"""RoBAS DGB engineering labels: original equations with explicit provenance."""
import math

import pytest

from bearing_cad.contracts import StampedCageSpec
from bearing_cad.drawing_legacy_design import (
    derive_dgb_drawing_values, dgb_radial_clearance_mm,
    _race_weights,
)
from bearing_cad.drawing_legacy_dimensions import apply_deep_groove_dimensions


P = {
    "bore_d_mm": 40.0, "outside_d_mm": 68.0, "width_mm": 15.0,
    "pitch_d_mm": 54.0, "ball_d_mm": 8.0, "ball_count": 11,
    "inner_shoulder_d_mm": 47.2, "outer_shoulder_d_mm": 60.8,
    "inner_groove_radius_mm": 4.08, "outer_groove_radius_mm": 4.24,
}


def cage():
    return StampedCageSpec(
        kind="stamping_double_half", inner_d_mm=48,
        outside_d_mm=60, width_mm=11.5, pocket_clearance_mm=.15,
        board_thickness_mm=.7, rivet_shaft_d_mm=1,
        rivet_head_d_mm=1.6, rivet_hole_clearance_mm=.05,
    )


def _report(keys):
    return {
        "schema_version": "robas.drawing.variables.v1",
        "variables": [
            {"name": name, "value": None, "source": "sqlite_default",
             "row_index": i} for i, name in enumerate(keys)
        ],
    }


def test_dgb_geometry_follows_original_formula_at_nominal_bore():
    values, evidence = derive_dgb_drawing_values(parameters=P)
    assert values["inner_groove_d_mm"] == 46
    assert values["inner_groove_position_mm"] == 7.5
    assert values["outer_groove_d_mm"] == pytest.approx(62.013)
    assert "cage_pitch_d_mm" not in values
    assert "STAMPING_CAGE_DIMENSIONS_NOT_AVAILABLE_FOR_SELECTED_CAGE" in evidence["warnings"]
    assert dgb_radial_clearance_mm(40) == pytest.approx(.013)
    # C# integer division, not mathematical average: (4+11)/2 = 7.
    assert dgb_radial_clearance_mm(10) == pytest.approx(.007)
    assert dgb_radial_clearance_mm(18) == pytest.approx(.008)
    assert dgb_radial_clearance_mm(160) == pytest.approx(.037)
    assert dgb_radial_clearance_mm(199.9) == pytest.approx(.044)
    assert dgb_radial_clearance_mm(200) is None


def test_explicit_other_clearance_does_not_silently_use_robas_c0_diameter():
    values, evidence = derive_dgb_drawing_values(
        parameters=P, radial_clearance_group="C3")
    assert "outer_groove_d_mm" not in values
    assert "DGB_OUTER_GROOVE_NEEDS_SOURCE_C0_CLEARANCE" in evidence["warnings"]


def test_stamped_3d_cage_dimensions_fill_existing_dgb_robas_drawing_fields():
    values, evidence = derive_dgb_drawing_values(parameters=P, cage=cage())
    assert values["cage_pitch_d_mm"] == 54
    assert values["cage_pitch_tolerance_mm"] == .025
    assert values["cage_outer_tolerance_mm"] == .09
    assert values["cage_inner_tolerance_mm"] == .08
    assert values["cage_board_thickness_mm"] == .7
    assert values["cage_sphere_radius_mm"] == pytest.approx(4.15)
    assert values["cage_pocket_spacing_mm"] == pytest.approx(
        54 * math.sin(math.pi / 11))
    assert values["cage_pocket_rivet_spacing_mm"] == pytest.approx(
        54 * math.sin(math.pi / 22))
    assert values["cage_rivet_hole_d_mm"] == pytest.approx(1.1)
    assert values["rivet_hole_upper_tolerance_mm"] == pytest.approx(.15)
    assert values["rivet_hole_lower_tolerance_mm"] == pytest.approx(.08)
    assert values["half_cage_weight_kg"] > 0
    assert evidence["mass_basis"].startswith("RoBAS empirical")

    keys = [
        "De", "di", "a", "C_", "C1_", "Dcp", "Dc", "Dc1",
        "S_", "Rc", "Rc_Upper", "Rc_Lower", "tc", "tc_Upper",
        "tc_Lower", "W07", "W07Z", "W", "K_", "rrc"
    ]
    report = apply_deep_groove_dimensions(
        report=_report(keys), parameters=P, legacy_values=values)
    fields = {row["name"]: row["value"] for row in report["variables"]}
    assert fields["De"] == "62.013±0.015"
    assert fields["di"] == "46.000±0.015"
    assert fields["a"] == "7.5±0.025"
    assert fields["Dcp"] == "54±0.025"
    assert fields["Dc"] == "60±0.09"
    assert fields["Dc1"] == "48±0.08"
    assert fields["Rc"] == "4.15"
    assert fields["tc"] == "1.1"
    assert fields["W07Z"]
    assert fields["W"] is None  # no trustworthy inner and outer ring masses yet
    assert fields["K_"] is None and fields["rrc"] is None


def test_robas_ring_mass_equations_need_provided_valid_chamfer():
    chamfer = [""] * 20
    chamfer[2], chamfer[11] = "0.4", "0.2max"
    weights = _race_weights(P, di=46, de=62.013, chamfer=chamfer)
    assert weights["outer_race_weight_kg"] == pytest.approx(.07368767025739394)
    assert weights["inner_race_weight_kg"] == pytest.approx(.04985741907035138)
    chamfer[11] = ""
    assert _race_weights(P, di=46, de=62.013, chamfer=chamfer) == {}


def test_invalid_unsupported_dimensions_fail_without_fabricating_values():
    with pytest.raises(ValueError):
        derive_dgb_drawing_values(parameters={**P, "ball_count": 0})
    with pytest.raises(ValueError):
        derive_dgb_drawing_values(parameters={**P, "ball_d_mm": 100})

def test_exact_robas_stamping_adapter_can_fill_pocket_depth_and_flat_radius():
    from bearing_cad.robas_stamping import robas_stamping_profile
    model = "6008"
    source = robas_stamping_profile(
        bearing_model=model, ball_d_mm=P["ball_d_mm"],
        pitch_d_mm=P["pitch_d_mm"], ball_count=P["ball_count"],
        bearing_width_mm=P["width_mm"],
        inner_shoulder_d_mm=P["inner_shoulder_d_mm"],
        outer_shoulder_d_mm=P["outer_shoulder_d_mm"],
        rivet_hole_clearance_mm=.05,
    )
    cage_spec = StampedCageSpec(**source["cad_cage"])
    values, evidence = derive_dgb_drawing_values(
        parameters=P, cage=cage_spec, bearing_model=model)
    assert values["cage_pocket_depth_mm"] == pytest.approx(4.04)
    assert values["cage_flat_to_sphere_radius_mm"] == pytest.approx(
        source["source_dimensions"]["flat_to_sphere_radius_mm"])
    checked = apply_deep_groove_dimensions(
        report=_report(["K_", "K_Upper", "K_Lower", "rrc"]),
        parameters=P, legacy_values=values)
    fields = {row["name"]:row["value"] for row in checked["variables"]}
    assert float(fields["K_"]) == pytest.approx(4.04)
    assert fields["K_Upper"] == "+0.04"
    assert fields["K_Lower"] == "0"
    assert float(fields["rrc"]) > 0
    assert "ROBAS_STAMPING_NOMINAL_POCKET_PROFILE_REQUIRES_3D_REVIEW" in evidence["warnings"]


def test_custom_stamped_cage_does_not_claim_robas_source_pocket_geometry():
    from bearing_cad.robas_stamping import robas_stamping_profile
    source = robas_stamping_profile(
        bearing_model="6008", ball_d_mm=P["ball_d_mm"],
        pitch_d_mm=P["pitch_d_mm"], ball_count=P["ball_count"],
        bearing_width_mm=P["width_mm"],
        inner_shoulder_d_mm=P["inner_shoulder_d_mm"],
        outer_shoulder_d_mm=P["outer_shoulder_d_mm"],
        rivet_hole_clearance_mm=.05,
    )
    original = source["cad_cage"]
    changed = {**original, "rivet_head_d_mm": original["rivet_head_d_mm"]+.1}
    values, warnings = derive_dgb_drawing_values(
        parameters=P, cage=StampedCageSpec(**changed), bearing_model="6008")
    assert "cage_pocket_depth_mm" not in values
    assert "cage_flat_to_sphere_radius_mm" not in values
    assert "STAMPING_CAGE_DIFFERS_FROM_ORIGINAL_SOURCE_PROFILE" in warnings["warnings"]



def test_original_dgb_shoulder_source_reference_and_checked_cad_match():
    # Source: DGBGeometry.cs lines 68-91, BallGeometry getters use round(..., 2).
    # The 40-mm bore selects 0.40*Dw. With original C0 clearance,
    # d2=46+3.2=49.2 and Dd2=round(62.013-3.2, 2)=58.81.
    original_profile = {
        **P, "inner_shoulder_d_mm": 49.20, "outer_shoulder_d_mm": 58.81,
    }
    values, evidence = derive_dgb_drawing_values(parameters=original_profile)
    assert values["inner_sidewall_d_mm"] == 49.2
    assert values["outer_sidewall_d_mm"] == 58.81
    assert evidence["original_source_shoulder_mm"] == {
        "d2": 49.2, "Dd2": 58.81,
    }
    assert evidence["original_source_shoulder_matches_cad"] == {
        "d2": True, "Dd2": True,
    }
    report = apply_deep_groove_dimensions(
        report=_report(["Dd2", "Dd2_Upper", "Dd2_Lower",
                        "d2", "d2_Upper", "d2_Lower"]),
        parameters=original_profile,
        legacy_values=values,
    )
    labels = {row["name"]: row["value"] for row in report["variables"]}
    assert labels == {
        "Dd2": "58.8", "Dd2_Upper": "+0.25", "Dd2_Lower": "0",
        "d2": "49.2", "d2_Upper": "0", "d2_Lower": "-0.25",
    }


def test_custom_dgb_cad_shoulders_stay_true_to_actual_model_with_source_warning():
    # The UI demo uses different actual B-Rep shoulders. Do not substitute
    # RoBAS defaults just to reduce unresolved variable counts.
    values, evidence = derive_dgb_drawing_values(parameters=P)
    assert "inner_sidewall_d_mm" not in values
    assert "outer_sidewall_d_mm" not in values
    assert evidence["original_source_shoulder_mm"] == {
        "d2": 49.2, "Dd2": 58.81,
    }
    assert evidence["original_source_shoulder_matches_cad"] == {
        "d2": False, "Dd2": False,
    }
    assert "DGB_D2_DIFFERS_FROM_ORIGINAL_ROBAS_SOURCE" in evidence["warnings"]
    assert "DGB_DD2_DIFFERS_FROM_ORIGINAL_ROBAS_SOURCE" in evidence["warnings"]
    r = apply_deep_groove_dimensions(
        report=_report(["Dd2", "d2"]), parameters=P, legacy_values=values)
    assert [row["value"] for row in r["variables"]] == ["60.8", "47.2"]


def test_dgb_original_source_shoulder_035_boundary_and_custom_pitch():
    # d=25 mm selects 0.35*Dw, while d>25 uses 0.40*Dw.
    small = {**P, "bore_d_mm": 25.0, "outside_d_mm": 75.0,
             "pitch_d_mm": 50.0, "ball_d_mm": 8.0}
    values, e = derive_dgb_drawing_values(parameters=small)
    assert e["original_source_shoulder_mm"]["d2"] == 44.8
    assert "inner_sidewall_d_mm" not in values

    custom = {**P, "pitch_d_mm": 55.0}
    values, e = derive_dgb_drawing_values(parameters=custom)
    assert e["original_source_shoulder_mm"] == {}
    assert e["original_source_shoulder_matches_cad"] == {}
    assert "DGB_CUSTOM_PITCH_NOT_ORIGINAL_ROBAS_GEOMETRY" in e["warnings"]
    assert "inner_sidewall_d_mm" not in values


def test_dgb_non_c0_clearance_does_not_claim_original_outer_shoulder():
    values, e = derive_dgb_drawing_values(
        parameters=P, radial_clearance_group="C3")
    assert "Dd2" not in e["original_source_shoulder_mm"]
    assert "outer_sidewall_d_mm" not in values
    assert "d2" in e["original_source_shoulder_mm"]
    assert "DGB_OUTER_GROOVE_NEEDS_SOURCE_C0_CLEARANCE" in e["warnings"]

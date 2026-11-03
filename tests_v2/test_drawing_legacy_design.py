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

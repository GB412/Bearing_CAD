"""Original RoBAS ACB straight-pocket cage dimensions in the 2D data path."""
import math
import pytest
from bearing_cad.contracts import CageSpec
from bearing_cad.drawing_legacy_acb_cage import (
    derive_acb_cage_drawing_values, _outside_tolerance, _width_tolerance,
)
from bearing_cad.drawing_legacy_dimensions import apply_angular_contact_dimensions


PARAMS = {
    "bore_d_mm": 40., "outside_d_mm": 68., "width_mm": 15.,
    "pitch_d_mm": 54., "ball_d_mm": 8., "ball_count": 11,
    "inner_groove_radius_mm": 4.12, "outer_groove_radius_mm": 4.2,
    "inner_shoulder_left_d_mm": 49., "inner_shoulder_right_d_mm": 47.,
    "outer_shoulder_left_d_mm": 61., "outer_shoulder_right_d_mm": 59.,
}


def cage(**kwargs):
    args = dict(kind="straight_pocket", inner_d_mm=51., outside_d_mm=57.,
                width_mm=11., pocket_clearance_mm=.15)
    args.update(kwargs)
    return CageSpec(**args)


def report(names):
    return {"schema_version": "robas.drawing.variables.v1", "variables": [
        {"name": key, "value": None, "row_index": i, "source": "sqlite_default"}
        for i, key in enumerate(names)]}


def test_acb_cage_derives_actual_geometry_and_original_tolerances():
    values, evidence = derive_acb_cage_drawing_values(parameters=PARAMS, cage=cage())
    assert values["cage_pitch_d_mm"] == 54.
    assert values["cage_pocket_spacing_mm"] == pytest.approx(57*math.sin(math.pi/11))
    assert values["cage_pocket_d_mm"] == pytest.approx(8.3)
    assert values["cage_outer_d_tolerance_mm"] == .074
    assert values["cage_inner_d_tolerance_mm"] == .074
    assert values["cage_width_tolerance_mm"] == .110
    assert values["cage_pocket_d_upper_tolerance_mm"] == .1
    assert "cage_chamfer_mm" not in values
    assert "ACB_CAGE_CHAMFER_NOT_PRESENT_IN_OCCT_CAGE" in evidence["warnings"]

    keys = ["Dcp","C_","Dc","Dc_Upper","Dc_Lower","Dc1","Dc1_Upper",
            "Dc1_Lower","Deltac","Deltac_Upper","Deltac_Lower",
            "Bc","Bc_Upper","Bc_Lower","Bca","Bca_Upper","Bca_Lower","e_"]
    output = apply_angular_contact_dimensions(
        report=report(keys), parameters=PARAMS, legacy_values=values)
    result = {item["name"]:item["value"] for item in output["variables"]}
    assert result["Dcp"] == "54±0.015"
    assert result["Dc"] == "57" and result["Dc_Lower"] == "-0.074"
    assert result["Dc1"] == "51" and result["Dc1_Lower"] == "-0.074"
    assert result["Deltac_Upper"] == "+0.1" and result["Deltac_Lower"] == "0"
    assert result["Bc"] == "11" and result["Bc_Lower"] == "-0.11"
    assert result["Bca"] == "5.5"
    assert result["e_"] is None


def test_acb_missing_cage_is_not_replaced_with_legacy_constructor_defaults():
    values, ev = derive_acb_cage_drawing_values(parameters=PARAMS, cage=None)
    assert values == {}
    assert ev["warnings"] == ["ACB_STRAIGHT_POCKET_CAGE_NOT_SELECTED"]


@pytest.mark.parametrize("diameter, expected", [
    (10, None),(18,.043),(18.01,.052),(30,.052),(50,.062),
    (80,.074),(120,.087),(180,.100),(250,.115),(250.01,None)
])
def test_source_outside_diameter_tolerance_boundaries(diameter, expected):
    assert _outside_tolerance(diameter) == expected


@pytest.mark.parametrize("width, expected", [
    (10,.090),(10.01,.110),(18,.110),(30,.130),
    (50,.160),(80,.190),(80.01,None)
])
def test_source_width_tolerance_boundaries(width, expected):
    assert _width_tolerance(width) == expected


def test_outside_original_range_does_not_fabricate_zero_tolerance():
    values, evidence = derive_acb_cage_drawing_values(
        parameters=PARAMS, cage=cage(outside_d_mm=290))
    assert "cage_outer_d_tolerance_mm" not in values
    assert "ACB_CAGE_OUTER_TOLERANCE_UNDEFINED_IN_ROBAS" in evidence["warnings"]

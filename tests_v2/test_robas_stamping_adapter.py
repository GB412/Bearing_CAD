"""RoBAS StampingCage original source equations and CAD adapter acceptance."""
import math
from copy import deepcopy

import pytest

from bearing_cad.robas_stamping import robas_stamping_profile
from bearing_cad.contracts import parse_request
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.geometry_checks import inspect_solid, interference_volume
from test_contracts import deep_request


def _profile(**override):
    args = {
        "bearing_model": "6008", "ball_d_mm": 8.33438,
        "pitch_d_mm": 54, "ball_count": 11, "bearing_width_mm": 15,
        "inner_shoulder_d_mm": 48.999372,
        "outer_shoulder_d_mm": 59.013628,
        "rivet_hole_clearance_mm": 0.05,
    }
    args.update(override)
    return robas_stamping_profile(**args)


def test_6008_source_dimensions_and_width_semantics():
    p = _profile()
    c, source = p["cad_cage"], p["source_dimensions"]
    assert p["candidate_only"]
    assert c["kind"] == "stamping_double_half"
    assert source["width_radial_mm"] == pytest.approx(3.750471)
    assert c["inner_d_mm"] == pytest.approx(50.249529)
    assert c["outside_d_mm"] == pytest.approx(57.750471)
    assert source["board_thickness_mm"] == pytest.approx(0.7)
    assert source["sphere_radius_mm"] == pytest.approx(4.583909)
    assert source["half_cage_axial_height_mm"] == pytest.approx(5.283909)
    assert c["width_mm"] == pytest.approx(10.567818)
    assert c["pocket_clearance_mm"] == pytest.approx(0.416719)
    assert c["rivet_shaft_d_mm"] == 1.0
    assert c["rivet_head_d_mm"] == 1.6
    assert source["pocket_depth_mm"] == pytest.approx(4.20719)
    assert source["pocket_to_pocket_mm"] == pytest.approx(54 * math.sin(math.pi / 11))
    assert source["pocket_to_rivet_mm"] == pytest.approx(54 * math.sin(math.pi / 22))


def test_source_board_thickness_series_and_large_60_width():
    for family, board, hole, head in [
        ("6008", 0.7, 1.0, 1.6),
        ("6208", 1.0, 1.2, 1.9),
        ("6308", 0.7, 1.0, 1.6),
    ]:
        p = _profile(bearing_model=family)
        assert p["cad_cage"]["board_thickness_mm"] == board
        assert p["cad_cage"]["rivet_shaft_d_mm"] == hole
        assert p["cad_cage"]["rivet_head_d_mm"] == head
    # Original 60-series Kc=0.48 above Dw=20 (independent of ring feasibility).
    with pytest.raises(ValueError, match="fit"):
        _profile(ball_d_mm=21)


def test_invalid_source_and_cad_dimensions_fail_closed():
    for overrides, message in [
        ({"bearing_model": "6408"}, "series"),
        ({"bearing_model": "6208", "ball_d_mm": 46}, "not defined"),
        ({"bearing_model": "6008", "ball_d_mm": 4}, "not defined"),
        ({"ball_count": 0}, "ball_count"),
        ({"ball_count": True}, "ball_count"),
        ({"rivet_hole_clearance_mm": -0.1}, "positive"),
        ({"rivet_hole_clearance_mm": 0.5}, "retained rivet"),
        ({"bearing_width_mm": 10}, "axial envelope"),
        ({"outer_shoulder_d_mm": 57}, "fit"),
    ]:
        with pytest.raises(ValueError, match=message):
            _profile(**overrides)


def test_original_6008_cage_adapts_to_real_occt_brep():
    profile = _profile()
    data = deep_request()
    data["parameters"].update({
        "ball_d_mm": 8.33438,
        "pitch_d_mm": 54,
        "ball_count": 11,
        "inner_groove_radius_mm": 0.51 * 8.33438,
        "outer_groove_radius_mm": 0.53 * 8.33438,
        "inner_shoulder_d_mm": 48.999372,
        "outer_shoulder_d_mm": 59.013628,
    })
    data["cage"] = profile["cad_cage"]
    request = parse_request(data)
    model = build_deep_groove(request)
    assert len(model.instances) == 26
    parts = {part.component_id: part.shape for part in model.components}
    assert set(parts) == {"inner_ring", "outer_ring", "ball", "cage_upper", "cage_lower", "rivet"}
    assert all(inspect_solid(shape).valid for shape in parts.values())
    assert parts["cage_upper"].BoundingBox().zmax == pytest.approx(
        profile["source_dimensions"]["half_cage_axial_height_mm"], abs=1e-5)
    assert interference_volume(parts["cage_upper"], parts["cage_lower"]) < 1e-6


def test_existing_explicit_stamping_contract_remains_unchanged():
    data = deep_request()
    data["cage"] = {
        "kind": "stamping_double_half", "inner_d_mm": 48, "outside_d_mm": 60,
        "width_mm": 11.5, "pocket_clearance_mm": 0.15,
        "board_thickness_mm": 0.7, "rivet_shaft_d_mm": 1,
        "rivet_head_d_mm": 1.6, "rivet_hole_clearance_mm": 0.05,
    }
    canonical = parse_request(deepcopy(data)).canonical_json()
    assert parse_request(data).canonical_json() == canonical

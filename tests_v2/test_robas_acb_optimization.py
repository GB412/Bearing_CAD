"""RoBAS ACBOptimizer source formulas, input boundary and candidate nonmutation."""
import csv
import math

import pytest

from bearing_cad.contracts import parse_request
from bearing_cad.robas_acb_optimization import (
    _ball_count, _candidate_geometry, _source_bounds, optimize_acb_candidates,
)
from bearing_cad.robas_optimization import OptimizationError

INITIAL = {
    "bearing_type": "rolling.angular_contact_ball",
    "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
    "contact_angle_deg": 25, "cage_material": "engineering_plastic",
    "cage": None,
}
OPTIONS = {
    "model": "7008", "accuracy_class": "P5", "preload_n": 100,
    "weights": {"spin_ratio": .3, "axial_stiffness": .3, "dynamic_load": .4},
}


@pytest.fixture
def acb_resources(tmp_path):
    root = tmp_path / "RoBAS_Resources"
    resource = root / "Resource"
    resource.mkdir(parents=True)
    (resource / "BallDB.csv").write_text(
        "diameter(mm)\n7.9375\n8.0\n8.33438\n8.5\n8.73125\n9\n",
        encoding="utf-8")
    with (resource / "球轴承零件相关系数.csv").open(
            "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Dw/Dpw", "fc", "fo"))
        for n in range(10, 20):
            writer.writerow((n / 100, 50 + n, 14 + n / 10))
    return root


def test_original_acb_source_material_ball_count_and_coefficients():
    assert _ball_count(8, 54, "engineering_plastic") == int(
        math.pi * 54 / ((1.01 + 1.5/8) * 8))
    assert _ball_count(8, 54, "phenolic") == int(
        math.pi * 54 / ((1.01 + 1.9/8) * 8))
    assert _ball_count(8, 54, "engineering_plastic") > _ball_count(
        8, 54, "phenolic")
    assert _source_bounds("7008", 40, 25) == (.30, .32, .35, .35)
    assert _source_bounds("7208", 40, 25) == (.30, .32, .40, .40)
    assert _source_bounds("7208", 40, 40) == (.30, .32, .65, .60)
    assert _source_bounds("7308", 40, 25) == (.30, .33, .40, .40)
    with pytest.raises(OptimizationError, match="d>120"):
        _source_bounds("7308", 150, 25)


def test_acb_candidates_are_valid_complete_cad_requests_and_do_not_apply(acb_resources):
    incoming = {**INITIAL}
    opts = {**OPTIONS, "weights": dict(OPTIONS["weights"])}
    response = optimize_acb_candidates(
        resources=acb_resources, initial=incoming, optimization=opts)
    assert incoming == INITIAL
    assert response["schema_version"] == "bearing-cad.robas-acb-optimization.v1"
    assert response["applied"] is False and response["candidate_only"] is True
    assert 1 <= len(response["candidates"]) <= 5
    assert response["total_valid_candidates"] >= len(response["candidates"])
    assert [x["rank"] for x in response["candidates"]] == list(
        range(1, len(response["candidates"]) + 1))
    assert [x["score"] for x in response["candidates"]] == sorted(
        [x["score"] for x in response["candidates"]], reverse=True)
    assert "SOURCE_ACB_MODEL_CATALOG_EMPTY_NO_MODEL_DIMENSION_CERTIFICATION" in response["warnings"]
    assert "SOURCE_OPTIMIZER_MAXIMIZES_SPIN_RATIO_ENGINEERING_DIRECTION_UNREVIEWED" in response["warnings"]
    for candidate in response["candidates"]:
        checked = parse_request(candidate["design"])
        assert checked.bearing_type.value == INITIAL["bearing_type"]
        p = checked.parameters
        assert p["contact_angle_deg"] == 25
        assert p["cage_material"] == "engineering_plastic"
        assert p["bore_d_mm"] == 40 and p["outside_d_mm"] == 68
        assert p["inner_shoulder_right_d_mm"] < p["inner_shoulder_left_d_mm"]
        assert p["outer_shoulder_right_d_mm"] < p["outer_shoulder_left_d_mm"]
        assert checked.cage is None
        a=math.radians(25)
        gamma = round(p["ball_d_mm"]*math.cos(a)/p["pitch_d_mm"], 2)
        assert candidate["coefficient_lookup"]["gamma"] == pytest.approx(gamma)
        assert candidate["metrics"]["dynamic_load_n"] > 0
        assert candidate["metrics"]["static_load_n"] > 0
        assert candidate["metrics"]["axial_stiffness_source_units"] > 0
        z,b,fc=p["ball_count"],p["ball_d_mm"],candidate["coefficient_lookup"]["fc"]
        cr=1.3*fc*math.cos(a)**.7*z**(2/3)*b**1.8
        assert candidate["metrics"]["dynamic_load_n"] == pytest.approx(cr)
        ka=3.43*(z*z*b*math.sin(a)**5)**(1/3)*100**(1/3)
        assert candidate["metrics"]["axial_stiffness_source_units"] == pytest.approx(ka)


def test_preload_changes_axial_stiffness_by_source_cube_root(acb_resources):
    first = optimize_acb_candidates(resources=acb_resources,initial=INITIAL,
                                    optimization=OPTIONS)
    second = optimize_acb_candidates(
        resources=acb_resources,initial=INITIAL,
        optimization={**OPTIONS,"preload_n":800})
    metrics1={tuple((x["design"]["parameters"][k] for k in (
        "ball_d_mm","ball_count","pitch_d_mm"))):x["metrics"]
        for x in first["candidates"]}
    for x in second["candidates"]:
        key=tuple(x["design"]["parameters"][k] for k in (
            "ball_d_mm","ball_count","pitch_d_mm"))
        if key in metrics1:
            assert x["metrics"]["axial_stiffness_source_units"] == pytest.approx(
                2*metrics1[key]["axial_stiffness_source_units"])
            return
    pytest.fail("Expected at least one candidate common to both preloads")


def test_material_changes_initial_ball_count_and_candidate_space(acb_resources):
    plastic=optimize_acb_candidates(resources=acb_resources,initial=INITIAL,
                                    optimization=OPTIONS)
    phenolic=optimize_acb_candidates(
        resources=acb_resources,initial={**INITIAL,"cage_material":"phenolic"},
        optimization=OPTIONS)
    assert plastic["source_initial_hash"] != phenolic["source_initial_hash"]
    assert phenolic["candidates"][0]["design"]["parameters"]["cage_material"] == "phenolic"


@pytest.mark.parametrize("invalid", [
    {**INITIAL, "contact_angle_deg": 0},
    {**INITIAL, "contact_angle_deg": 30},
    {**INITIAL, "cage_material": "unknown"},
    {**INITIAL, "cage": {"kind":"straight_pocket"}},
    {**INITIAL, "bore_d_mm":40, "outside_d_mm":39},
    {**INITIAL, "unexpected":1},
    {**INITIAL, "width_mm":False},
])
def test_acb_initial_inputs_fail_closed(acb_resources,invalid):
    with pytest.raises(OptimizationError):
        optimize_acb_candidates(
            resources=acb_resources,initial=invalid,optimization=OPTIONS)


@pytest.mark.parametrize("invalid", [
    {**OPTIONS, "model":"6008"},
    {**OPTIONS, "model":"7408"},
    {**OPTIONS, "preload_n": 0},
    {**OPTIONS, "accuracy_class":"INVALID"},
    {**OPTIONS, "weights":{"spin_ratio":.3,"axial_stiffness":.4,"dynamic_load":.4}},
    {**OPTIONS, "weights":{"spin_ratio":True,"axial_stiffness":0,"dynamic_load":0}},
])
def test_acb_optimization_options_fail_closed(acb_resources,invalid):
    with pytest.raises(OptimizationError):
        optimize_acb_candidates(
            resources=acb_resources,initial=INITIAL,optimization=invalid)


def test_unknown_source_coefficient_must_not_be_faked(acb_resources):
    path=acb_resources/"Resource"/"球轴承零件相关系数.csv"
    path.write_text("Dw/Dpw,fc,fo\n0.99,12,15\n",encoding="utf-8")
    with pytest.raises(OptimizationError, match="No ACB candidate"):
        optimize_acb_candidates(resources=acb_resources,
                                initial=INITIAL,optimization=OPTIONS)


def test_source_acb_requires_minimal_input_no_existing_3d_fields(acb_resources):
    assert set(INITIAL) == {
        "bearing_type","bore_d_mm","outside_d_mm","width_mm",
        "contact_angle_deg","cage_material","cage"}
    result=optimize_acb_candidates(resources=acb_resources,
                                   initial=INITIAL,optimization=OPTIONS)
    assert all("inner_shoulder_left_d_mm" in x["design"]["parameters"]
               for x in result["candidates"])


def test_adapted_acb_shoulders_are_explicitly_not_exact_legacy_dimensions():
    result = _candidate_geometry(INITIAL, 8.33438, 17, 54, .35, .35)
    assert result is not None
    p=result["parameters"]
    assert p["inner_shoulder_left_d_mm"]-p["inner_shoulder_right_d_mm"] == pytest.approx(.15*8.33438)
    assert p["outer_shoulder_left_d_mm"]-p["outer_shoulder_right_d_mm"] == pytest.approx(.15*8.33438)

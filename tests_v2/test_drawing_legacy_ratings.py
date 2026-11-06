"""Original RoBAS fc/fo CSV search and rating formula parity (N->kN)."""
import math
import pytest

from bearing_cad.drawing_legacy_ratings import (
    calculate_robas_loads,apply_robas_loads,
)
from bearing_cad.drawing_variables import DrawingDataError

@pytest.fixture
def resources(tmp_path):
    resource=tmp_path/"Resource"
    resource.mkdir()
    (resource/"球轴承零件相关系数.csv").write_text(
        "Dw/Dpw,fc,fo\n0.2,50,15\n0.21,60,17\n0.3,55,16\n",encoding="utf-8")
    (resource/"圆柱滚子轴承相关系数.csv").write_text(
        "Dw/Dpw,fc\n0.2,85\n0.21,105\n0.3,90\n",encoding="utf-8")
    return tmp_path

def _p(kind,diameter=10,pitch=50):
    p={"pitch_d_mm":pitch,
       "ball_d_mm":diameter,"ball_count":10,
       "roller_d_mm":diameter,"roller_length_mm":12,
       "roller_count":12,"contact_angle_deg":25}
    return p

@pytest.mark.parametrize("kind",[
    "rolling.deep_groove_ball","rolling.angular_contact_ball",
    "rolling.cylindrical_roller"])
def test_original_ratings_source_formula(resources,kind):
    p=_p(kind)
    r=calculate_robas_loads(resources=resources,bearing_type=kind,parameters=p)
    assert r["gamma"]==.2
    assert r["coefficient_found"]
    if kind=="rolling.deep_groove_ball":
        dynamic=1.3*50*10**(2/3)*10**1.8
        static=15*10*10**2
    elif kind=="rolling.angular_contact_ball":
        a=math.radians(25)
        dynamic=1.3*50*math.cos(a)**.7*10**(2/3)*10**1.8
        static=15*10*10**2*math.cos(a)
    else:
        dynamic=1.89*50*12**(7/9)*12**(3/4)*10**(29/27)
        static=21.6*12*12*10
    assert r["dynamic_load_n"]==pytest.approx(dynamic)
    assert r["static_load_n"]==pytest.approx(static)

def test_dgb_original_large_ball_branch(resources):
    r=calculate_robas_loads(resources=resources,
       bearing_type="rolling.deep_groove_ball",
       parameters=_p("dgb",diameter=30,pitch=100))
    assert r["dynamic_load_n"]==pytest.approx(3.467*1.3*55*10**(2/3)*30**1.8)

def test_gamma_not_found_preserves_original_zero_behavior(resources):
    r=calculate_robas_loads(resources=resources,
       bearing_type="rolling.deep_groove_ball",
       parameters=_p("dgb",diameter=10,pitch=70))
    assert not r["coefficient_found"]
    assert r["dynamic_load_n"]==0
    assert r["warning"]

def test_load_text_and_source_trace(resources):
    r={"schema_version":"robas.drawing.variables.v1",
       "variables":[{"name":k,"value":None,"row_index":i,"source":"db"}
                    for i,k in enumerate(["Cr","Cor","Unrelated"])]}
    out=apply_robas_loads(report=r,resources=resources,
       bearing_type="rolling.deep_groove_ball",parameters=_p("dgb"))
    values={k["name"]:k["value"] for k in out["variables"]}
    assert values["Cr"]==f"{1.3*50*10**(2/3)*10**1.8/1000:.2f}"
    assert values["Cor"]=="15.00"
    assert values["Unrelated"] is None
    assert out["legacy_load_evidence"]["fc"]==50

def test_invalid_coef_or_missing_file_is_not_faked(resources):
    with pytest.raises(DrawingDataError):
        calculate_robas_loads(resources=resources,bearing_type="invalid",
                               parameters=_p("invalid"))
    with pytest.raises(DrawingDataError):
        calculate_robas_loads(resources=resources/"missing",
                               bearing_type="rolling.deep_groove_ball",parameters=_p("dgb"))


def _report():
    return {"schema_version": "robas.drawing.variables.v1",
            "variables": [{"name": name, "value": None, "row_index": i,
                           "source": "sqlite_default"}
                          for i, name in enumerate(("Cr", "Cor", "W16", "W46"))]}


@pytest.mark.parametrize("kind", [
    "rolling.deep_groove_ball", "rolling.angular_contact_ball",
    "rolling.cylindrical_roller",
])
def test_drawing_uses_ball_coefficient_csv_even_for_crb(resources, kind):
    result = calculate_robas_loads(
        resources=resources, bearing_type=kind, parameters=_p(kind))
    assert result["fc"] == 50
    assert result["fo"] == 15
    assert result["coefficient_csv"] == "球轴承零件相关系数.csv"
    assert result["dynamic_load_valid"]
    if kind == "rolling.cylindrical_roller":
        assert "ROBAS_CRB_DRAWING_USES_BASE_BALL_CSV_NOT_ROLLER_OPTIMIZER_CSV" in result["warnings"]


def test_crb_drawing_does_not_need_optimizer_only_roller_csv(resources):
    (resources / "Resource" / "圆柱滚子轴承相关系数.csv").unlink()
    result = calculate_robas_loads(
        resources=resources, bearing_type="rolling.cylindrical_roller",
        parameters=_p("crb"))
    assert result["fc"] == 50
    assert result["dynamic_load_valid"]


@pytest.mark.parametrize("kind", [
    "rolling.deep_groove_ball", "rolling.angular_contact_ball",
    "rolling.cylindrical_roller",
])
def test_drawing_gamma_and_formula_use_source_public_getters(resources, kind):
    p = _p(kind, diameter=10.251, pitch=50.005)
    p["roller_length_mm"] = 12.006
    result = calculate_robas_loads(
        resources=resources, bearing_type=kind, parameters=p)
    # 50.005 is exposed by PitchDiameter as 50.00; 10.251/50 => 0.21.
    assert result["gamma"] == .21
    assert result["fc"] == 60 and result["fo"] == 17
    if kind == "rolling.deep_groove_ball":
        expected = 1.3 * 60 * 10**(2 / 3) * 10.251**1.8
        static = 17 * 10 * 10.251**2
    elif kind == "rolling.angular_contact_ball":
        cosine = math.cos(math.radians(25))
        expected = 1.3 * 60 * cosine**.7 * 10**(2 / 3) * 10.251**1.8
        static = 17 * 10 * 10.251**2 * cosine
    else:
        expected = 1.89 * 60 * 12.01**(7 / 9) * 12**(3 / 4) * 10.251**(29 / 27)
        static = 21.6 * 12 * 12.01 * 10.251
    assert result["dynamic_load_n"] == pytest.approx(expected)
    assert result["static_load_n"] == pytest.approx(static)


def test_near_coefficient_row_is_not_exact_source_match(resources):
    (resources / "Resource" / "球轴承零件相关系数.csv").write_text(
        "Dw/Dpw,fc,fo\n0.20000000005,50,15\n", encoding="utf-8")
    result = calculate_robas_loads(
        resources=resources, bearing_type="rolling.deep_groove_ball",
        parameters=_p("dgb"))
    assert result["gamma"] == .2
    assert not result["coefficient_found"]
    assert not result["dynamic_load_valid"]
    assert result["dynamic_load_n"] == 0


@pytest.mark.parametrize("kind, expected_cor", [
    ("rolling.deep_groove_ball", None),
    ("rolling.angular_contact_ball", None),
    ("rolling.cylindrical_roller", "31.10"),
])
def test_missing_coefficient_never_fabricates_valid_cr(resources, kind, expected_cor):
    p = _p(kind, diameter=10, pitch=70)
    revised = apply_robas_loads(
        report=_report(), resources=resources, bearing_type=kind, parameters=p)
    values = {row["name"]: row["value"] for row in revised["variables"]}
    assert values["Cr"] is None
    assert values["Cor"] == expected_cor
    assert values["W16"] is None and values["W46"] is None
    assert "Cr" in revised["unresolved_ratings"]
    assert revised["legacy_load_evidence"]["coefficient_found"] is False
    assert revised["legacy_load_evidence"]["drawing_fields_written"] == (
        ["Cor"] if expected_cor is not None else [])


@pytest.mark.parametrize("kind", [
    "rolling.deep_groove_ball", "rolling.angular_contact_ball",
    "rolling.cylindrical_roller",
])
def test_missing_base_source_csv_fails_closed(resources, kind):
    (resources / "Resource" / "球轴承零件相关系数.csv").unlink()
    with pytest.raises(DrawingDataError, match="Missing original RoBAS coefficient CSV"):
        calculate_robas_loads(
            resources=resources, bearing_type=kind, parameters=_p(kind))


def test_nonpositive_source_coefficient_does_not_emit_invalid_cr(resources):
    (resources / "Resource" / "球轴承零件相关系数.csv").write_text(
        "Dw/Dpw,fc,fo\n0.2,0,15\n", encoding="utf-8")
    out = apply_robas_loads(
        report=_report(), resources=resources,
        bearing_type="rolling.deep_groove_ball", parameters=_p("dgb"))
    values = {row["name"]: row["value"] for row in out["variables"]}
    assert values["Cr"] is None
    assert values["Cor"] == "15.00"
    assert out["legacy_load_evidence"]["coefficient_found"]


def test_bad_source_coefficient_is_rejected(resources):
    (resources / "Resource" / "球轴承零件相关系数.csv").write_text(
        "Dw/Dpw,fc,fo\n0.2,nan,15\n", encoding="utf-8")
    with pytest.raises(DrawingDataError, match="Non-finite RoBAS coefficient"):
        calculate_robas_loads(
            resources=resources, bearing_type="rolling.deep_groove_ball",
            parameters=_p("dgb"))

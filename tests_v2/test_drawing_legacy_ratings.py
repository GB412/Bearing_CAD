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
        "Dw/Dpw,fc,fo\n0.2,50,15\n0.3,55,16\n",encoding="utf-8")
    (resource/"圆柱滚子轴承相关系数.csv").write_text(
        "Dw/Dpw,fc\n0.2,85\n0.3,90\n",encoding="utf-8")
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
        dynamic=1.89*85*12**(7/9)*12**(3/4)*10**(29/27)
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

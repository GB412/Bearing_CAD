"""CRB source coefficient, geometry and the explicit missing-Kr gate."""
from __future__ import annotations

import csv
import math

import pytest

from bearing_cad.contracts import parse_request
from bearing_cad.robas_crb_optimization import (
    _roller_count, _source_roller_length_limit, optimize_crb_candidates,
)
from bearing_cad.robas_optimization import OptimizationError

INITIAL = {
    "bearing_type":"rolling.cylindrical_roller",
    "bore_d_mm":40,"outside_d_mm":80,"width_mm":18,
    "configuration":"NU",
    "radial_clearance_mm":.05,"axial_clearance_mm":.4,"rib_width_mm":2,
    "roller_profile":"crowned","roller_end_chamfer_mm":.2,
    "roller_crown_relief_mm":.02,"cage":None,
}
OPTIONS={"model":"NU208","accuracy_class":"P5","objective":"dynamic_load_only"}


@pytest.fixture
def crb_resources(tmp_path):
    root=tmp_path/"RoBAS_Resources"
    source=root/"Resource"
    source.mkdir(parents=True)
    (source/"CylinderRollerDiameterDB.csv").write_text(
        "Dw\n8\n9\n10\n11\n12\n13\n14\n15\n16\n",encoding="utf-8")
    (source/"CylinderRollerDB.csv").write_text(
        "Dw,Lw\n10,10\n10,12\n11,11\n11,13\n"
        "12,12\n12,14\n13,13\n13,16\n14,14\n14,18\n",
        encoding="utf-8")
    with (source/"圆柱滚子轴承相关系数.csv").open(
        "w",newline="",encoding="utf-8-sig") as f:
        writer=csv.writer(f)
        writer.writerow(("Dw/Dpw","fc"))
        for i in range(10,31):
            writer.writerow((i/100,60+i))
    return root


def test_source_roll_count_and_nearest_listed_length():
    assert _roller_count(5,60)==int(math.pi*60/(1.35*5))
    assert _roller_count(11,60)==int(math.pi*60/(1.225*11))
    assert _roller_count(50,100)==int(math.pi*100/(1.3*50))
    rows=[{"Dw":11.0,"Lw":11.0},{"Dw":11.0,"Lw":13.0},
          {"Dw":11.0,"Lw":20.0}]
    assert _source_roller_length_limit(11,80,18,rows)==13
    assert _source_roller_length_limit(12,80,18,rows) is None


def test_crb_source_cr_only_outputs_valid_distinct_candidate_structures(crb_resources):
    before={**INITIAL}
    reply=optimize_crb_candidates(resources=crb_resources,
                                  initial=INITIAL,optimization=OPTIONS)
    assert before==INITIAL
    assert reply["schema_version"]=="bearing-cad.robas-crb-optimization.v1"
    assert reply["candidate_only"] is True and reply["applied"] is False
    assert reply["objective_status"]=="CR_ONLY_SOURCE_KR_NOT_IMPLEMENTED"
    assert "SOURCE_CRB_RADIAL_STIFFNESS_RETURNS_ZERO_NOT_VALID_KR" in reply["warnings"]
    assert "CRB_OPTIMIZER_ROLLER_CSV_DIFFERS_FROM_DRAWING_BALL_CSV" in reply["warnings"]
    assert reply["source_model_evidence"]["status"]=="MODEL_CONFIGURATION_PREFIX_MATCH_UNVERIFIED_DIMENSIONS"
    assert set(reply["source_csv_sha256"])=={
        "CylinderRollerDiameterDB.csv","CylinderRollerDB.csv",
        "圆柱滚子轴承相关系数.csv"}
    assert reply["total_valid_candidates"]>=reply["total_distinct_structures"]
    assert len(reply["candidates"])==min(5,reply["total_distinct_structures"])
    assert reply["candidates"][0]["score"]==pytest.approx(1.0)
    scores=[x["score"] for x in reply["candidates"]]
    assert scores==sorted(scores,reverse=True)
    groups=set()
    for row in reply["candidates"]:
        assert row["metrics"]["radial_stiffness_source_units"] is None
        assert row["metrics"]["dynamic_load_n"]>0
        assert row["metrics"]["static_load_n"]>0
        p=parse_request(row["design"]).parameters
        assert p["configuration"]=="NU"
        assert p["roller_profile"]=="crowned"
        assert p["radial_clearance_mm"]==pytest.approx(.05)
        assert p["bore_d_mm"]==40 and p["outside_d_mm"]==80
        assert p["inner_rib_tip_d_mm"]<p["pitch_d_mm"]<p["outer_rib_tip_d_mm"]
        key=(p["roller_d_mm"],p["roller_length_mm"],p["roller_count"])
        assert key not in groups
        groups.add(key)
        z,dw,lw= p["roller_count"],p["roller_d_mm"],p["roller_length_mm"]
        fc=row["coefficient_lookup"]["fc"]
        assert row["metrics"]["dynamic_load_n"]==pytest.approx(
            1.89*fc*lw**(7/9)*z**(.75)*dw**(29/27))
        assert row["metrics"]["static_load_n"]==pytest.approx(21.6*z*lw*dw)


@pytest.mark.parametrize("config",["N","NU","NJ","NF","NUP"])
def test_all_original_rib_configurations_return_cad_ready_parameters(
        crb_resources,config):
    model=config+"208"
    initial={**INITIAL,"configuration":config}
    option={**OPTIONS,"model":model}
    result=optimize_crb_candidates(resources=crb_resources,
                                   initial=initial,optimization=option)
    assert result["candidates"]
    for entry in result["candidates"]:
        assert parse_request(entry["design"]).parameters["configuration"]==config


@pytest.mark.parametrize("bad",[
    {**INITIAL,"configuration":"BAD"},
    {**INITIAL,"cage":{"kind":"cylindrical_window"}},
    {**INITIAL,"radial_clearance_mm":-1},
    {**INITIAL,"roller_profile":"illegal"},
    {**INITIAL,"bore_d_mm":80},
    {**INITIAL,"rib_width_mm":8},
    {**INITIAL,"outside_d_mm":201},
    {**INITIAL,"roller_end_chamfer_mm":False},
    {**INITIAL,"unknown":1},
])
def test_bad_initial_does_not_produce_candidates(crb_resources,bad):
    with pytest.raises(OptimizationError):
        optimize_crb_candidates(resources=crb_resources,
                                initial=bad,optimization=OPTIONS)


@pytest.mark.parametrize("bad",[
    {**OPTIONS,"model":"NUP208"},
    {**OPTIONS,"model":"6008"},
    {**OPTIONS,"objective":"cr_kr_weighted"},
    {**OPTIONS,"accuracy_class":"UNKNOWN"},
    {**OPTIONS,"unknown":1},
])
def test_invalid_source_label_or_unsupported_kr_is_rejected(crb_resources,bad):
    with pytest.raises(OptimizationError):
        optimize_crb_candidates(resources=crb_resources,
                                initial=INITIAL,optimization=bad)


def test_roller_coefficient_csv_missing_or_unmatched_is_not_faked(crb_resources):
    path=crb_resources/"Resource"/"圆柱滚子轴承相关系数.csv"
    path.unlink()
    with pytest.raises(OptimizationError,match="missing"):
        optimize_crb_candidates(resources=crb_resources,
                                initial=INITIAL,optimization=OPTIONS)
    path.write_text("Dw/Dpw,fc\n0.99,99\n",encoding="utf-8")
    with pytest.raises(OptimizationError,match="No source-backed CRB candidates"):
        optimize_crb_candidates(resources=crb_resources,
                                initial=INITIAL,optimization=OPTIONS)


def test_crb_no_prior_roller_parameters_required(crb_resources):
    assert "roller_d_mm" not in INITIAL
    assert "roller_count" not in INITIAL
    assert "pitch_d_mm" not in INITIAL
    response=optimize_crb_candidates(resources=crb_resources,
                                     initial=INITIAL,optimization=OPTIONS)
    assert response["candidates"][0]["design"]["parameters"]["roller_count"]>=2

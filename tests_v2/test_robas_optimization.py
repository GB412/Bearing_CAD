"""DGB optimizer: original coefficient sources, candidate-only contract and guards."""
from __future__ import annotations

import csv
import math
import sqlite3

import pytest

from bearing_cad.contracts import parse_request
from bearing_cad.drawing_variables import DrawingDataError
from bearing_cad.robas_optimization import optimize_dgb_candidates, OptimizationError
from test_robas_sizing_api import _request, _start, _stop

MODEL = "6008"
INITIAL = {
    "bearing_type": "rolling.deep_groove_ball",
    "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
    "cage": {"kind": "simplified_annular", "pocket_clearance_mm": .25},
}
OPTIONS = {
    "model": MODEL, "accuracy_class": "P5", "radial_clearance_group": "C0",
    "weights": {"dynamic_load": .8, "radial_stiffness": .2},
}


@pytest.fixture
def tables(tmp_path):
    root = tmp_path / "RoBAS_Resources"
    folder = root / "Resource"
    folder.mkdir(parents=True)
    (folder / "BallDB.csv").write_text(
        "diameter(mm)\n7.9375\n8\n8.33438\n8.5\n8.73125\n9\n",
        encoding="utf-8")
    with (folder / "球轴承零件相关系数.csv").open(
            "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Dw/Dpw", "fc", "fo"))
        for index, gamma in enumerate((.14, .15, .16, .17, .18, .19)):
            writer.writerow((gamma, 50 + index * 2, 15 + index))
    data = root / "Data"
    data.mkdir()
    with sqlite3.connect(data / "BearingType.db") as db:
        db.execute(
            'CREATE TABLE "深沟球轴承型号目录" '
            '("model" TEXT, "d" REAL, "Dd" REAL, "B" REAL)')
        db.executemany(
            'INSERT INTO "深沟球轴承型号目录" VALUES (?,?,?,?)',
            (("6008", 40, 68, 15), ("6208", 40, 80, 18)))
    return root


def test_dgb_optimizer_returns_ranked_readonly_full_geometry_candidates(tables):
    raw_input = dict(INITIAL)
    options = {
        **OPTIONS, "weights": {"dynamic_load": .8, "radial_stiffness": .2}}
    original_input = {**raw_input, "cage": dict(raw_input["cage"])}
    result = optimize_dgb_candidates(resources=tables, initial=raw_input,
                                     optimization=options)
    assert raw_input == original_input
    assert result["schema_version"] == "bearing-cad.robas-dgb-optimization.v1"
    assert result["candidate_only"] is True and result["applied"] is False
    assert result["total_valid_candidates"] >= len(result["candidates"]) > 1
    assert len(result["candidates"]) <= 5
    assert len(result["source_initial_hash"]) == 64
    assert result["source_catalog_evidence"]["status"] == (
        "SOURCE_MODEL_DIMENSIONS_MATCH_REQUEST")
    assert "SOURCE_DGB_SECOND_BEST_SELECTION_BUG_NOT_REPRODUCED" in result["warnings"]
    assert [row["rank"] for row in result["candidates"]] == list(
        range(1, len(result["candidates"]) + 1))
    assert [row["score"] for row in result["candidates"]] == sorted(
        [row["score"] for row in result["candidates"]], reverse=True)
    for candidate in result["candidates"]:
        checked = parse_request(candidate["design"])
        p = checked.parameters
        assert checked.bearing_type.value == INITIAL["bearing_type"]
        assert (p["bore_d_mm"], p["outside_d_mm"], p["width_mm"]) == (40, 68, 15)
        assert p["ball_count"] != 0 and p["pitch_d_mm"] > p["ball_d_mm"]
        assert p["inner_groove_radius_mm"] == pytest.approx(.51 * p["ball_d_mm"])
        assert p["outer_groove_radius_mm"] == pytest.approx(.53 * p["ball_d_mm"])
        assert candidate["metrics"]["dynamic_load_n"] > 0
        assert candidate["metrics"]["static_load_n"] > 0
        assert candidate["metrics"]["radial_stiffness_source_units"] > 0
        assert checked.cage.kind == "simplified_annular"


def test_dgb_objective_weights_are_meaningful(tables):
    loads = optimize_dgb_candidates(
        resources=tables, initial=INITIAL,
        optimization={**OPTIONS, "weights": {"dynamic_load": 1, "radial_stiffness": 0}})
    stiffness = optimize_dgb_candidates(
        resources=tables, initial=INITIAL,
        optimization={**OPTIONS, "weights": {"dynamic_load": 0, "radial_stiffness": 1}})
    assert loads["candidates"][0]["metrics"]["dynamic_load_n"] == pytest.approx(
        max(item["metrics"]["dynamic_load_n"] for item in loads["candidates"]))
    assert stiffness["candidates"][0]["metrics"]["radial_stiffness_source_units"] == pytest.approx(
        max(item["metrics"]["radial_stiffness_source_units"]
            for item in stiffness["candidates"]))
    assert loads["optimization"]["weights"] != stiffness["optimization"]["weights"]


@pytest.mark.parametrize("bad_weights", [
    {"dynamic_load": .8, "radial_stiffness": .3},
    {"dynamic_load": -1, "radial_stiffness": 2},
    {"dynamic_load": float("nan"), "radial_stiffness": 1},
    {"dynamic_load": .5},
    {"dynamic_load": True, "radial_stiffness": 0},
])
def test_dgb_weights_must_be_explicit_and_valid(tables, bad_weights):
    with pytest.raises(OptimizationError):
        optimize_dgb_candidates(
            resources=tables, initial=INITIAL,
            optimization={**OPTIONS, "weights": bad_weights})


def test_mismatched_source_model_is_not_optimizable(tables):
    with pytest.raises(DrawingDataError, match="dimensions disagree"):
        optimize_dgb_candidates(resources=tables, initial=INITIAL,
                                optimization={**OPTIONS, "model": "6208"})


def test_optimizer_rejects_stamped_cage_until_recomputed(tables):
    with pytest.raises(OptimizationError, match="simplified_annular"):
        optimize_dgb_candidates(resources=tables,
            initial={**INITIAL, "cage": {"kind": "stamping_double_half",
                                       "pocket_clearance_mm": .15}},
            optimization=OPTIONS)


def test_optimizer_needs_no_prepopulated_ball_count_or_grooves(tables):
    assert set(INITIAL) == {
        "bearing_type", "bore_d_mm", "outside_d_mm", "width_mm", "cage"}
    result = optimize_dgb_candidates(
        resources=tables, initial=INITIAL, optimization=OPTIONS)
    assert result["candidates"][0]["design"]["parameters"]["ball_count"] >= 2


def test_optimizer_never_uses_unlisted_fabricated_coefficients(tables):
    coefficient = tables / "Resource" / "球轴承零件相关系数.csv"
    coefficient.write_text("Dw/Dpw,fc,fo\n0.01,99,99\n", encoding="utf-8")
    with pytest.raises(OptimizationError, match="No source-backed DGB candidates"):
        optimize_dgb_candidates(resources=tables, initial=INITIAL,
                                optimization=OPTIONS)


def test_optimizer_rejects_unsupported_bores_and_models(tables):
    with pytest.raises(OptimizationError, match="d=240"):
        optimize_dgb_candidates(
            resources=tables,
            initial={**INITIAL, "bore_d_mm": 250, "outside_d_mm": 280},
            optimization=OPTIONS)
    with pytest.raises(OptimizationError, match="series 60, 62 and 63"):
        optimize_dgb_candidates(
            resources=tables, initial=INITIAL,
            optimization={**OPTIONS, "model": "6408"})


def test_optimizer_api_http_gates_and_status(tables, tmp_path):
    server, thread = _start(tmp_path / "cad-artifacts", tables)
    path = "/api/v2/cad/optimization/dgb"
    try:
        status, health = _request(server, "GET", "/api/v2/cad/status")
        assert status == 200 and health["robas_optimization_available"]
        status, result = _request(
            server, "POST", path, {"initial": INITIAL, "optimization": OPTIONS})
        assert status == 200
        assert result["candidate_only"] is True
        assert result["applied"] is False
        status, denied = _request(
            server, "POST", path, {"initial": INITIAL, "optimization": OPTIONS},
            origin="http://evil.example")
        assert status == 403 and denied["error"]["error_code"] == "ORIGIN_FORBIDDEN"
        status, denied = _request(
            server, "POST", path,
            {"initial": INITIAL, "optimization": OPTIONS, "extra": True})
        assert status == 422 and denied["error"]["error_code"] == "PARAMETER_INVALID"
        status, denied = _request(
            server, "POST", path,
            {"initial": INITIAL, "optimization": {**OPTIONS, "model": "6208"}})
        assert status == 422 and denied["error"]["error_code"] == "OPTIMIZATION_INVALID"
    finally:
        _stop(server, thread)


def test_optimizer_api_missing_resources_is_explicit(tmp_path):
    server, thread = _start(tmp_path / "cad-artifacts")
    try:
        status, health = _request(server, "GET", "/api/v2/cad/status")
        assert status == 200 and not health["robas_optimization_available"]
        status, denied = _request(
            server, "POST", "/api/v2/cad/optimization/dgb",
            {"initial": INITIAL, "optimization": OPTIONS})
        assert status == 503
        assert denied["error"]["error_code"] == "ROBAS_RESOURCES_UNAVAILABLE"
    finally:
        _stop(server, thread)

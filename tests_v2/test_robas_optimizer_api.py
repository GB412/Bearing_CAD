"""HTTP endpoint tests run in CAD-V2 environment (CADQuery installed)."""
from test_robas_sizing_api import _request, _start, _stop
from test_robas_optimization import tables, INITIAL, OPTIONS

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


def test_optimized_candidate_builds_real_valid_occt_brep(tables):
    import pytest
    pytest.importorskip("cadquery")
    from bearing_cad.contracts import parse_request
    from bearing_cad.deep_groove import build_deep_groove
    from bearing_cad.geometry_checks import inspect_solid
    from bearing_cad.robas_optimization import optimize_dgb_candidates

    result = optimize_dgb_candidates(
        resources=tables, initial=INITIAL, optimization=OPTIONS)
    selected = parse_request(result["candidates"][0]["design"])
    model = build_deep_groove(selected)
    assert all(inspect_solid(part.shape).valid for part in model.components)
    assert len(model.instances) == selected.parameters["ball_count"] + 3

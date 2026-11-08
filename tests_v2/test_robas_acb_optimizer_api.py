"""ACB optimization HTTP gates and real CAD B-Rep regression."""
from test_robas_sizing_api import _request, _start, _stop
from test_robas_acb_optimization import acb_resources, INITIAL, OPTIONS


def test_acb_optimizer_http_route_requires_original_resources(acb_resources,tmp_path):
    srv,thread=_start(tmp_path/"artifacts",acb_resources)
    path="/api/v2/cad/optimization/acb"
    try:
        status,health=_request(srv,"GET","/api/v2/cad/status")
        assert status==200 and health["robas_acb_optimization_available"]
        status,reply=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":OPTIONS})
        assert status==200
        assert reply["candidate_only"] and not reply["applied"]
        status,bad=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":OPTIONS},
            origin="http://evil.example")
        assert status==403 and bad["error"]["error_code"]=="ORIGIN_FORBIDDEN"
        status,bad=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":OPTIONS,"extra":1})
        assert status==422 and bad["error"]["error_code"]=="PARAMETER_INVALID"
        status,bad=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":{**OPTIONS,"preload_n":0}})
        assert status==422 and bad["error"]["error_code"]=="OPTIMIZATION_INVALID"
    finally:
        _stop(srv,thread)


def test_acb_optimizer_http_without_resources_returns_503(tmp_path):
    srv,thread=_start(tmp_path/"artifacts")
    try:
        status,health=_request(srv,"GET","/api/v2/cad/status")
        assert status==200 and not health["robas_acb_optimization_available"]
        status,reply=_request(srv,"POST","/api/v2/cad/optimization/acb",{
            "initial":INITIAL,"optimization":OPTIONS})
        assert status==503 and reply["error"]["error_code"]=="ROBAS_RESOURCES_UNAVAILABLE"
    finally:
        _stop(srv,thread)


def test_top_acb_candidate_builds_occt_geometry(acb_resources):
    import pytest
    pytest.importorskip("cadquery")
    from bearing_cad.robas_acb_optimization import optimize_acb_candidates
    from bearing_cad.contracts import parse_request
    from bearing_cad.angular_contact import build_angular_contact
    from bearing_cad.geometry_checks import inspect_solid
    optimized=optimize_acb_candidates(
        resources=acb_resources,initial=INITIAL,optimization=OPTIONS)
    first=parse_request(optimized["candidates"][0]["design"])
    model=build_angular_contact(first)
    assert len(model.instances)==first.parameters["ball_count"]+2
    assert all(inspect_solid(part.shape).valid for part in model.components)

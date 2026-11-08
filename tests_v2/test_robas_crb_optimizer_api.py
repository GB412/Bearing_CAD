"""CRB source-backed API gates and actual OCCT regression (CADQuery environment)."""
from test_robas_sizing_api import _request, _start, _stop
from test_robas_crb_optimization import crb_resources, INITIAL, OPTIONS


def test_crb_optimizer_http_source_and_validation(crb_resources,tmp_path):
    srv,thread=_start(tmp_path/"artifacts",crb_resources)
    path="/api/v2/cad/optimization/crb"
    try:
        status,health=_request(srv,"GET","/api/v2/cad/status")
        assert status==200 and health["robas_crb_optimization_available"]
        status,reply=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":OPTIONS})
        assert status==200 and reply["candidate_only"] is True
        assert reply["objective_status"]=="CR_ONLY_SOURCE_KR_NOT_IMPLEMENTED"
        status,err=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":OPTIONS},
            origin="http://evil.example")
        assert status==403 and err["error"]["error_code"]=="ORIGIN_FORBIDDEN"
        status,err=_request(srv,"POST",path,{
            "initial":INITIAL,"optimization":OPTIONS,"extra":1})
        assert status==422 and err["error"]["error_code"]=="PARAMETER_INVALID"
        status,err=_request(srv,"POST",path,{
            "initial":INITIAL,
            "optimization":{**OPTIONS,"objective":"cr_kr_weighted"}})
        assert status==422 and err["error"]["error_code"]=="OPTIMIZATION_INVALID"
    finally:
        _stop(srv,thread)


def test_crb_optimizer_without_original_resources_is_disabled(tmp_path):
    srv,thread=_start(tmp_path/"artifacts")
    try:
        status,health=_request(srv,"GET","/api/v2/cad/status")
        assert status==200 and not health["robas_crb_optimization_available"]
        status,err=_request(srv,"POST","/api/v2/cad/optimization/crb",{
            "initial":INITIAL,"optimization":OPTIONS})
        assert status==503 and err["error"]["error_code"]=="ROBAS_RESOURCES_UNAVAILABLE"
    finally:
        _stop(srv,thread)


def test_top_crb_candidate_builds_real_occt_brep(crb_resources):
    import pytest
    pytest.importorskip("cadquery")
    from bearing_cad.robas_crb_optimization import optimize_crb_candidates
    from bearing_cad.contracts import parse_request
    from bearing_cad.cylindrical_roller import build_cylindrical_roller
    from bearing_cad.geometry_checks import inspect_solid
    result=optimize_crb_candidates(resources=crb_resources,
                                   initial=INITIAL,optimization=OPTIONS)
    selected=parse_request(result["candidates"][0]["design"])
    assembly=build_cylindrical_roller(selected)
    assert len(assembly.instances)==selected.parameters["roller_count"]+2
    assert all(inspect_solid(component.shape).valid
               for component in assembly.components)


def test_nup_candidate_includes_distinct_loose_rib_brep(crb_resources):
    import pytest
    pytest.importorskip("cadquery")
    from bearing_cad.robas_crb_optimization import optimize_crb_candidates
    from bearing_cad.contracts import parse_request
    from bearing_cad.cylindrical_roller import build_cylindrical_roller
    initial={**INITIAL,"configuration":"NUP"}
    options={**OPTIONS,"model":"NUP208"}
    result=optimize_crb_candidates(resources=crb_resources,
                                   initial=initial,optimization=options)
    selected=parse_request(result["candidates"][0]["design"])
    assembly=build_cylindrical_roller(selected)
    assert "loose_rib" in [p.component_id for p in assembly.components]
    assert len(assembly.instances)==selected.parameters["roller_count"]+3

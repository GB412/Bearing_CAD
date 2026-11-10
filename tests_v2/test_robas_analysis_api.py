"""HTTP orchestration with a portable launcher and independent Windows goldens."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
from subprocess import CompletedProcess, TimeoutExpired
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bearing_cad import robas_analysis, robas_solver_probe
from bearing_cad.api import make_server
from bearing_cad.contracts import parse_request
from bearing_cad.robas_ball_input import BallDataDocument, geometry_updates
from bearing_cad.robas_results import parse_static_results
from test_robas_ball_input import ACB, ACB_SHA256, DGB, DGB_SHA256, _case, _synthetic_data
from test_robas_results import run as result_fixture  # noqa: F401 (pytest fixture)
from test_robas_roller_input import GOLDEN, GOLDEN_SHA256, n222_request
from test_robas_sizing_api import _request, _stop
from test_robas_solver_probe import _test_pe


ROUTE = "/api/v2/cad/analyses"


@contextmanager
def _server(tmp_path, resources=None, manifest=None):
    server = make_server(artifacts_root=tmp_path / "artifacts", robas_resources=resources,
                         robas_analysis_profiles=manifest)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        _stop(server, thread)


def _profile(tmp_path, raw, request, digest=None):
    path = tmp_path / "reference.txt"
    path.write_bytes(raw)
    manifest = tmp_path / "profiles.json"
    manifest.write_text(json.dumps({"reviewed": {
        "bearing_type": request.bearing_type.value, "configuration": request.parameters.get("configuration"),
        "data_file": path.name, "sha256": digest or sha256(raw).hexdigest(), "source": "Operator-reviewed test profile",
    }}), encoding="utf-8")
    return manifest, path


def _body(request, geometry, conditions=None):
    return {"design": json.loads(request.canonical_json()), "request_hash": request.request_hash,
            "profile_id": "reviewed", "analysis_geometry": geometry,
            "operating_conditions": conditions if conditions is not None else {}}


@pytest.fixture
def portable(tmp_path, monkeypatch, result_fixture):
    design = _case("dgb_no_cage")
    request = parse_request({**design, "parameters": {**design["parameters"], "ball_count": 2}})
    base = BallDataDocument.parse(_synthetic_data()).with_updates({
        **geometry_updates(request, analysis_inner_race_outside_diameter_mm=49),
        (10, "freeIntCls"): 0,
        **{(3, name): f"'{filename}'" for name, filename in zip(
            ("finName", *(f"pltNames{i}" for i in range(1, 10))), robas_analysis._OUTPUT_NAMES)},
    })
    manifest, reference = _profile(tmp_path, base.render().encode(), request)
    resources = tmp_path / "resources"
    (resources / "exe").mkdir(parents=True)
    exe = _test_pe()
    (resources / "exe" / "RoBAS_v2.exe").write_bytes(exe)
    digest = sha256(exe).hexdigest()
    state = {"status": "ok"}

    def launch(path, folder, timeout):
        assert timeout == 45 and path.parent == folder
        if state["status"] == "timeout":
            raise TimeoutExpired(path, timeout)
        if state["status"] == "start":
            raise OSError("test start failure")
        if state["status"] == "exit":
            return CompletedProcess(path, 4)
        if state["status"] != "no_output":
            output = (result_fixture / "OUT.txt").read_bytes()
            (folder / "OUT.txt").write_bytes(output if state["status"] != "bad_out" else b"truncated")
        return CompletedProcess(path, 0)

    def probe(**kwargs):
        report = robas_solver_probe.run_probe(**kwargs, _platform="Windows", _launcher=launch, expected_sha=digest)
        if state["status"] == "tampered":
            path = Path(report["run_directory"]) / "OUT.txt"
            path.write_bytes(path.read_bytes() + b"\r\n")
        return report

    monkeypatch.setattr(robas_analysis, "platform", SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(robas_analysis, "run_probe", probe)
    monkeypatch.setattr(robas_analysis, "inspect_executable",
                        lambda resource: robas_solver_probe.inspect_executable(resource, expected_sha=digest))
    return resources, manifest, reference, _body(request, {"inner_race_od_mm": 49}), state


def test_http_uses_bound_result_and_persists_distinct_input_versions(tmp_path, portable):
    resources, manifest, reference, body, _ = portable
    reference_hash = sha256(reference.read_bytes()).hexdigest()
    with _server(tmp_path, resources, manifest) as server:
        status, available = _request(server, "GET", ROUTE + "/status")
        assert status == 200 and available["available"]
        assert available["profiles"]["reviewed"]["sha256"] == reference_hash
        assert "data_file" not in available["profiles"]["reviewed"]
        first_status, first = _request(server, "POST", ROUTE, body)
        second_status, second = _request(server, "POST", ROUTE, {
            **body, "operating_conditions": {"load_x_n": 1200, "inner_speed_rpm": 4000, "free_clearance_mm": 0.02},
        })
    assert first_status == second_status == 201, (first, second)
    assert first["run_id"] != second["run_id"]
    assert first["request_hash"] == second["request_hash"] == body["request_hash"]
    assert first["generated_data_sha256"] != second["generated_data_sha256"]
    assert second["profile"]["sha256"] == reference_hash == sha256(reference.read_bytes()).hexdigest()
    assert second["result"]["source_binding"]["status"] == "HASH_VERIFIED"
    assert second["result"]["files"]["DATA.txt"]["sha256"] == second["generated_data_sha256"]
    assert second["result"]["execution"] == {"status": "EXITED_ZERO", "exit_code": 0}
    assert second["result"]["convergence"] == {"status": "UNKNOWN"}
    assert second["result"]["contacts"][0]["outer"]["load"]["value"] == 126
    folder = tmp_path / "artifacts" / "robas-analysis" / ("analysis-" + second["run_id"])
    doc = BallDataDocument.read(folder / "DATA.txt")
    assert doc.value(29, "appLoadX") == "1200.0"
    assert doc.value(32, "rpmRange12") == "4000.0"
    assert float(doc.value(10, "freeIntCls")) == pytest.approx(0.00002)
    assert json.loads((folder / "analysis_result.json").read_bytes()) == second


@pytest.mark.parametrize(("case", "http", "code"), [
    ("timeout", 504, "ANALYSIS_TIMEOUT"), ("start", 502, "ANALYSIS_EXECUTION_FAILED"),
    ("exit", 502, "ANALYSIS_EXECUTION_FAILED"), ("no_output", 502, "ANALYSIS_OUTPUT_INVALID"),
    ("bad_out", 502, "ANALYSIS_RESULT_INVALID"), ("tampered", 502, "ANALYSIS_RESULT_INVALID"),
])
def test_http_distinguishes_probe_and_parser_failures(tmp_path, portable, case, http, code):
    resources, manifest, _, body, state = portable
    state["status"] = case
    with _server(tmp_path, resources, manifest) as server:
        status, error = _request(server, "POST", ROUTE, body)
    assert status == http and error["error"]["error_code"] == code
    assert "run_id" in error and "execution" in error and "result" not in error
    if case == "tampered":
        assert "SHA-256 mismatch" in error["error"]["message"]


def test_http_closed_fields_design_hash_and_profile_integrity(tmp_path, portable):
    resources, manifest, reference, body, _ = portable
    with _server(tmp_path, resources, manifest) as server:
        for change, expected, path in [
            ({"exe_path": "C:/external.exe"}, 422, "/exe_path"),
            ({"profile_id": "../DATA.txt"}, 422, "/profile_id"),
            ({"request_hash": "0" * 64}, 409, "/request_hash"),
            ({"operating_conditions": {"(1, nStps)": 9}}, 422, "/operating_conditions/(1, nStps)"),
            ({"operating_conditions": {"load_x_n": 1000001}}, 422, "/operating_conditions/load_x_n"),
            ({"analysis_geometry": {}}, 422, "/analysis_geometry/inner_race_od_mm"),
        ]:
            status, reply = _request(server, "POST", ROUTE, {**body, **change})
            assert status == expected and reply["error"]["field_path"] == path
        status, _ = _request(server, "POST", ROUTE, body, origin="http://elsewhere.example")
        assert status == 403
        reference.write_bytes(reference.read_bytes().replace(b"'test-run'", b"'altered'"))
        status, reply = _request(server, "POST", ROUTE, body)
        assert status == 503 and "pinned SHA-256" in reply["error"]["message"]
    assert not (tmp_path / "artifacts" / "robas-analysis").exists()


def test_reference_manifest_refuses_escape(tmp_path):
    sub = tmp_path / "manifest"
    sub.mkdir()
    (tmp_path / "outside.txt").write_bytes(b"reference")
    manifest, _ = _profile(sub, b"reference", n222_request())
    entries = json.loads(manifest.read_bytes())
    entries["reviewed"]["data_file"] = "../outside.txt"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="under the manifest directory"):
        robas_analysis.load_analysis_profiles(manifest)


def test_pinned_reference_cannot_redirect_solver_output(tmp_path, portable):
    resources, _, reference, body, _ = portable
    original = BallDataDocument.read(reference)
    raw = original.with_updates({(3, "finName"): "'../OUT.txt'"}).render().encode()
    manifest, _ = _profile(tmp_path, raw, parse_request(body["design"]))
    with _server(tmp_path, resources, manifest) as server:
        status, error = _request(server, "POST", ROUTE, body)
    assert status == 503 and "unsupported output filenames" in error["error"]["message"]
    assert not (tmp_path / "artifacts" / "robas-analysis").exists()


def test_unsupported_and_unconfigured_http(tmp_path):
    with _server(tmp_path) as server:
        status, error = _request(server, "POST", ROUTE, _body(n222_request(configuration="NU"), {}))
        assert status == 422 and error["error"]["field_path"] == "/design/parameters/configuration"
        status, error = _request(server, "POST", ROUTE, _body(n222_request(), {}))
        assert status == 503 and error["error"]["error_code"] == "ANALYSIS_UNAVAILABLE"
        request, geometry = _golden_design("ACB")
        status, error = _request(server, "POST", ROUTE, _body(request, {**geometry, "outer_sidewall_mm": 99}))
        assert status == 422 and error["error"]["field_path"] == "/analysis_geometry/outer_sidewall_mm"


def test_one_active_analysis_and_retention_budget(tmp_path, portable, monkeypatch):
    resources, manifest, _, body, _ = portable
    initial = robas_analysis.run_probe
    entered, release = Event(), Event()

    def waiting(**kwargs):
        entered.set()
        assert release.wait(5)
        return initial(**kwargs)

    monkeypatch.setattr(robas_analysis, "run_probe", waiting)
    monkeypatch.setattr(robas_analysis, "_MAX_RETAINED_RUNS", 1)
    replies = []
    with _server(tmp_path, resources, manifest) as server:
        request = Thread(target=lambda: replies.append(_request(server, "POST", ROUTE, body)))
        request.start()
        try:
            assert entered.wait(5)
            status, error = _request(server, "POST", ROUTE, body)
            assert status == 503 and error["error"]["error_code"] == "ANALYSIS_BUSY"
        finally:
            release.set()
            request.join(timeout=8)
        assert replies[0][0] == 201
        status, error = _request(server, "POST", ROUTE, body)
        assert status == 503 and error["error"]["error_code"] == "ANALYSIS_STORAGE_LIMIT"


def _golden_design(kind):
    if kind == "N222":
        return n222_request(), {}
    fixture = _case("dgb_no_cage" if kind == "DGB" else "acb_25deg_window")
    design = {key: value for key, value in fixture.items() if key != "cage"}
    if kind == "DGB":
        dw = 8.334
        parameters = dict(bore_d_mm=40, outside_d_mm=68, width_mm=15, ball_count=11,
                          pitch_d_mm=54, inner_shoulder_d_mm=49, outer_shoulder_d_mm=59.02)
        geometry = {"inner_race_od_mm": 49}
    else:
        dw = 11
        # CAD's opposite shoulder fields use the source's tapered-end
        # diameter values, rounded to 0.01 mm. The solver uses only the
        # explicitly identified original analysis sidewalls below.
        parameters = dict(bore_d_mm=65, outside_d_mm=100, width_mm=18, ball_count=20, pitch_d_mm=82.5,
                          contact_angle_deg=25, inner_shoulder_left_d_mm=75.9, inner_shoulder_right_d_mm=72.44,
                          outer_shoulder_left_d_mm=92.56, outer_shoulder_right_d_mm=89.15)
        geometry = {"inner_race_od_mm": 75.9, "inner_sidewall_mm": 75.9, "outer_sidewall_mm": 89.15}
    design["parameters"] = {**design["parameters"], **parameters, "ball_d_mm": dw,
                            "inner_groove_radius_mm": .54 * dw, "outer_groove_radius_mm": .52 * dw}
    return parse_request(design), geometry


@pytest.mark.parametrize(("kind", "source", "digest", "outer_load", "inner_stress", "nonfinite"), [
    ("DGB", DGB, DGB_SHA256, 2251, 3402, 15),
    ("ACB", ACB, ACB_SHA256, 954.5, 1968, 15),
    ("N222", GOLDEN.parent, GOLDEN_SHA256, 16750, 1138, 5),
])
def test_windows_original_exe_full_http_chain(tmp_path, kind, source, digest, outer_load, inner_stress, nonfinite):
    resources = Path(os.environ.get("ROBAS_WINDOWS_RESOURCES", r"C:\RollBearing"))
    matches = sorted(source.rglob("DATA.txt"))
    if platform.system() != "Windows" or not matches or not (resources / "exe" / "RoBAS_v2.exe").is_file():
        pytest.skip("requires local Windows RoBAS EXE and private original DATA")
    original = matches[0]
    assert sha256(original.read_bytes()).hexdigest() == digest
    request, geometry = _golden_design(kind)
    manifest, reference = _profile(tmp_path, original.read_bytes(), request, digest)
    with _server(tmp_path, resources, manifest) as server:
        status, result = _request(server, "POST", ROUTE, _body(request, geometry))
    assert status == 201, result
    assert result["request_hash"] == request.request_hash and result["profile"]["sha256"] == digest
    parsed = result["result"]
    assert parsed["source_binding"]["status"] == "HASH_VERIFIED"
    assert parsed["execution"]["status"] == "EXITED_ZERO" and parsed["convergence"]["status"] == "UNKNOWN"
    assert parsed["contacts"][0]["outer"]["load"]["value"] == pytest.approx(outer_load)
    assert parsed["contacts"][0]["inner"]["stress"]["value"] == pytest.approx(inner_stress)
    assert len(parsed["nonfinite_evidence"]) == nonfinite
    baseline = parse_static_results(original.parent, family="roller" if kind == "N222" else "ball")
    for field in ("contacts", "stiffness_sweep", "summary", "nonfinite_evidence"):
        assert parsed[field] == baseline[field], field
    if kind == "N222":
        assert parsed["files"] == baseline["files"]
    assert sha256(reference.read_bytes()).hexdigest() == sha256(original.read_bytes()).hexdigest() == digest

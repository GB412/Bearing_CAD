"""Loopback endpoint for source-backed RoBAS DGB initial geometry."""
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from bearing_cad.api import make_server


def _request(server, method, path, payload=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    headers = {}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
        headers["Origin"] = origin or f"http://127.0.0.1:{server.server_port}"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    result = json.loads(response.read())
    status = response.status
    conn.close()
    return status, result


def _start(root, resources=None):
    server = make_server(port=0, artifacts_root=root, robas_resources=resources)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


def _resources(root):
    folder = root / "Resource"
    folder.mkdir(parents=True)
    (folder / "BallDB.csv").write_text(
        "diameter(mm)\n8\n8.33438\n8.5\n", encoding="utf-8")
    return root


def test_dgb_sizing_endpoint_returns_source_backed_candidate_profile():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        resources = _resources(root / "RoBAS_Resources")
        server, thread = _start(root / "artifacts", resources)
        try:
            status, health = _request(server, "GET", "/api/v2/cad/status")
            assert status == 200
            assert health["robas_sizing_available"] is True
            status, profile = _request(server, "POST", "/api/v2/cad/sizing/dgb-geometry", {
                "bearing_type": "rolling.deep_groove_ball",
                "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
            })
            assert status == 200
            assert profile["candidate_only"] is True
            assert profile["parameters"]["ball_d_mm"] == 8.33438
            assert profile["parameters"]["ball_count"] == 11
        finally:
            _stop(server, thread)


def test_dgb_sizing_endpoint_fails_closed_without_robas_resources():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        server, thread = _start(root / "artifacts")
        try:
            status, health = _request(server, "GET", "/api/v2/cad/status")
            assert status == 200
            assert health["robas_sizing_available"] is False
            status, result = _request(server, "POST", "/api/v2/cad/sizing/dgb-geometry", {
                "bearing_type": "rolling.deep_groove_ball",
                "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
            })
            assert status == 503
            assert result["error"]["error_code"] == "ROBAS_RESOURCES_UNAVAILABLE"
        finally:
            _stop(server, thread)


def test_dgb_sizing_endpoint_rejects_extra_fields_and_cross_origin_posts():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        resources = _resources(root / "RoBAS_Resources")
        server, thread = _start(root / "artifacts", resources)
        payload = {
            "bearing_type": "rolling.deep_groove_ball",
            "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
        }
        try:
            status, result = _request(server, "POST", "/api/v2/cad/sizing/dgb-geometry",
                                      {**payload, "guess": True})
            assert status == 422
            assert result["error"]["error_code"] == "PARAMETER_INVALID"
            status, result = _request(server, "POST", "/api/v2/cad/sizing/dgb-geometry",
                                      payload, origin="http://evil.example")
            assert status == 403
            assert result["error"]["error_code"] == "ORIGIN_FORBIDDEN"
        finally:
            _stop(server, thread)


def test_dgb_sizing_endpoint_rejects_undefined_legacy_clearance_range():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        resources = _resources(root / "RoBAS_Resources")
        server, thread = _start(root / "artifacts", resources)
        try:
            status, result = _request(server, "POST", "/api/v2/cad/sizing/dgb-geometry", {
                "bearing_type": "rolling.deep_groove_ball",
                "bore_d_mm": 200, "outside_d_mm": 228, "width_mm": 15,
            })
            assert status == 422
            assert result["error"]["error_code"] == "PARAMETER_INVALID"
            assert "radial-clearance table is undefined" in result["error"]["message"]
        finally:
            _stop(server, thread)

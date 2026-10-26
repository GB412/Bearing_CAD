"""HTTP-level acceptance tests for the local CAD V2 service."""
import hashlib
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread, Event
import unittest
from unittest.mock import patch

from bearing_cad.api import make_server
from test_contracts import deep_request


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.server = make_server(port=0, artifacts_root=Path(self.tmp.name))
        self.port = self.server.server_port
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self, method, path, payload=None, *, origin=True, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        opts = dict(headers or {})
        if origin:
            opts.setdefault("Origin", f"http://127.0.0.1:{self.port}")
        if payload is not None and not isinstance(payload, (str, bytes)):
            payload = json.dumps(payload)
        if payload is not None:
            opts.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=payload, headers=opts)
        reply = conn.getresponse()
        body = reply.read()
        code, hdrs = reply.status, dict(reply.getheaders())
        conn.close()
        if hdrs.get("Content-Type", "").startswith("application/json") and body:
            return code, hdrs, json.loads(body)
        return code, hdrs, body

    def test_status_and_unknown_job(self):
        code, headers, payload = self.request("GET", "/api/v2/cad/status")
        self.assertEqual(code, 200)
        self.assertEqual(payload["mode"], "loopback_synchronous")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("GET", "/api/v2/cad/jobs/" + "0" * 32)[0], 404)
        self.assertEqual(self.request("GET", "/api/v2/cad/../cad/status")[0], 404)

    def test_host_and_origin(self):
        with self.assertRaises(ValueError):
            make_server(host="0.0.0.0")
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", deep_request(), origin=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", deep_request(),
                                      headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/v2/cad/status", origin=False,
                                      headers={"Host": "evil.example"})[0], 403)

    def test_malformed_invalid_and_resource_limits(self):
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", "{oops")[0], 400)
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", '{"x":NaN}')[0], 400)
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs",
                                      '{"schema_version":"a","schema_version":"b"}')[0], 400)
        invalid = deep_request()
        invalid["approval_state"] = "CONFIRMED"
        code, _, payload = self.request("POST", "/api/v2/cad/jobs", invalid)
        self.assertEqual(code, 422)
        self.assertEqual(payload["error"]["field_path"], "/approval_state")
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", deep_request(),
                                      headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", "x" * 17000)[0], 413)
        invalid = deep_request()
        invalid["detail_level"] = "detailed"
        self.assertEqual(self.request("POST", "/api/v2/cad/jobs", invalid)[0], 422)
        invalid = deep_request()
        invalid["parameters"]["ball_count"] = 65
        code, _, payload = self.request("POST", "/api/v2/cad/jobs", invalid)
        self.assertEqual((code, payload["error"]["error_code"]), (422, "RESOURCE_LIMIT"))

    def test_real_cad_generation_manifest_and_download(self):
        code, _, created = self.request("POST", "/api/v2/cad/jobs", deep_request())
        self.assertEqual(code, 201)
        self.assertEqual(created["status"], "succeeded")
        self.assertEqual(self.request("GET", created["job_url"])[2]["status"], "succeeded")
        code, _, artifact = self.request("GET", created["manifest_url"])
        self.assertEqual(code, 200)
        self.assertEqual(artifact["manifest"]["completeness"], "CAGE_OMITTED")
        self.assertEqual(len(artifact["manifest"]["instances"]), 13)
        uri = artifact["file_urls"]["bearing_assembly.step"]
        code, headers, contents = self.request("GET", uri)
        self.assertEqual(code, 200)
        self.assertEqual(hashlib.sha256(contents).hexdigest(),
                         artifact["manifest"]["files"]["bearing_assembly.step"]["sha256"])
        self.assertEqual(self.request("HEAD", uri)[0], 200)
        self.assertEqual(self.request("GET", uri + "/../design_snapshot.json")[0], 404)
        self.assertEqual(self.request("GET", created["manifest_url"] + "/files/hidden.dll")[0], 404)

        # Integrity validation remains mandatory on every download.
        generated = next(Path(self.tmp.name).iterdir()) / "bearing_assembly.step"
        with generated.open("ab") as stream:
            stream.write(b"tampered")
        self.assertEqual(self.request("GET", uri)[0], 404)

        # Job IDs are scoped to the server instance, even with shared disk cache.
        other = make_server(port=0, artifacts_root=Path(self.tmp.name))
        worker = Thread(target=other.serve_forever, daemon=True)
        worker.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", other.server_port, timeout=5)
            conn.request("GET", created["manifest_url"])
            response = conn.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            conn.close()
        finally:
            other.shutdown()
            other.server_close()
            worker.join(timeout=5)

    def test_failure_redaction_and_job_state(self):
        with patch("bearing_cad.api.generate_bundle", side_effect=RuntimeError("sensitive_detail")):
            code, _, payload = self.request("POST", "/api/v2/cad/jobs", deep_request())
        self.assertEqual(code, 500)
        self.assertNotIn("sensitive_detail", str(payload))
        job = self.request("GET", "/api/v2/cad/jobs/" + payload["job_id"])[2]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "CAD_GENERATION_FAILED")

    def test_busy(self):
        entered, release = Event(), Event()
        statuses = []
        def blocking(*args, **kwargs):
            entered.set()
            release.wait(timeout=10)
            raise RuntimeError("expected mock failure")
        def submit():
            statuses.append(self.request("POST", "/api/v2/cad/jobs", deep_request())[0])
        with patch("bearing_cad.api.generate_bundle", side_effect=blocking):
            worker = Thread(target=submit)
            worker.start()
            self.assertTrue(entered.wait(timeout=5))
            code, _, payload = self.request("POST", "/api/v2/cad/jobs", deep_request())
            self.assertEqual((code, payload["error"]["error_code"]), (503, "BUSY"))
            release.set()
            worker.join(timeout=10)
        self.assertEqual(statuses, [500])

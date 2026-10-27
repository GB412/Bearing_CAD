"""HTTP API must route cylindrical configurations without misparsing text fields."""
import http.client
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from bearing_cad.api import make_server
from test_cylindrical_roller import cylindrical_request


class CylindricalApiTests(unittest.TestCase):
    def test_http_generated_step_and_manifest(self):
        with TemporaryDirectory() as folder:
            server = make_server(port=0, artifacts_root=Path(folder))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = cylindrical_request("NUP")
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=90)
                conn.request("POST", "/api/v2/cad/jobs", body=json.dumps(request),
                             headers={"Content-Type": "application/json",
                                      "Origin": f"http://127.0.0.1:{server.server_port}"})
                response = conn.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 201, body)
                self.assertEqual(body["status"], "succeeded")
                conn.request("GET", body["manifest_url"])
                artifact_response = conn.getresponse()
                artifact = json.loads(artifact_response.read())
                self.assertEqual(artifact_response.status, 200)
                manifest = artifact["manifest"]
                self.assertEqual(manifest["configuration"], "NUP")
                self.assertEqual(len(manifest["instances"]), 14)
                conn.request("GET", artifact["file_urls"]["bearing_assembly.step"])
                step_response = conn.getresponse()
                self.assertEqual(step_response.status, 200)
                self.assertGreater(len(step_response.read()), 1000)
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=10)

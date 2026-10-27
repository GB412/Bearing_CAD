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
    def test_http_and_parser_reject_bad_detail_and_oversized_cage(self):
        from bearing_cad.contracts import ContractError, parse_request
        oversized = cylindrical_request("NUP")
        oversized["cage"] = {"kind":"cylindrical_window", "inner_d_mm":1001,
                            "outside_d_mm":1002, "width_mm":16, "pocket_clearance_mm":.15}
        unsupported = cylindrical_request("NU")
        unsupported["detail_level"]="envelope"
        cases=[(oversized,"RESOURCE_LIMIT","/cage/inner_d_mm"),
               (unsupported,"NOT_SUPPORTED","/detail_level")]
        with TemporaryDirectory() as folder:
            server=make_server(port=0,artifacts_root=Path(folder))
            thread=Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                for payload,code,field in cases:
                    with self.subTest(code=code):
                        with self.assertRaises(ContractError) as failure:
                            parse_request(payload)
                        self.assertEqual(failure.exception.error_code,code)
                        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=10)
                        conn.request("POST","/api/v2/cad/jobs",body=json.dumps(payload),
                                     headers={"Content-Type":"application/json",
                                              "Origin":f"http://127.0.0.1:{server.server_port}"})
                        response=conn.getresponse()
                        result=json.loads(response.read())
                        self.assertEqual(response.status,422)
                        self.assertEqual(result["error"]["error_code"],code)
                        self.assertEqual(result["error"]["field_path"],field)
                        conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=10)


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
                conn.close()  # POST response sets Connection: close.
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=90)
                conn.request("GET", body["manifest_url"])
                artifact_response = conn.getresponse()
                artifact = json.loads(artifact_response.read())
                self.assertEqual(artifact_response.status, 200)
                manifest = artifact["manifest"]
                self.assertEqual(manifest["configuration"], "NUP")
                self.assertEqual(len(manifest["instances"]), 14)
                conn.close()
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=90)
                conn.request("GET", artifact["file_urls"]["bearing_assembly.step"])
                step_response = conn.getresponse()
                self.assertEqual(step_response.status, 200)
                self.assertGreater(len(step_response.read()), 1000)
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=10)

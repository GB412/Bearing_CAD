"""Optional same-origin rolling workbench static serving (no separate Vite proxy)."""
import http.client
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from bearing_cad.api import make_server


class WorkbenchStaticTests(unittest.TestCase):
    def test_static_is_opt_in_and_allowlisted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "rolling.html").write_text("<!doctype html><title>V2 workbench</title>", encoding="utf-8")
            (root / "assets" / "rolling-42.js").write_text("console.log('v2')", encoding="utf-8")
            (root / "assets" / "rolling-42.css").write_text("body{}", encoding="utf-8")
            (root / "index.html").write_text("<title>Legacy demo</title>", encoding="utf-8")
            server = make_server(port=0, artifacts_root=root / "cad", static_root=root)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def get(path, method="GET", host=None):
                    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=8)
                    client.request(method, path, headers={"Host": host or f"127.0.0.1:{server.server_port}"})
                    reply = client.getresponse()
                    result = reply.status, dict(reply.getheaders()), reply.read()
                    client.close()
                    return result
                self.assertEqual(get("/rolling.html")[0], 200)
                self.assertIn(b"V2 workbench", get("/")[2])
                self.assertEqual(get("/assets/rolling-42.js")[0], 200)
                self.assertEqual(get("/assets/rolling-42.css")[0], 200)
                self.assertEqual(get("/rolling.html", "HEAD")[2], b"")
                self.assertEqual(get("/index.html")[0], 404)
                self.assertEqual(get("/.env")[0], 404)
                self.assertEqual(get("/assets/../index.html")[0], 404)
                self.assertEqual(get("/assets/%2e%2e/index.html")[0], 404)
                self.assertEqual(get("/rolling.html?x=1")[0], 404)
                self.assertEqual(get("/rolling.html", host="evil.example")[0], 403)
                self.assertEqual(get("/api/v2/cad/status")[0], 200)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=8)

    def test_missing_static_build_fails_fast(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                make_server(port=0, artifacts_root=Path(root)/"cad", static_root=Path(root))

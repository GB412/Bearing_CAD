import tempfile
import unittest
from pathlib import Path

from bearing_cad.contracts import parse_request
from bearing_cad.artifacts import generate_bundle, verify_bundle
from test_contracts import deep_request


class ArtifactsTests(unittest.TestCase):
    def test_bundle_cache_roundtrip_and_tamper(self):
        data = deep_request()
        data["cage"] = {"kind": "simplified_annular", "inner_d_mm": 48,
                        "outside_d_mm": 60, "width_mm": 11, "pocket_clearance_mm": .25}
        request = parse_request(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = generate_bundle(request, root)
            self.assertEqual(path, generate_bundle(request, root))
            report = verify_bundle(path)
            self.assertEqual(report["request_hash"], request.request_hash)
            self.assertEqual(report["completeness"], "SIMPLIFIED_CAGE")
            self.assertEqual(len(report["instances"]), 14)
            self.assertEqual(len(report["parts"]), 4)
            self.assertEqual(len(report["files"]), 6)
            self.assertFalse(any(p.name.startswith(".cad-v2-staging-") for p in root.iterdir()))
            step = path / "bearing_assembly.step"
            step.write_bytes(step.read_bytes() + b"invalid-footer")
            with self.assertRaises(ValueError):
                verify_bundle(path)
            with self.assertRaises(ValueError):
                generate_bundle(request, root)

    def test_cage_omitted_is_explicit_in_manifest(self):
        request = parse_request(deep_request())
        with tempfile.TemporaryDirectory() as tmp:
            manifest = verify_bundle(generate_bundle(request, Path(tmp)))
            self.assertEqual(manifest["completeness"], "CAGE_OMITTED")
            self.assertEqual(len(manifest["instances"]), 13)

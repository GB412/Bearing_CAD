"""RoBAS CylinderPocketCage-inspired windows: actual OCCT solids and STEP."""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import cadquery as cq

from bearing_cad.artifacts import generate_bundle, verify_bundle
from bearing_cad.contracts import ContractError, parse_request
from bearing_cad.cylindrical_roller import build_cylindrical_roller
from bearing_cad.geometry_checks import inspect_solid, interference_volume
from test_cylindrical_roller import cylindrical_request


def with_cage(configuration="NU"):
    data = cylindrical_request(configuration)
    data["cage"] = {"kind": "cylindrical_window", "inner_d_mm": 52.6,
                    "outside_d_mm": 55.4, "width_mm": 16,
                    "pocket_clearance_mm": .15}
    return data


class CylindricalWindowCageTests(unittest.TestCase):
    def test_five_variants_window_cage_and_geometry(self):
        for kind in ("N", "NU", "NJ", "NF", "NUP"):
            with self.subTest(kind=kind):
                model = build_cylindrical_roller(parse_request(with_cage(kind)))
                parts = {part.component_id: part.shape for part in model.components}
                cage = parts["cage"]
                self.assertTrue(inspect_solid(cage).valid)
                self.assertEqual(len(model.instances), 15 if kind == "NUP" else 14)
                self.assertIn("cage", [p.component_id for p in model.components])
                # A window is a true absence of material at each roller center.
                for i in range(11):
                    theta = 2 * math.pi * i / 11
                    hole = (27 * math.cos(theta), 27 * math.sin(theta), 0)
                    bridge = (27 * math.cos(theta + math.pi / 11),
                              27 * math.sin(theta + math.pi / 11), 0)
                    self.assertFalse(cage.val().isInside(hole))
                    self.assertTrue(cage.val().isInside(bridge))
                # Axial rims remain present on both sides.
                self.assertTrue(cage.val().isInside((27, 0, 7.5)))
                self.assertTrue(cage.val().isInside((27, 0, -7.5)))
                for key, part in parts.items():
                    if key != "cage" and key != "roller":
                        self.assertLess(interference_volume(cage, part), 1e-6)
                self.assertLess(interference_volume(cage, parts["roller"].translate((27, 0, 0))), 1e-6)

    def test_export_cage_step_roundtrip_and_manifest(self):
        for kind in ("NU", "NUP"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                request = parse_request(with_cage(kind))
                output = generate_bundle(request, Path(root))
                meta = verify_bundle(output)
                self.assertEqual(meta["completeness"], "CYLINDRICAL_WINDOW_CAGE")
                self.assertIn("cage.stl", meta["files"])
                self.assertEqual(len(meta["instances"]), 15 if kind == "NUP" else 14)
                imported = cq.importers.importStep(str(output / "bearing_assembly.step")).solids().vals()
                self.assertEqual(len(imported), len(meta["instances"]))
                self.assertTrue(all(s.isValid() for s in imported))
                self.assertEqual(generate_bundle(request, Path(root)), output)

    def test_invalid_window_and_unsupported_cage_kind(self):
        variants = (
            {"inner_d_mm": 50},
            {"outside_d_mm": 58},
            {"width_mm": 12.2},
            {"width_mm": 21},
            {"pocket_clearance_mm": 4},
            {"kind": "simplified_annular"},
        )
        for change in variants:
            with self.subTest(change=change):
                request = with_cage()
                request["cage"].update(change)
                with self.assertRaises(ContractError):
                    build_cylindrical_roller(parse_request(request))

    def test_unmodified_cage_free_request_remains_compatible(self):
        model = build_cylindrical_roller(parse_request(cylindrical_request("NU")))
        self.assertNotIn("cage", {p.component_id for p in model.components})
        self.assertEqual(len(model.instances), 13)

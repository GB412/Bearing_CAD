"""Radial straight-pocket cage migrated from RoBAS intent with STEP gate."""
from __future__ import annotations
import math
import tempfile
from pathlib import Path
import unittest

import cadquery as cq

from bearing_cad.angular_contact import build_angular_contact
from bearing_cad.artifacts import generate_bundle, verify_bundle
from bearing_cad.contracts import ContractError, parse_request
from bearing_cad.geometry_checks import inspect_solid, interference_volume
from test_angular_contact import request as angular_request


def angular_with_cage(alpha=25):
    data = angular_request(alpha)
    data["cage"] = {"kind": "straight_pocket", "inner_d_mm": 51,
                    "outside_d_mm": 57, "width_mm": 11,
                    "pocket_clearance_mm": .15}
    return data


class StraightPocketCageTests(unittest.TestCase):
    def test_radial_windows_are_real_and_leave_axial_bridge(self):
        for angle in (15, 25, 40):
            with self.subTest(angle=angle):
                m = build_angular_contact(parse_request(angular_with_cage(angle)))
                parts = {p.component_id: p.shape for p in m.components}
                cage = parts["cage"]
                self.assertTrue(inspect_solid(cage).valid)
                self.assertEqual(len(m.components), 4)
                self.assertEqual(len(m.instances), 14)
                for i in range(11):
                    theta = math.pi / 2 + 2 * math.pi * i / 11
                    center = (27 * math.cos(theta), 27 * math.sin(theta), 0)
                    bridge = (27 * math.cos(theta + math.pi / 11),
                              27 * math.sin(theta + math.pi / 11), 0)
                    self.assertFalse(cage.val().isInside(center))
                    self.assertTrue(cage.val().isInside(bridge))
                self.assertTrue(cage.val().isInside((0, 27, 5.3)))
                self.assertTrue(cage.val().isInside((0, 27, -5.3)))
                for name, shape in parts.items():
                    if name != "cage" and name != "ball":
                        self.assertLess(interference_volume(cage, shape), 1e-6)
                self.assertLess(interference_volume(cage, parts["ball"].translate((0, 27, 0))), 1e-6)

    def test_step_all_solids_valid_and_cache_identity(self):
        with tempfile.TemporaryDirectory() as root:
            data = parse_request(angular_with_cage())
            target = generate_bundle(data, Path(root))
            manifest = verify_bundle(target)
            self.assertEqual(manifest["completeness"], "STRAIGHT_POCKET_CAGE")
            self.assertIn("cage.stl", manifest["files"])
            self.assertEqual(len(manifest["instances"]), 14)
            reread = cq.importers.importStep(str(target / "bearing_assembly.step")).solids().vals()
            self.assertEqual(len(reread), 14)
            self.assertTrue(all(s.isValid() for s in reread))
            plain = generate_bundle(parse_request(angular_request()), Path(root))
            self.assertNotEqual(target, plain)
            self.assertEqual(target, generate_bundle(data, Path(root)))

    def test_invalid_cage_geometry_and_kind_fail_closed(self):
        for changes in (
            {"inner_d_mm": 48},
            {"outside_d_mm": 61},
            {"width_mm": 8},
            {"width_mm": 16},
            {"pocket_clearance_mm": 4},
            {"kind": "cylindrical_window"},
        ):
            with self.subTest(changes=changes):
                payload = angular_with_cage()
                payload["cage"].update(changes)
                with self.assertRaises(ContractError):
                    build_angular_contact(parse_request(payload))

"""A real two-half/hemisphere-rivet assembly inspired by RoBAS StampingCage."""
from __future__ import annotations
import math
import tempfile
import unittest
from pathlib import Path

import cadquery as cq

from bearing_cad.contracts import ContractError, parse_request
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.artifacts import generate_bundle, verify_bundle
from bearing_cad.geometry_checks import inspect_solid, interference_volume
from test_contracts import deep_request


def stamping_request(scale=1):
    data = deep_request()
    for key, value in list(data["parameters"].items()):
        if key != "ball_count":
            data["parameters"][key] = value * scale
    data["cage"] = {
        "kind": "stamping_double_half",
        "inner_d_mm": 48 * scale,
        "outside_d_mm": 60 * scale,
        "width_mm": 11.5 * scale,
        "pocket_clearance_mm": .15 * scale,
        "board_thickness_mm": .7 * scale,
        "rivet_shaft_d_mm": 1.0 * scale,
        "rivet_head_d_mm": 1.6 * scale,
        "rivet_hole_clearance_mm": .05 * scale,
    }
    return data


class StampingCageTests(unittest.TestCase):
    def test_split_halves_and_rivets_are_real_separate_solids(self):
        for scale in (.75, 1., 1.5):
            with self.subTest(scale=scale):
                model = build_deep_groove(parse_request(stamping_request(scale)))
                self.assertEqual(len(model.instances), 26)
                self.assertEqual(len(model.components), 6)
                shapes = {x.component_id: x.shape for x in model.components}
                self.assertEqual(set(shapes), {"inner_ring","outer_ring","ball",
                                               "cage_upper","cage_lower","rivet"})
                self.assertTrue(all(inspect_solid(s).valid for s in shapes.values()))
                self.assertLess(interference_volume(shapes["cage_upper"],shapes["cage_lower"]),1e-6)
                ball_locations = [x.translation_mm for x in model.instances if x.component_id=="ball"]
                rivet_locations = [x.translation_mm for x in model.instances if x.component_id=="rivet"]
                self.assertEqual(len(ball_locations),11)
                self.assertEqual(len(rivet_locations),11)
                self.assertNotEqual(set(ball_locations),set(rivet_locations))
                self.assertAlmostEqual(math.hypot(*rivet_locations[0][:2]),27*scale,places=7)
                self.assertLess(interference_volume(shapes["rivet"].translate(rivet_locations[0]),
                                                     shapes["ball"].translate(ball_locations[0])),1e-6)
                for name in ("cage_upper","cage_lower"):
                    self.assertLess(interference_volume(shapes[name],shapes["inner_ring"]),1e-6)
                    self.assertLess(interference_volume(shapes[name],shapes["outer_ring"]),1e-6)

    def test_step_manifest_roundtrip_and_legacy_compatibility(self):
        with tempfile.TemporaryDirectory() as root:
            request=parse_request(stamping_request())
            bundle=generate_bundle(request,Path(root))
            manifest=verify_bundle(bundle)
            self.assertEqual(manifest["completeness"],"STAMPING_DOUBLE_HALF")
            self.assertEqual(len(manifest["instances"]),26)
            for p in ("cage_upper.stl","cage_lower.stl","rivet.stl"):
                self.assertIn(p,manifest["files"])
            solids=cq.importers.importStep(str(bundle/"bearing_assembly.step")).solids().vals()
            self.assertEqual(len(solids),26)
            self.assertTrue(all(s.isValid() for s in solids))
            self.assertEqual(bundle,generate_bundle(request,Path(root)))
            old=generate_bundle(parse_request(deep_request()),Path(root))
            self.assertNotEqual(bundle,old)

    def test_reject_thin_rivets_and_bad_cage_geometry(self):
        changes=({"inner_d_mm":46},{"outside_d_mm":62},{"width_mm":9},
                 {"pocket_clearance_mm":1},{"rivet_head_d_mm":.5},
                 {"rivet_head_d_mm":7},{"kind":"not_existing"})
        for update in changes:
            with self.subTest(update=update):
                data=stamping_request();data["cage"].update(update)
                with self.assertRaises(ContractError):
                    build_deep_groove(parse_request(data))

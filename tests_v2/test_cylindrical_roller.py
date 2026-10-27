"""Parameterized CRB N/NU/NJ/NF/NUP exact B-Rep regression."""
from __future__ import annotations
import math
import tempfile
from pathlib import Path
import unittest

import cadquery as cq

from bearing_cad.contracts import ContractError, parse_request
from bearing_cad.cylindrical_roller import build_cylindrical_roller
from bearing_cad.geometry_checks import inspect_solid
from bearing_cad.artifacts import generate_bundle, verify_bundle


def cylindrical_request(config="NU", factor=1.):
    dimensions = {
        "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 18,
        "roller_d_mm": 8, "roller_length_mm": 12, "pitch_d_mm": 54,
        "roller_count": 11, "configuration": config,
        "radial_clearance_mm": 0.05, "axial_clearance_mm": 0.4,
        "rib_width_mm": 2, "inner_rib_tip_d_mm": 52, "outer_rib_tip_d_mm": 56,
    }
    for key in dimensions:
        if key not in ("roller_count", "configuration"):
            dimensions[key] *= factor
    return {"schema_version": "bearing-cad.request.v1",
            "bearing_type": "rolling.cylindrical_roller", "unit": "mm",
            "detail_level": "functional", "geometry_strategy": "explicit",
            "parameters": dimensions}


class CylindricalRollerTests(unittest.TestCase):
    def test_configuration_parts_and_step_roundtrip(self):
        for config in ("N", "NU", "NJ", "NF", "NUP"):
            with self.subTest(config=config):
                model = build_cylindrical_roller(parse_request(cylindrical_request(config)))
                expected = 14 if config == "NUP" else 13
                self.assertEqual(len(model.instances), expected)
                self.assertEqual(len(model.components), 4 if config == "NUP" else 3)
                self.assertEqual([c.component_id for c in model.components[:3]],
                                 ["inner_ring", "outer_ring", "roller"])
                for component in model.components:
                    self.assertTrue(inspect_solid(component.shape).valid)
                assembly = cq.Assembly(name="roller_bearing")
                lookup = {part.component_id: part.shape for part in model.components}
                for inst in model.instances:
                    assembly.add(lookup[inst.component_id], name=inst.instance_id,
                                 loc=cq.Location(cq.Vector(*inst.translation_mm)))
                with tempfile.TemporaryDirectory() as temp:
                    step = Path(temp) / "cylindrical.step"
                    assembly.save(str(step))
                    reread = cq.importers.importStep(str(step)).solids().vals()
                    self.assertEqual(len(reread), expected)
                    self.assertTrue(all(x.isValid() for x in reread))
                if config == "NUP":
                    self.assertIn("loose_rib", lookup)
                    self.assertAlmostEqual(inspect_solid(lookup["inner_ring"]).extents_mm[2], 16, places=4)
                else:
                    self.assertNotIn("loose_rib", lookup)

    def test_five_configuration_geometry_not_aliases(self):
        profiles = {}
        for config in ("N", "NU", "NJ", "NF", "NUP"):
            model = build_cylindrical_roller(parse_request(cylindrical_request(config)))
            profiles[config] = tuple(round(inspect_solid(p.shape).volume_mm3, 4)
                                      for p in model.components)
        self.assertNotEqual(profiles["N"], profiles["NU"])
        self.assertNotEqual(profiles["NU"], profiles["NJ"])
        self.assertNotEqual(profiles["NJ"], profiles["NF"])
        self.assertNotEqual(profiles["NF"], profiles["NUP"])

    def test_uniform_scale_and_roller_spacing(self):
        for factor in (0.75, 1, 1.5):
            with self.subTest(factor=factor):
                model = build_cylindrical_roller(parse_request(cylindrical_request("NUP", factor)))
                centers = [i.translation_mm for i in model.instances if i.component_id == "roller"]
                self.assertEqual(len(centers), 11)
                self.assertEqual(len(set(centers)), 11)
                self.assertTrue(all(abs(math.hypot(x, y)-27*factor) < 1e-9 for x, y, z in centers))
                self.assertTrue(all(abs(z)<1e-10 for x, y, z in centers))

    def test_invalid_design_rejected(self):
        changes = (
            {"radial_clearance_mm": 4},
            {"inner_rib_tip_d_mm": 58},
            {"outer_rib_tip_d_mm": 51},
            {"rib_width_mm": 4},
            {"axial_clearance_mm": 3},
            {"roller_count": 30},
            {"roller_length_mm": 19},
            {"configuration": "bad"},
        )
        for change in changes:
            with self.subTest(change=change):
                request = cylindrical_request("NU")
                request["parameters"].update(change)
                with self.assertRaises(ContractError):
                    build_cylindrical_roller(parse_request(request))
        wrong = cylindrical_request()
        wrong["cage"] = {"kind": "simplified_annular"}
        with self.assertRaises(ContractError):
            parse_request(wrong)

    def test_content_addressed_artifact_and_legacy_separation(self):
        request = parse_request(cylindrical_request("NUP"))
        with tempfile.TemporaryDirectory() as folder:
            first = generate_bundle(request, Path(folder))
            manifest = verify_bundle(first)
            self.assertEqual(manifest["bearing_type"], "rolling.cylindrical_roller")
            self.assertEqual(manifest["configuration"], "NUP")
            self.assertEqual(manifest["completeness"], "CAGE_OMITTED")
            self.assertEqual(len(manifest["instances"]), 14)
            self.assertIn("loose_rib.stl", manifest["files"])
            self.assertEqual(first, generate_bundle(request, Path(folder)))
            other = generate_bundle(parse_request(cylindrical_request("NU")), Path(folder))
            self.assertNotEqual(first, other)

"""Real OCCT deep-groove fixtures; concept design, not manufacturer geometry."""
import tempfile
from pathlib import Path
import unittest

import cadquery as cq

from bearing_cad.contracts import parse_request, ContractError
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.geometry_checks import inspect_solid
from test_contracts import deep_request


class DeepGrooveTests(unittest.TestCase):
    def test_multiple_dimensions_and_real_assembly_step(self):
        # Geometrically similar fixtures, not independent design certifications.
        for factor in (0.75, 1.0, 1.5):
            with self.subTest(scale=factor):
                data = deep_request()
                for key, value in data["parameters"].items():
                    if key != "ball_count":
                        data["parameters"][key] = value * factor
                model = build_deep_groove(parse_request(data))
                self.assertEqual(len(model.components), 3)
                self.assertEqual(len(model.instances), 13)
                self.assertTrue(inspect_solid(model.components[0].shape).valid)
                self.assertTrue(inspect_solid(model.components[1].shape).valid)
                assembly = cq.Assembly(name="deep_groove")
                definitions = {part.component_id: part.shape for part in model.components}
                for instance in model.instances:
                    assembly.add(
                        definitions[instance.component_id], name=instance.instance_id,
                        loc=cq.Location(cq.Vector(*instance.translation_mm)),
                    )
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / "bearing.step"
                    assembly.save(str(path))
                    self.assertGreater(path.stat().st_size, 1000)
                    reread = cq.importers.importStep(str(path))
                    self.assertEqual(len(reread.solids().vals()), 13)

    def test_overlapping_balls_and_bad_curvature_rejected(self):
        data = deep_request()
        data["parameters"]["ball_count"] = 30
        with self.assertRaises(ContractError):
            build_deep_groove(parse_request(data))
        data = deep_request()
        data["parameters"]["inner_groove_radius_mm"] = 2
        with self.assertRaises(ContractError):
            build_deep_groove(parse_request(data))

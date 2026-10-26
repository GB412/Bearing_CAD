"""Functional annular ball-pocket cage; not detailed stamped cage geometry."""
import tempfile
from pathlib import Path
import unittest

import cadquery as cq

from bearing_cad.contracts import parse_request, ContractError
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.geometry_checks import inspect_solid
from test_contracts import deep_request


class SimplifiedCageTests(unittest.TestCase):
    def test_pocket_cage_and_step(self):
        for factor in (0.75, 1.0, 1.5):
            with self.subTest(factor=factor):
                data = deep_request()
                for key, val in data["parameters"].items():
                    if key != "ball_count":
                        data["parameters"][key] = val * factor
                data["cage"] = {
                    "kind": "simplified_annular",
                    "inner_d_mm": 48 * factor,
                    "outside_d_mm": 60 * factor,
                    "width_mm": 9 * factor,
                    "pocket_clearance_mm": 0.25 * factor,
                }
                request = parse_request(data)
                without = deep_request()
                for key, val in without["parameters"].items():
                    if key != "ball_count":
                        without["parameters"][key] = val * factor
                self.assertNotEqual(request.request_hash, parse_request(without).request_hash)
                model = build_deep_groove(request)
                self.assertEqual(len(model.components), 4)
                self.assertEqual(len(model.instances), 14)
                cage = next(x.shape for x in model.components if x.component_id == "cage")
                self.assertTrue(inspect_solid(cage).valid)
                assembly = cq.Assembly(name="simplified_cage_bearing")
                definitions = {part.component_id: part.shape for part in model.components}
                for instance in model.instances:
                    assembly.add(definitions[instance.component_id], name=instance.instance_id,
                                 loc=cq.Location(cq.Vector(*instance.translation_mm)))
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "bearing.step"
                    assembly.save(str(path))
                    self.assertEqual(len(cq.importers.importStep(str(path)).solids().vals()), 14)

    def test_invalid_and_unimplemented_cage(self):
        for changes in ({"kind": "detailed_stamping"}, {"width_mm": 2}, {"inner_d_mm": 46}):
            with self.subTest(changes=changes):
                data = deep_request()
                data["cage"] = {"kind": "simplified_annular", "inner_d_mm": 48,
                                "outside_d_mm": 60, "width_mm": 9, "pocket_clearance_mm": 0.25}
                data["cage"].update(changes)
                with self.assertRaises(ContractError):
                    build_deep_groove(parse_request(data))
        data = deep_request()
        data["cage"] = None
        with self.assertRaises(ContractError):
            parse_request(data)

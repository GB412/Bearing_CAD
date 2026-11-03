"""RoBAS-compatible plain rollers and separately identified CAD enhancements."""
import math
import tempfile
import unittest
from pathlib import Path

import cadquery as cq

from bearing_cad.geometry import profiled_cylindrical_roller
from bearing_cad.geometry_checks import inspect_solid
from bearing_cad.cylindrical_roller import build_cylindrical_roller
from bearing_cad.contracts import ContractError, parse_request
from test_cylindrical_roller import cylindrical_request


class RollerProfileTests(unittest.TestCase):
    def test_original_plain_roller_volume_unchanged(self):
        plain = profiled_cylindrical_roller(8, 12)
        self.assertAlmostEqual(plain.val().Volume(), math.pi * 4**2 * 12, places=6)
        self.assertTrue(inspect_solid(plain).valid)

    def test_real_revolved_chamfer_and_crown_roundtrip(self):
        original = profiled_cylindrical_roller(8, 12).val()
        for mode, relief in (("chamfered", 0), ("crowned", .02)):
            with self.subTest(profile=mode):
                roller = profiled_cylindrical_roller(
                    8, 12, profile=mode, chamfer_mm=.2, crown_relief_mm=relief)
                self.assertTrue(inspect_solid(roller).valid)
                self.assertLess(roller.val().Volume(), original.Volume())
                self.assertAlmostEqual(roller.val().BoundingBox().zlen, 12)
                with tempfile.TemporaryDirectory() as temp:
                    step = Path(temp) / "roller.step"
                    cq.exporters.export(roller, str(step), exportType="STEP")
                    imported = cq.importers.importStep(str(step)).solids().vals()
                    self.assertEqual(len(imported), 1)
                    self.assertTrue(imported[0].isValid())
                    self.assertAlmostEqual(imported[0].Volume(), roller.val().Volume(), places=5)

    def test_optional_profile_is_accepted_in_cad_and_old_api_still_works(self):
        base = cylindrical_request("NUP")
        original = build_cylindrical_roller(parse_request(base))
        self.assertEqual(len(original.instances), 14)
        base["parameters"].update(roller_profile="crowned",
                                  roller_end_chamfer_mm=.2,
                                  roller_crown_relief_mm=.02)
        enhanced = build_cylindrical_roller(parse_request(base))
        self.assertEqual(len(enhanced.instances), 14)
        roller = next(p.shape for p in enhanced.components if p.component_id == "roller")
        self.assertTrue(inspect_solid(roller).valid)
        self.assertLess(roller.val().Volume(),
                        next(p.shape.val().Volume() for p in original.components
                             if p.component_id == "roller"))

    def test_invalid_profiles_fail_without_auto_clamping(self):
        for mode, chamfer, crown in [
            ("crowned", 0, .02), ("crowned", .2, 0),
            ("plain", .2, 0), ("chamfered", .2, .02),
            ("crowned", 10, .02), ("crowned", .2, 1),
        ]:
            with self.subTest(mode=mode, chamfer=chamfer, crown=crown):
                request = cylindrical_request()
                request["parameters"].update(roller_profile=mode,
                                             roller_end_chamfer_mm=chamfer,
                                             roller_crown_relief_mm=crown)
                with self.assertRaises(ContractError):
                    build_cylindrical_roller(parse_request(request))

"""Audited RoBAS analytic behavior, deliberately NOT a design recommendation.

These probes reproduce a specified C# call path; Eyeshot solid parity is unverified.
RoBAS source: see docs/migration/robas_geometry_equivalence.md.
"""
import math
import unittest

from bearing_cad.angular_contact import _raceway_centres
from bearing_cad.contracts import parse_request
from bearing_cad.geometry import circular_positions
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.cylindrical_roller import build_cylindrical_roller
from bearing_cad.angular_contact import build_angular_contact
from test_contracts import deep_request
from test_cylindrical_roller import cylindrical_request
from test_angular_contact import request as angular_request


def legacy_dgb_ball_count(ball_d_mm: float, pitch_d_mm: float) -> int:
    """DGBGeometry.cs:58 / DeepGrooveBallBearing.cs:63, coefficient 186 UNAUDITED."""
    return int(186 / math.degrees(2 * math.asin(ball_d_mm / pitch_d_mm))) + 1


def legacy_acb_groove_diameters(pitch_d_mm: float, ball_d_mm: float,
                                alpha: float) -> tuple[float, float]:
    """ACBGeometry.cs:64,78, caller-dependent alpha units; raw Math.Cos(alpha)."""
    outer_r, inner_r = 0.525 * ball_d_mm, 0.515 * ball_d_mm
    return (pitch_d_mm + 2 * outer_r - (2 * outer_r - ball_d_mm) * math.cos(alpha),
            pitch_d_mm - 2 * inner_r + (2 * inner_r - ball_d_mm) * math.cos(alpha))


class LegacyEquivalenceBaseline(unittest.TestCase):
    def test_dgb_two_legacy_call_paths_produce_distinct_pitch_and_count(self):
        outer_d, inner_d, ball_d = 68., 40., 8.
        from_geometry = (outer_d + inner_d) / 2  # DGBGeometry.cs:57
        from_scalar = (inner_d + inner_d) / 2  # DeepGrooveBallBearing.cs:62
        self.assertEqual((from_geometry, from_scalar), (54., 40.))
        self.assertEqual((legacy_dgb_ball_count(ball_d, from_geometry),
                          legacy_dgb_ball_count(ball_d, from_scalar)), (11, 9))
        # The Python contract intentionally uses an explicit, independently checked PCD.
        self.assertEqual(parse_request(deep_request()).parameters["pitch_d_mm"], 54.)

    def test_dgb_legacy_curvature_is_path_dependent(self):
        ball_d = 8.
        self.assertEqual((.51*ball_d, .53*ball_d), (4.08, 4.24))  # DGBGeometry
        self.assertEqual((.52*ball_d, .54*ball_d), (4.16, 4.32))  # Scalar race default
        p = parse_request(deep_request()).parameters
        self.assertNotAlmostEqual(p["inner_groove_radius_mm"], .52*ball_d)

    def test_acb_legacy_degree_radian_ambiguity_is_not_silently_copied(self):
        raw = legacy_acb_groove_diameters(54., 8., 25.)
        converted = legacy_acb_groove_diameters(54., 8., math.radians(25.))
        self.assertNotAlmostEqual(raw[0], converted[0], places=3)
        self.assertNotAlmostEqual(raw[1], converted[1], places=3)
        inner, outer = _raceway_centres(27., 4., 4.3, 4.5, 25.)
        self.assertAlmostEqual(math.dist(inner, (27., 0.)), .3, places=9)
        self.assertAlmostEqual(math.dist(outer, (27., 0.)), .5, places=9)
        self.assertAlmostEqual(inner[1]/(inner[0]-27.), math.tan(math.radians(25)), places=9)

    def test_python_models_have_expected_parts_without_claiming_eyeshot_equivalence(self):
        for request, builder, count in (
            (deep_request(), build_deep_groove, 13),
            (cylindrical_request("NUP"), build_cylindrical_roller, 14),
            (angular_request(25), build_angular_contact, 13),
        ):
            with self.subTest(bearing=request["bearing_type"]):
                model = builder(parse_request(request))
                self.assertEqual(len(model.instances), count)
                positions = [p.translation_mm for p in model.instances
                             if p.component_id in {"ball", "roller"}]
                self.assertEqual(len(positions), 11)
                self.assertEqual(len(set(positions)), 11)
                self.assertAlmostEqual(math.hypot(*positions[0][:2]), 27.)
                self.assertEqual(positions[0][2], 0.)
                self.assertEqual(positions, list(circular_positions(54., 11)))

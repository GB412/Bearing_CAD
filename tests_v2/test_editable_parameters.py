"""Parameter-editing regression: scaled geometry, API-budget parity and cages."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from bearing_cad.artifacts import generate_bundle, verify_bundle
from bearing_cad.contracts import ContractError, parse_request
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.cylindrical_roller import build_cylindrical_roller
from bearing_cad.angular_contact import build_angular_contact
from test_contracts import deep_request
from test_cylindrical_roller import cylindrical_request
from test_angular_contact import request as angular_request
from test_cylindrical_cage import with_cage as cylindrical_with_cage
from test_straight_pocket_cage import angular_with_cage
from test_stamping_cage import stamping_request


def scale_payload(payload, factor):
    data = copy.deepcopy(payload)
    for key, value in data["parameters"].items():
        if isinstance(value, (int, float)) and key not in (
            "ball_count", "roller_count", "contact_angle_deg"
        ):
            data["parameters"][key] = value * factor
    if "cage" in data:
        for key, value in data["cage"].items():
            if key != "kind":
                data["cage"][key] = value * factor
    return data


class EditableParametersTests(unittest.TestCase):
    def test_change_bore_only_is_rejected_for_default_three_types(self):
        for payload, builder in [
            (deep_request(), build_deep_groove),
            (cylindrical_request(), build_cylindrical_roller),
            (angular_request(), build_angular_contact),
        ]:
            case = copy.deepcopy(payload)
            case["parameters"]["bore_d_mm"] = 50
            with self.subTest(type=case["bearing_type"]), self.assertRaises(ContractError):
                builder(parse_request(case))

    def test_scale_bore_to_50_all_three_types_cages_and_real_step(self):
        cases = (
            (stamping_request(), 26),
            (cylindrical_with_cage("NUP"), 15),
            (angular_with_cage(25), 14),
        )
        with tempfile.TemporaryDirectory() as root:
            for payload, instance_count in cases:
                changed = scale_payload(payload, 1.25)
                request = parse_request(changed)
                with self.subTest(type=request.bearing_type.value):
                    self.assertEqual(request.parameters["bore_d_mm"], 50)
                    self.assertEqual(request.parameters["outside_d_mm"], 85)
                    output = generate_bundle(request, Path(root))
                    manifest = verify_bundle(output)
                    self.assertEqual(len(manifest["instances"]), instance_count)
                    self.assertIn("geometry_quality.json", manifest["files"])
                    if request.bearing_type.value == "rolling.angular_contact_ball":
                        import json
                        quality = json.loads((output/"geometry_quality.json").read_text(encoding="utf-8"))
                        report = quality["step_roundtrip"]
                        self.assertLessEqual(
                            report["worst_part_centroid_error_mm"],
                            report["radial_window_cage_centroid_limit_mm"],
                        )
                        self.assertLessEqual(
                            report["worst_relative_solid_volume_error"],
                            report["radial_window_cage_relative_volume_limit"],
                        )
                    self.assertEqual(manifest["request_hash"], request.request_hash)

    def test_axial_clearance_is_minimum_requirement_not_geometry_control(self):
        # The entered minimum reserve can change without changing the centered
        # roller or flanges. It still changes the request identity.
        from bearing_cad.geometry_checks import inspect_solid
        source=cylindrical_request("NUP")
        stricter=copy.deepcopy(source)
        stricter["parameters"]["axial_clearance_mm"]=0.8
        a,b=map(parse_request,(source,stricter))
        self.assertNotEqual(a.request_hash,b.request_hash)
        first,second=build_cylindrical_roller(a),build_cylindrical_roller(b)
        self.assertEqual([x.translation_mm for x in first.instances],
                         [x.translation_mm for x in second.instances])
        self.assertEqual([x.component_id for x in first.components],
                         [x.component_id for x in second.components])
        for before,after in zip(first.components,second.components):
            self.assertAlmostEqual(inspect_solid(before.shape).volume_mm3,
                                   inspect_solid(after.shape).volume_mm3,places=6)
        too_much=copy.deepcopy(source)
        too_much["parameters"]["axial_clearance_mm"]=1.1
        with self.assertRaises(ContractError):
            build_cylindrical_roller(parse_request(too_much))

    def test_forged_dataclass_request_cannot_bypass_cage_resource_limits(self):
        from dataclasses import replace
        from bearing_cad.contracts import CageSpec
        original=parse_request(cylindrical_request("NUP"))
        forged=replace(original,cage=CageSpec(kind="cylindrical_window",
                        inner_d_mm=1001,outside_d_mm=1002,width_mm=16,
                        pocket_clearance_mm=.15))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ContractError) as error:
                generate_bundle(forged,Path(temp))
            self.assertEqual(error.exception.error_code,"RESOURCE_LIMIT")

    def test_zero_clearance_and_resource_limit_contract(self):
        payload = cylindrical_request()
        payload["parameters"]["radial_clearance_mm"] = 0
        payload["parameters"]["axial_clearance_mm"] = 0
        parsed = parse_request(payload)
        self.assertEqual(parsed.parameters["radial_clearance_mm"], 0)
        self.assertEqual(parsed.parameters["axial_clearance_mm"], 0)
        model = build_cylindrical_roller(parsed)
        self.assertEqual(len(model.instances), 13)
        for key in ("radial_clearance_mm", "axial_clearance_mm"):
            bad = copy.deepcopy(payload)
            bad["parameters"][key] = -0.001
            with self.subTest(key=key), self.assertRaises(ContractError):
                parse_request(bad)
        for change in ({"roller_count":65}, {"outside_d_mm":1001}):
            bad = copy.deepcopy(payload)
            bad["parameters"].update(change)
            with self.subTest(change=change), self.assertRaises(ContractError):
                parse_request(bad)

    def test_simplified_cage_cannot_exceed_axial_envelope(self):
        payload = deep_request()
        payload["cage"] = {
            "kind":"simplified_annular",
            "inner_d_mm":48,"outside_d_mm":60,
            "width_mm":16,"pocket_clearance_mm":0.25,
        }
        with self.assertRaises(ContractError) as ctx:
            build_deep_groove(parse_request(payload))
        self.assertEqual(ctx.exception.field_path,"/cage/width_mm")

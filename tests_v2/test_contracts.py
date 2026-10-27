import copy
import unittest

from bearing_cad import BuilderRegistry, ContractError, parse_request
from bearing_cad.contracts import AssemblyModel, BearingType, ComponentDefinition, ComponentInstance


def deep_request():
    return {"schema_version": "bearing-cad.request.v1", "bearing_type": "rolling.deep_groove_ball",
            "unit": "mm", "detail_level": "functional", "geometry_strategy": "explicit",
            "parameters": {"bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
                           "ball_d_mm": 8, "pitch_d_mm": 54, "ball_count": 11,
                           "inner_groove_radius_mm": 4.3, "outer_groove_radius_mm": 4.5,
                           "inner_shoulder_d_mm": 47.2, "outer_shoulder_d_mm": 60.8}}


class ContractTests(unittest.TestCase):
    def test_roundtrip_hash_and_unit_normalization(self):
        a = parse_request(deep_request())
        b = deep_request()
        b["parameters"] = dict(reversed(list(b["parameters"].items())))
        b["parameters"]["bore_d_mm"] = 40.0
        self.assertEqual(a.request_hash, parse_request(b).request_hash)
        self.assertEqual(a.unit, "mm")
        with self.assertRaises(TypeError):
            a.parameters["bore_d_mm"] = 80
        self.assertEqual(a.parameters["bore_d_mm"], 40.0)
        c = deep_request()
        c["parameters"]["ball_count"] = 12
        self.assertNotEqual(a.request_hash, parse_request(c).request_hash)

    def test_reject_invalid_inputs(self):
        for parent, key, val, code in [
            ("parameters", "bore_d_mm", True, "PARAMETER_INVALID"),
            ("parameters", "outside_d_mm", float("nan"), "PARAMETER_INVALID"),
            ("parameters", "width_mm", float("inf"), "PARAMETER_INVALID"),
            ("parameters", "width_mm", 10**500, "PARAMETER_INVALID"),
            ("parameters", "width_mm", -1, "PARAMETER_INVALID"),
            ("parameters", "ball_count", 3.3, "PARAMETER_INVALID"),
            ("parameters", "ball_count", True, "PARAMETER_INVALID"),
            ("parameters", "outside_d_mm", 39, "PARAMETER_INVALID"),
            ("parameters", "pitch_d_mm", 90, "PARAMETER_INVALID"),
            ("root", "unit", "m", "PARAMETER_INVALID"),
            ("root", "bearing_type", "rolling.foo", "NOT_SUPPORTED"),
            ("root", "schema_version", "v0", "SCHEMA_UNSUPPORTED"),
            ("root", "approval_state", "CONFIRMED", "PARAMETER_INVALID"),
        ]:
            with self.subTest(field=key, value=val):
                obj = deep_request()
                (obj["parameters"] if parent=="parameters" else obj)[key] = val
                with self.assertRaises(ContractError) as ctx:
                    parse_request(obj)
                self.assertEqual(ctx.exception.error_code, code)
                self.assertTrue(ctx.exception.field_path.startswith("/"))
        invalid = deep_request(); del invalid["parameters"]["ball_d_mm"]
        with self.assertRaises(ContractError): parse_request(invalid)

    def test_three_types_are_parsed_without_inventing_dimensions(self):
        deep = deep_request()
        cylinder = copy.deepcopy(deep)
        cylinder["bearing_type"] = "rolling.cylindrical_roller"
        cylinder["parameters"] = {"bore_d_mm":40,"outside_d_mm":68,"width_mm":15,
                                  "roller_d_mm":8,"roller_length_mm":12,"pitch_d_mm":54,
                                  "roller_count":11,"configuration":"NU",
                                  "radial_clearance_mm":0.05,"axial_clearance_mm":0.4,
                                  "rib_width_mm":2,"inner_rib_tip_d_mm":52,
                                  "outer_rib_tip_d_mm":56}
        self.assertEqual(parse_request(cylinder).parameters["configuration"], "NU")
        angle = copy.deepcopy(deep)
        angle["bearing_type"] = "rolling.angular_contact_ball"
        del angle["parameters"]["inner_shoulder_d_mm"]
        del angle["parameters"]["outer_shoulder_d_mm"]
        angle["parameters"].update({"inner_shoulder_left_d_mm": 49,
                                    "inner_shoulder_right_d_mm": 47,
                                    "outer_shoulder_left_d_mm": 61,
                                    "outer_shoulder_right_d_mm": 59})
        angle["parameters"]["contact_angle_deg"] = 25
        self.assertEqual(parse_request(angle).parameters["contact_angle_deg"], 25.)
        angle["parameters"]["contact_angle_deg"] = 90
        with self.assertRaises(ContractError): parse_request(angle)

    def test_unimplemented_builder_fails_closed(self):
        with self.assertRaises(ContractError) as ctx:
            BuilderRegistry().build(parse_request(deep_request()))
        self.assertEqual(ctx.exception.error_code, "NOT_SUPPORTED")

    def test_component_identity(self):
        shape = object()
        part = ComponentDefinition("ball", "rolling_element", shape)
        assembly = AssemblyModel(BearingType.DEEP_GROOVE, (part,),
                                 (ComponentInstance("ball-001", "ball"),
                                  ComponentInstance("ball-002", "ball", (1.,2.,0.))))
        self.assertEqual(len(assembly.instances),2)
        with self.assertRaises(ContractError):
            AssemblyModel(BearingType.DEEP_GROOVE, (part,), (ComponentInstance("bad", "nope"),))


if __name__ == "__main__": unittest.main()

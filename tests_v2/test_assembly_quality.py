"""3D-MIG-06 geometry contract and STEP transform fidelity regression."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import cadquery as cq

from bearing_cad.assembly_quality import build_assembly, audit_step_roundtrip
from bearing_cad.artifacts import generate_bundle, verify_bundle
from bearing_cad.contracts import (AssemblyModel, BearingType, ComponentDefinition,
                                   ComponentInstance, ContractError, parse_request)
from test_contracts import deep_request
from test_cylindrical_roller import cylindrical_request
from test_angular_contact import request as angular_request


class AssemblyQualityTests(unittest.TestCase):
    def test_non_symmetric_part_z_rotation_is_visible_after_step_roundtrip(self):
        # An axially symmetrical bearing ring cannot reveal a missing rotation.
        # A 4x2 mm box rotated 90 deg about Z MUST have extents 2x4 mm.
        shape = cq.Workplane("XY").box(4, 2, 3)
        model = AssemblyModel(
            BearingType.DEEP_GROOVE,
            (ComponentDefinition("rectangular_probe", "probe", shape),),
            (ComponentInstance("rotated", "rectangular_probe", (10, 3, 0), 90),),
        )
        assembly = build_assembly(model)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rotated.step"
            assembly.save(str(path))
            reread = cq.importers.importStep(str(path)).solids().vals()
            self.assertEqual(len(reread), 1)
            ext = reread[0].BoundingBox()
            self.assertAlmostEqual(ext.xlen, 2, delta=0.001)
            self.assertAlmostEqual(ext.ylen, 4, delta=0.001)
            self.assertAlmostEqual((ext.xmin + ext.xmax) / 2, 10, delta=0.001)
            self.assertAlmostEqual((ext.ymin + ext.ymax) / 2, 3, delta=0.001)
            report = audit_step_roundtrip(model, assembly, reread)
            self.assertEqual(report["instance_count"], 1)
            self.assertLess(report["step_roundtrip"]["worst_bbox_error_mm"], 1e-3)

    def test_step_radial_window_volume_error_remains_visible(self):
        # Real OCCT roundtrip can perturb a multi-cut radial window cage by
        # ~0.017% despite valid source/import solids. Preserve a precision notice.
        from bearing_cad.cages import straight_pocket_cage
        from bearing_cad.contracts import CageSpec
        cage = straight_pocket_cage(
            CageSpec(kind="straight_pocket",inner_d_mm=51,
                     outside_d_mm=57,width_mm=11,pocket_clearance_mm=.15),
            pitch_d_mm=54,ball_d_mm=8,ball_count=11,bearing_width_mm=15,
            max_inner_shoulder_d_mm=49,min_outer_shoulder_d_mm=59,
        )
        model=AssemblyModel(
            BearingType.ANGULAR_CONTACT,
            (ComponentDefinition("cage","cage",cage),),
            (ComponentInstance("cage","cage"),),
        )
        assembly=build_assembly(model)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"radial.step"
            assembly.save(str(p))
            imported=cq.importers.importStep(str(p)).solids().vals()
            quality=audit_step_roundtrip(model,assembly,imported)
            error=quality["step_roundtrip"]["worst_relative_solid_volume_error"]
            self.assertLess(error,quality["step_roundtrip"]["allowed_relative_volume_error"])
            self.assertGreaterEqual(error,0)
            self.assertGreater(
                quality["step_roundtrip"]["radial_window_cage_relative_volume_limit"],
                quality["step_roundtrip"]["allowed_relative_volume_error"],
            )
            self.assertGreater(
                quality["step_roundtrip"]["radial_window_cage_centroid_limit_mm"],
                quality["step_roundtrip"]["allowed_part_centroid_error_mm"],
            )

    def test_interior_part_shift_rejected_even_if_total_bbox_and_volume_unchanged(self):
        # Three equal-volume solids: moving only the middle solid leaves both
        # overall envelope and sorted volumes unchanged. Old gate missed this.
        box = cq.Workplane("XY").box(2, 2, 2)
        model = AssemblyModel(
            BearingType.DEEP_GROOVE,
            (ComponentDefinition("probe", "probe", box),),
            tuple(ComponentInstance(f"box_{i}", "probe", (float(x), 0., 0.))
                  for i, x in enumerate((-10, 0, 10))),
        )
        assembly = build_assembly(model)
        solids = list(assembly.toCompound().Solids())
        self.assertEqual(len(solids), 3)
        # Preserve the two extrema; move the central solid by two millimetres.
        center = sorted(range(3), key=lambda i: abs(solids[i].Center().x))[0]
        solids[center] = solids[center].translate(cq.Vector(2., 0., 0.))
        with self.assertRaisesRegex(RuntimeError, "center of mass"):
            audit_step_roundtrip(model, assembly, solids)

    def test_invalid_instance_transforms_are_rejected_before_geometry(self):
        box = ComponentDefinition("a", "probe", object())
        for location, rotation in (
            ((math.nan, 0, 0), 0), ((0, math.inf, 0), 0),
            ((0, 0, 0), math.nan), ((0, 0, 0), math.inf),
            ((0, 0, 0), True),
        ):
            with self.subTest(location=location, rotation=rotation):
                with self.assertRaises(ContractError):
                    AssemblyModel(BearingType.DEEP_GROOVE, (box,),
                                  (ComponentInstance("one", "a", location, rotation),))
        with self.assertRaises(ContractError):
            AssemblyModel(BearingType.DEEP_GROOVE, (box,), ())

    def test_quality_report_for_three_bearing_builders(self):
        for payload in (deep_request(), cylindrical_request("NUP"), angular_request(25)):
            request = parse_request(payload)
            with self.subTest(kind=request.bearing_type.value), tempfile.TemporaryDirectory() as tmp:
                directory = generate_bundle(request, Path(tmp))
                manifest = verify_bundle(directory)
                info = json.loads((directory / "geometry_quality.json").read_text(encoding="utf-8"))
                self.assertEqual(info["instance_count"], len(manifest["instances"]))
                self.assertEqual(info["component_count"], len(manifest["parts"]))
                self.assertEqual(info["step_roundtrip"]["solid_count"], len(manifest["instances"]))
                self.assertEqual(len(info["step_roundtrip"]["source_bounds_mm"]), 6)
                self.assertLess(info["step_roundtrip"]["worst_relative_solid_volume_error"], 1e-5)
                self.assertLess(info["step_roundtrip"]["worst_bbox_error_mm"], 1e-3)
                self.assertLess(info["step_roundtrip"]["worst_part_centroid_error_mm"], 1e-3)
                self.assertAlmostEqual(
                    info["step_roundtrip"]["source_summed_volume_mm3"],
                    info["step_roundtrip"]["imported_summed_volume_mm3"],
                    delta=max(1e-5, info["step_roundtrip"]["source_summed_volume_mm3"]*1e-5)
                )
                for inst in manifest["instances"]:
                    self.assertEqual(inst["rotation_about_z_deg"], 0)
                self.assertIn("geometry_quality.json", manifest["files"])

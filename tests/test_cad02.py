"""Real CadQuery/OCP regression tests for CAD-02. Run only in the exact-CAD environment."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from generate_cad import Bearing
from cad02_pipeline import FeatureSpec, Design, build_models, generate, read_design, validate_models, verify_bundle

class CAD02Tests(unittest.TestCase):
    def setUp(self):
        self.base=Bearing(50,.05,70,50,86,60)
        self.design=Design(self.base,FeatureSpec()).validate()

    def test_legacy_input_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"legacy.json"
            path.write_text(json.dumps(vars(self.base)))
            self.assertEqual(read_design(path).geometry_hash,self.design.geometry_hash)
        self.assertEqual(self.design.normalized_geometry()["radial_clearance_mm"],50)
        other=Design(Bearing(60,.05,80,50,100,60),FeatureSpec()).validate()
        self.assertNotEqual(other.geometry_hash,self.design.geometry_hash)

    def test_reject_untrusted_approval_fields_and_bad_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.json"
            path.write_text(json.dumps({**vars(self.base),"approval_state":"CONFIRMED"}))
            with self.assertRaises(ValueError):read_design(path)
        invalid=[
            FeatureSpec(annular_groove_width_mm=6),
            FeatureSpec(oil_feed_hole_d_mm=5,annular_groove_width_mm=6),
            FeatureSpec(oil_feed_hole_d_mm=5,annular_groove_width_mm=50,annular_groove_depth_mm=1),
            FeatureSpec(oil_feed_hole_d_mm=5,annular_groove_width_mm=6,annular_groove_depth_mm=15),
            FeatureSpec(oil_feed_hole_d_mm=.0001),FeatureSpec(oil_feed_hole_d_mm=True),
            FeatureSpec(oil_feed_hole_d_mm=50),
        ]
        for features in invalid:
            with self.subTest(features=features):
                with self.assertRaises(ValueError):Design(self.base,features).validate()

    def test_features_modify_only_correct_solids(self):
        before=build_models(self.design)
        featured=Design(self.base,FeatureSpec(5,6,1.2)).validate()
        after=build_models(featured)
        validate_models(featured,after)
        self.assertLess(after["housing"].val().Volume(),before["housing"].val().Volume())
        self.assertLess(after["bushing"].val().Volume(),before["bushing"].val().Volume())
        self.assertAlmostEqual(after["shaft"].val().Volume(),before["shaft"].val().Volume(),places=6)

    def test_step_dxf_projections_and_cache_tamper(self):
        featured=Design(self.base,FeatureSpec(5,6,1.2)).validate()
        with tempfile.TemporaryDirectory() as tmp:
            dest=generate(featured,Path(tmp))
            self.assertEqual(dest,generate(featured,Path(tmp)))
            report=verify_bundle(dest,featured.geometry_hash)
            self.assertEqual(report["approval_state"],"DRAFT")
            self.assertEqual(len(report["topology_checks"]),3)
            self.assertGreater(report["projection_checks"]["side"]["visible_edges"],3)
            self.assertGreater(report["projection_checks"]["end"]["visible_edges"],3)
            import cadquery as cq
            self.assertEqual(len(cq.importers.importStep(str(dest/"bearing_assembly.step")).solids().vals()),3)
            import ezdxf
            doc=ezdxf.readfile(dest/"occt_projection.dxf")
            audit=doc.audit()
            self.assertFalse(audit.has_errors)
            self.assertFalse(audit.fixes)
            self.assertEqual(doc.units,ezdxf.units.MM)
            self.assertGreater(len(doc.modelspace()),20)
            self.assertIn("polyline",(dest/"occt_side.svg").read_text())
            with (dest/"bushing.step").open("ab") as handle:handle.write(b"corrupt")
            with self.assertRaises(RuntimeError):generate(featured,Path(tmp))

    def test_three_dimensions_and_volume(self):
        sizes=[Bearing(50,.05,70,50,86,60),Bearing(60,.08,82,55,100,70),Bearing(35,.02,48,30,64,40)]
        for b in sizes:
            with self.subTest(bearing=b):
                models=build_models(Design(b,FeatureSpec()).validate())
                report=validate_models(Design(b,FeatureSpec()),models)
                self.assertEqual(report["bushing"]["bounds_mm"]["z"],b.length_mm)
                self.assertAlmostEqual(models["bushing"].val().Volume(),
                    math.pi/4*(b.bush_od_mm**2-b.bore_d_mm**2)*b.length_mm,places=4)

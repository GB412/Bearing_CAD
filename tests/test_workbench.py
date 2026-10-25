"""Engineering workbench: exact section B-Reps and one-source review drawing."""
from pathlib import Path
import tempfile
import unittest
import math
from generate_cad import Bearing
from cad02_pipeline import Design,FeatureSpec,build_models,generate,verify_bundle
from cad_workbench_drawing import make_sections,check_assembly,_section_faces

class WorkbenchGeometryTests(unittest.TestCase):
 def design(self):
  return Design(Bearing(50,.05,70,50,86,60),FeatureSpec(5,6,1.2)).validate()
 def test_real_sections_and_assembly_clearances(self):
  d=self.design();m=build_models(d);section=make_sections(d,m)
  report=check_assembly(d,m)
  self.assertAlmostEqual(report["radial_clearance_mm"],.05)
  for name in ("housing","bushing","shaft"):
   self.assertEqual(len(section[name].solids().vals()),1)
   self.assertTrue(section[name].val().isValid())
   self.assertGreater(section[name].val().Volume(),0)
   self.assertLess(section[name].val().Volume(),m[name].val().Volume())
   self.assertGreater(len(_section_faces(section[name])),0)
 def test_review_drawing_and_sections_in_bundle(self):
  import ezdxf
  import cadquery as cq
  d=self.design()
  with tempfile.TemporaryDirectory() as root:
   dest=generate(d,Path(root))
   report=verify_bundle(dest,d.geometry_hash)
   self.assertIn("assembly_checks",report)
   self.assertEqual(report["section_drawing_checks"]["status"],"DRAFT_NOT_FOR_MANUFACTURE")
   self.assertGreater(report["section_drawing_checks"]["end_visible_edges"],2)
   for name in ("housing","bushing","shaft"):
    self.assertTrue((dest/f"{name}_section.stl").stat().st_size>1000)
    solid=cq.importers.importStep(str(dest/f"{name}_section.step")).solids().vals()
    self.assertEqual(len(solid),1)
   svg=(dest/"bearing_review_sheet.svg").read_text(encoding="utf-8")
   self.assertIn("滑动轴承",svg)
   self.assertIn("内环槽",svg)
   doc=ezdxf.readfile(dest/"bearing_review_sheet.dxf")
   audit=doc.audit()
   self.assertFalse(audit.errors)
   self.assertFalse(audit.fixes)
   self.assertGreater(len(list(doc.modelspace().query("HATCH"))),0)
   self.assertEqual(doc.units,ezdxf.units.MM)

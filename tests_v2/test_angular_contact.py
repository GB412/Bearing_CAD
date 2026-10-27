import math
import tempfile
import unittest
from pathlib import Path
import cadquery as cq
from bearing_cad.contracts import ContractError,parse_request
from bearing_cad.angular_contact import build_angular_contact,_raceway_centres
from bearing_cad.artifacts import generate_bundle,verify_bundle
from bearing_cad.geometry_checks import inspect_solid

def request(angle=25):
 return {"schema_version":"bearing-cad.request.v1","bearing_type":"rolling.angular_contact_ball",
 "unit":"mm","detail_level":"functional","geometry_strategy":"explicit",
 "parameters":{"bore_d_mm":40,"outside_d_mm":68,"width_mm":15,"ball_d_mm":8,
 "pitch_d_mm":54,"ball_count":11,"inner_groove_radius_mm":4.3,
 "outer_groove_radius_mm":4.5,"contact_angle_deg":angle,
 "inner_shoulder_left_d_mm":49,"inner_shoulder_right_d_mm":47,
 "outer_shoulder_left_d_mm":61,"outer_shoulder_right_d_mm":59}}

class AngularContactTests(unittest.TestCase):
 def test_angles_geometry_and_step(self):
  for alpha in (15,25,40):
   with self.subTest(alpha=alpha):
    m=build_angular_contact(parse_request(request(alpha)))
    self.assertEqual(len(m.instances),13)
    self.assertTrue(all(inspect_solid(p.shape).valid for p in m.components))
    a=cq.Assembly(name="angular_contact")
    parts={p.component_id:p.shape for p in m.components}
    for inst in m.instances:
     a.add(parts[inst.component_id],name=inst.instance_id,
           loc=cq.Location(cq.Vector(*inst.translation_mm)))
    with tempfile.TemporaryDirectory() as root:
     path=Path(root)/"bearing.step";a.save(str(path))
     reread=cq.importers.importStep(str(path)).solids().vals()
     self.assertEqual(len(reread),13)
     self.assertTrue(all(s.isValid() for s in reread))
 def test_contact_angle_converts_once_and_changes_geometry(self):
  centers=_raceway_centres(27,4,4.3,4.5,25)
  self.assertAlmostEqual(centers[0][1],.3*math.sin(math.radians(25)),places=9)
  self.assertAlmostEqual(centers[1][1],-.5*math.sin(math.radians(25)),places=9)
  self.assertNotEqual(_raceway_centres(27,4,4.3,4.5,15),centers)
 def test_invalid_dimensions_and_angle(self):
  for field,value in (("contact_angle_deg",0),("contact_angle_deg",90),
   ("inner_groove_radius_mm",3),("inner_shoulder_left_d_mm",46),
   ("outer_shoulder_right_d_mm",62),("width_mm",8),
   ("ball_count",50)):
   x=request();x["parameters"][field]=value
   with self.subTest(field=field,value=value),self.assertRaises(ContractError):
    build_angular_contact(parse_request(x))
 def test_artifact_roundtrip(self):
  with tempfile.TemporaryDirectory() as root:
   x=parse_request(request())
   folder=generate_bundle(x,Path(root))
   manifest=verify_bundle(folder)
   self.assertEqual(manifest["bearing_type"],"rolling.angular_contact_ball")
   self.assertEqual(manifest["contact_angle_deg"],25.)
   self.assertEqual(manifest["completeness"],"CAGE_OMITTED")
   self.assertEqual(len(manifest["instances"]),13)
   self.assertEqual(folder,generate_bundle(x,Path(root)))

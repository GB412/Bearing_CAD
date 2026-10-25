import math
import unittest
from pathlib import Path
import sys
import unittest.mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from generate_cad import Bearing, cad_models, make_dxf
class CadCase(unittest.TestCase):
 def setUp(self):
  self.p=Bearing(50,.05,70,50,86,60)
 def test_clearance(self):
  self.assertAlmostEqual(self.p.bore_d_mm,50.1)
 def test_invalid_wall(self):
  with self.assertRaises(ValueError):Bearing(50,.05,50,50,86,60).validate()
 def test_invalid_clearance(self):
  with self.assertRaises(ValueError):Bearing(50,0,70,50,86,60).validate()
 def test_invalid_length(self):
  with self.assertRaises(ValueError):Bearing(50,.05,70,80,86,60).validate()
 def test_boundary_and_invalid_parameter_matrix(self):
  cases = [
   (Bearing(15,.005,30,15,40,15), True),
   (Bearing(120,.3,130,150,150,180), True),
   (Bearing(14.999,.05,70,50,86,60), False),
   (Bearing(120.001,.05,150,50,180,60), False),
   (Bearing(50,.0049,70,50,86,60), False),
   (Bearing(50,.3001,70,50,86,60), False),
   (Bearing(50,.05,54.1,50,86,60), False),
   (Bearing(50,.05,70,14.999,86,60), False),
   (Bearing(50,.05,70,150.001,86,180), False),
   (Bearing(50,.05,70,50,76,60), False),
   (Bearing(50,.05,70,50,86,49), False),
   (Bearing(50,.05,70,50,86,181), False),
  ]
  for bearing, valid in cases:
   with self.subTest(bearing=bearing):
    if valid:
     self.assertIs(bearing.validate(), bearing)
    else:
     with self.assertRaises(ValueError):
      bearing.validate()
 def test_representative_2d_3d_dimensions_share_schema(self):
  cases = [Bearing(50,.05,70,50,86,60), Bearing(60,.08,82,55,100,70), Bearing(35,.02,48,30,64,40)]
  for bearing in cases:
   bearing.validate()
   self.assertAlmostEqual(bearing.bore_d_mm, bearing.shaft_d_mm + 2 * bearing.radial_clearance_mm)
   self.assertEqual(bearing.shaft_length_mm, bearing.housing_length_mm + 18)
   self.assertGreater(bearing.bush_od_mm, bearing.bore_d_mm + 4)
   self.assertGreater(bearing.housing_od_mm, bearing.bush_od_mm + 6)
 def test_existing_dxf_has_units_and_demo_layers(self):
  try:
   import ezdxf
  except ModuleNotFoundError:
   self.skipTest('ezdxf is optional; install requirements-cad.txt to parse DXF')
  path=Path(__file__).resolve().parents[1]/'outputs'/'bearing_section.dxf'
  doc=ezdxf.readfile(path)
  self.assertEqual(doc.units, ezdxf.units.MM)
  for layer in ('HOUSING','BUSHING','SHAFT','CENTER','DIM'):
   self.assertIn(layer, doc.layers)
  self.assertGreater(len(doc.modelspace()), 10)
 def test_cad_solid_volume(self):
  try:
   import cadquery
  except ModuleNotFoundError:
   self.skipTest('CadQuery is optional; install the pinned CAD environment to run solid checks')
  b=self.p
  md=cad_models(b)
  theoretical={
   'housing': math.pi/4*(b.housing_od_mm**2-b.bush_od_mm**2)*b.housing_length_mm,
   'bushing': math.pi/4*(b.bush_od_mm**2-b.bore_d_mm**2)*b.length_mm,
   'shaft': math.pi/4*b.shaft_d_mm**2*b.shaft_length_mm,
  }
  for name, shape in md.items():
   self.assertAlmostEqual(shape.val().Volume(),theoretical[name],places=5)
if __name__=='__main__':unittest.main()

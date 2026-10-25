import math
import unittest
from pathlib import Path
import sys
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
 def test_cad_solid_volume(self):
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

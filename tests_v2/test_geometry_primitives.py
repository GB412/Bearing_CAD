import math
import unittest
from bearing_cad.geometry import annulus, revolve_radial_profile, sphere, cylindrical_roller, circular_positions
from bearing_cad.geometry_checks import inspect_solid, interference_volume


class GeometryPrimitivesTests(unittest.TestCase):
    def test_annulus_and_revolved_section(self):
        expected = math.pi * (30**2 - 20**2) * 12
        ring = annulus(40, 60, 12)
        report = inspect_solid(ring)
        self.assertTrue(report.valid)
        self.assertEqual(report.solids, 1)
        self.assertAlmostEqual(report.volume_mm3, expected, places=4)
        self.assertTrue(all(abs(x-y)<1e-5 for x,y in zip(report.extents_mm,(60,60,12))))
        revolved = revolve_radial_profile(((20,-6),(30,-6),(30,6),(20,6)))
        report2 = inspect_solid(revolved)
        self.assertTrue(report2.valid)
        self.assertAlmostEqual(report2.volume_mm3, expected, places=4)

    def test_sphere_roller_and_positions(self):
        self.assertAlmostEqual(inspect_solid(sphere(8)).volume_mm3, 4/3*math.pi*4**3, places=4)
        self.assertAlmostEqual(inspect_solid(cylindrical_roller(8,11)).volume_mm3, math.pi*4**2*11, places=4)
        coords = circular_positions(54, 11)
        self.assertEqual(len(coords), 11)
        self.assertEqual(len(set(coords)), 11)
        self.assertTrue(all(abs(math.hypot(x,y)-27)<1e-10 for x,y,z in coords))
        self.assertAlmostEqual(coords[0][0], 27, places=10)

    def test_intersection(self):
        self.assertAlmostEqual(interference_volume(sphere(8),sphere(8)),4/3*math.pi*4**3,places=4)
        self.assertAlmostEqual(interference_volume(sphere(8),sphere(8).translate((20,0,0))),0.,places=7)

    def test_reject_invalid(self):
        for fn,args in ((annulus,(60,40,10)),(annulus,(True,60,10)),
                        (sphere,(float("nan"),)),(cylindrical_roller,(5,-1)),
                        (circular_positions,(54,0)),(circular_positions,(54,True)),
                        (revolve_radial_profile,([(0,0),(1,0),(1,1)],))):
            with self.subTest(fn=fn.__name__,args=args),self.assertRaises(ValueError):
                fn(*args)

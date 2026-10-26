"""Mandatory OCCT test: never skip when the kernel cannot be imported."""
import unittest
from bearing_cad.kernel_probe import run_probe


class KernelProbeTests(unittest.TestCase):
    def test_step_roundtrip(self):
        result = run_probe()
        self.assertTrue(result["step_roundtrip"])
        self.assertAlmostEqual(result["volume_mm3"], 24, places=5)
        self.assertEqual(len(result["dimensions_mm"]),3)


if __name__ == "__main__": unittest.main()

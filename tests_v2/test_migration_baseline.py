"""3D-MIG-07A protects source provenance and verifies real OCCT case capture."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from bearing_cad.migration_baseline import (
    CASES_FILE, REPORT_SCHEMA, UNKNOWN_REFERENCE, UNVERIFIED,
    analytic_legacy_probe, load_fixtures, run_baseline,
)


class MigrationBaselineTests(unittest.TestCase):
    def test_seven_cases_have_explicit_legacy_provenance(self):
        fixture = load_fixtures()
        items = fixture["cases"]
        self.assertEqual(len(items), 7)
        self.assertEqual([case["case_id"] for case in items], [
            "dgb_no_cage", "dgb_stamped", "crb_NU_window", "crb_NUP_window",
            "acb_15deg", "acb_25deg_window", "acb_40deg",
        ])
        self.assertEqual({c["request"]["cage"]["kind"] for c in items
                          if c["request"].get("cage")},
                         {"stamping_double_half", "cylindrical_window", "straight_pocket"})
        self.assertEqual([c["request"]["parameters"]["contact_angle_deg"] for c in items[-3:]],
                         [15, 25, 40])
        for case in items:
            self.assertTrue(case["legacy_source_refs"])
            self.assertFalse(any("http" in path for path in case["legacy_source_refs"]))
            self.assertIn("request", case)
            self.assertEqual(case["request"]["unit"], "mm")
        self.assertEqual(fixture["reference_step_status"], UNKNOWN_REFERENCE)

    def test_legacy_numeric_call_paths_are_not_silently_collapsed(self):
        fixtures = load_fixtures()["cases"]
        notes = analytic_legacy_probe(fixtures[0])
        self.assertEqual(notes["legacy_geometry_constructor_pitch_d_mm"], 54)
        self.assertEqual(notes["legacy_scalar_constructor_pitch_d_mm"], 40)
        self.assertEqual(notes["legacy_geometry_count_expression"], 11)
        self.assertEqual(notes["legacy_scalar_count_expression"], 9)
        self.assertEqual(notes["legacy_geometry_inner_outer_groove_radius_mm"], [4.08, 4.24])
        self.assertEqual(notes["legacy_scalar_inner_outer_groove_radius_mm"], [4.16, 4.32])
        note = analytic_legacy_probe(fixtures[5])
        self.assertNotAlmostEqual(note["legacy_raw_MathCos_of_numeric"],
                                  note["legacy_deg_to_rad_MathCos"], places=3)

    def test_unavailable_source_step_is_required_not_rebranded_as_verified(self):
        source = load_fixtures()
        source["reference_step_status"] = "EQUIVALENT"
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "invalid.json"
            f.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_fixtures(f)

    def test_actual_step_report_can_regenerate_deterministically(self):
        # The full seven-case real OCCT matrix is a separate CI gate,
        # avoiding seven STEP builds twice during ordinary unit tests.
        subset = copy.deepcopy(load_fixtures())
        subset["cases"] = [subset["cases"][0]]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "fixture.json"
            path.write_text(json.dumps(subset, ensure_ascii=False), encoding="utf-8")
            out = folder / "report"
            first = run_baseline(path, out)
            report_bytes = (out / "comparison.json").read_bytes()
            markdown_bytes = (out / "comparison.md").read_bytes()
            second = run_baseline(path, out)
            self.assertEqual(first, second)
            self.assertEqual(report_bytes, (out / "comparison.json").read_bytes())
            self.assertEqual(markdown_bytes, (out / "comparison.md").read_bytes())
            self.assertEqual(first["report_schema"], REPORT_SCHEMA)
            self.assertEqual(first["case_count"], 1)
            row = first["cases"][0]
            self.assertEqual(row["solid_equivalence_status"], UNVERIFIED)
            self.assertEqual(row["legacy_step_status"], UNKNOWN_REFERENCE)
            self.assertIsNone(row["legacy_step_metrics"])
            self.assertEqual(row["python_measurements"]["instance_count"], 13)
            self.assertLess(row["python_measurements"]["max_rolling_phase_error_mm"], 1e-6)
            self.assertIn("geometry_quality.json", [p.name for p in
                           (out / "bundles" / row["artifact_key"]).iterdir()])

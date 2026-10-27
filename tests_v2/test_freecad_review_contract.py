"""The FreeCAD GUI macro must remain syntactically valid and non-approving."""
from pathlib import Path
import unittest


class FreeCADReviewContractTests(unittest.TestCase):
    def test_freecad_review_helper_is_parseable_without_freecad_dependency(self):
        root = Path(__file__).resolve().parent.parent
        script = root / "scripts" / "freecad_step_review.py"
        source = script.read_text(encoding="utf-8")
        compile(source, str(script), "exec")
        self.assertIn("AUTOMATED_IMPORT_CHECK_ONLY_MANUAL_REVIEW_PENDING", source)
        self.assertNotIn('"status": "PASSED"', source)
        self.assertIn("Import.insert", source)

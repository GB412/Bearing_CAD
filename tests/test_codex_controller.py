"""Pure deterministic tests; do not require GitHub credentials, Codex CLI or CadQuery."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/"scripts"/"codex_controller.py"
spec=importlib.util.spec_from_file_location("codex_controller",path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class TestGates(unittest.TestCase):
    def test_required_missing_and_skipped(self):
        required=["CAD-01 validation","CAD-02 OCCT verification"]
        self.assertEqual(module.decide_checks([],required),"pending")
        self.assertEqual(module.decide_checks([dict(workflow=required[0],bucket="pass")],required),"pending")
        self.assertEqual(module.decide_checks([dict(workflow=x,bucket="pass" if x==required[0] else "skipping") for x in required],required),"pending")
    def test_block_fail_and_complete_pass(self):
        req=["one","two"]
        self.assertEqual(module.decide_checks([dict(workflow="one",bucket="pass"),dict(workflow="two",bucket="fail")],req),"failed")
        self.assertEqual(module.decide_checks([dict(workflow=x,bucket="pass") for x in req],req),"passed")
    def test_controller_files_are_protected(self):
        with self.assertRaises(module.GateError):module.check_protected({"scripts/codex_controller.py"})
        module.check_protected({"bearing_cad/rolling/deep_groove.py"})
    def test_queue_has_unique_tasks_and_required_gates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"queue.json"
            p.write_text(json.dumps(dict(required_workflows=["ci"],local_checks=[["true"]],tasks=[dict(id="MIG-01",title="t",objective="o",acceptance=["one"]) ])))
            self.assertEqual(len(module.load_queue(p)["tasks"]),1)
            p.write_text(json.dumps(dict(required_workflows=["ci"],local_checks=[["true"]],tasks=[dict(id="MIG-01",title="t",objective="o",acceptance=["one"])]*2)))
            with self.assertRaises(module.GateError):module.load_queue(p)
    def test_atomic_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.json"
            module.save(p,{"tasks":{"MIG-01":{"phase":"BLOCKED"}}})
            self.assertEqual(json.loads(p.read_text())["tasks"]["MIG-01"]["phase"],"BLOCKED")

if __name__=="__main__":unittest.main()

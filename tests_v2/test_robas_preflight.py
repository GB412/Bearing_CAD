import importlib.util
import json
import sqlite3


def load_preflight():
    spec = importlib.util.spec_from_file_location(
        "robas_preflight", "bridge/cadimport/preflight.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_resources(tmp_path):
    root = tmp_path / "resources"
    for directory, names, _database in load_preflight().TEMPLATES.values():
        folder = root / "Resource" / "哑图" / directory
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            (folder / name).write_bytes(b"AC1021" + b"fixture")
    (root / "Data").mkdir(parents=True)
    for name in ("DGBData.db", "ACBData.db", "CRBData.db"):
        with sqlite3.connect(root / "Data" / name) as db:
            db.execute('CREATE TABLE "变量表" ("变量名" TEXT, "变量值" TEXT)')
            db.execute('INSERT INTO "变量表" VALUES (?, ?)', ("model", None))
    (root / "Resource").mkdir(parents=True, exist_ok=True)
    for name in load_preflight().REQUIRED_CSV:
        (root / "Resource" / name).write_text("key,value\na,1\n", encoding="utf-8")
    return root


def test_preflight_records_hashes_and_schema(tmp_path):
    module = load_preflight()
    report = module.preflight(make_resources(tmp_path))
    assert report["status"] == "CHECK_FAILED"  # intentionally incomplete fixture
    assert len(report["templates"]["rolling.deep_groove_ball"]) == 4
    assert report["databases"]["DGBData.db"]["integrity_check"] == "ok"
    assert len(report["databases"]["DGBData.db"]["sha256"]) == 64
    assert any("required tables" in item for item in report["failures"])


def test_preflight_writes_json_report(tmp_path):
    module = load_preflight()
    report = module.preflight(make_resources(tmp_path))
    target = tmp_path / "environment_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == "robas.environment.v1"

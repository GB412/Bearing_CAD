"""Read-only inspection of the private RoBAS DWG/SQLite/CSV resources."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

TEMPLATES = {
    "rolling.deep_groove_ball": ("深沟球DWG", ("0_00KS.DWG", "0_01KS.DWG", "0_02.DWG", "0_07.DWG"), "DGBData.db"),
    "rolling.angular_contact_ball": ("角接触DWG", ("6_00_ZDSTW.dwg", "6_01SK.DWG", "6_02SK.DWG", "6_07_ZDST.dwg"), "ACBData.db"),
    "rolling.cylindrical_roller:N": ("单列圆柱DWG", ("N-00.dwg", "N-01.dwg", "N-02.dwg", "N-06.dwg"), "CRBData.db"),
}
REQUIRED_CSV = (
    "球轴承零件相关系数.csv", "圆柱滚子轴承相关系数.csv",
    "BallDB.csv", "CylinderRollerDB.csv", "CylinderRollerDiameterDB.csv",
)
TECHNICAL_TABLES = tuple(
    grade + "级" + suffix
    for grade in ("B", "C", "D", "E", "G")
    for suffix in ("总图外圈技术条件", "总图内圈技术条件", "外圈技术条件", "内圈技术条件")
)


def _file(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": sha256(data).hexdigest()}


def _database(path: Path) -> dict:
    result = _file(path)
    result["integrity_check"] = "failed"
    result["tables"] = {}
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            result["integrity_check"] = db.execute("PRAGMA integrity_check").fetchone()[0]
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for name in names:
                columns = [row[1] for row in db.execute(f'PRAGMA table_info("{name.replace(chr(34), chr(34) * 2)}")')]
                result["tables"][name] = {"columns": columns, "rows": db.execute(f'SELECT count(*) FROM "{name.replace(chr(34), chr(34) * 2)}"').fetchone()[0]}
            if "变量表" not in result["tables"]:
                result["error"] = "missing table 变量表"
            else:
                cols = result["tables"]["变量表"]["columns"]
                if not {"变量名", "变量值"}.issubset(cols):
                    result["error"] = "变量表 columns do not match expected schema"
            required = {"变量表", "倒角尺寸表", *TECHNICAL_TABLES}
            if path.name == "CRBData.db":
                required.add("滚道宽度公差")
            missing = sorted(required - set(result["tables"]))
            if missing:
                result["missing_required_tables"] = missing
    except (OSError, sqlite3.DatabaseError) as error:
        result["error"] = str(error)
    return result


def _csv(path: Path) -> dict:
    result = _file(path)
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(text.splitlines()))
        result["encoding"] = "utf-8-sig"
        result["columns"] = rows[0] if rows else []
        result["row_count"] = max(len(rows) - 1, 0)
        required = {
            "球轴承零件相关系数.csv": {"Dw/Dpw", "fc", "fo"},
            "圆柱滚子轴承相关系数.csv": {"Dw/Dpw", "fc"},
            "BallDB.csv": {"diameter(mm)"},
            "CylinderRollerDB.csv": {"Dw", "Lw", "rsmin", "rsmax"},
            "CylinderRollerDiameterDB.csv": {"Dw"},
        }.get(path.name, set())
        numeric_ok = True
        if path.name.endswith("相关系数.csv"):
            try:
                indices = [result["columns"].index(column) for column in sorted(required)]
                numeric_ok = all(
                    all(float(row[index].strip()) > 0 for index in indices)
                    for row in rows[1:] if len(row) > max(indices)
                )
            except (ValueError, IndexError):
                numeric_ok = False
        result["required_columns"] = sorted(required)
        result["required_columns_present"] = required.issubset(result["columns"])
        result["numeric_values_valid"] = numeric_ok
        result["valid"] = bool(rows and rows[0] and result["row_count"] > 0 and result["required_columns_present"] and numeric_ok)
    except (OSError, UnicodeError, csv.Error) as error:
        result["valid"] = False
        result["error"] = str(error)
    return result


def preflight(root: Path, bridge: Path | None = None) -> dict:
    root = Path(root).resolve()
    report = {"schema_version": "robas.environment.v1", "status": "CHECK_FAILED", "resources_root": str(root), "templates": {}, "databases": {}, "csv": {}, "fonts": {"files": []}, "bridge": {}}
    failures = []
    for key, (directory_name, names, database_name) in TEMPLATES.items():
        directory = root / "Resource" / "哑图" / directory_name
        available = {p.name.casefold(): p for p in directory.iterdir()} if directory.is_dir() else {}
        entries = []
        for name in names:
            path = available.get(name.casefold())
            if path is None:
                failures.append(f"missing DWG: {directory / name}")
                continue
            info = _file(path)
            info["signature"] = path.read_bytes()[:6].decode("ascii", errors="replace")
            info["valid_signature"] = info["signature"].startswith("AC10")
            if not info["valid_signature"]:
                failures.append(f"invalid DWG signature: {path}")
            entries.append(info)
        report["templates"][key] = entries
        db_path = root / "Data" / database_name
        if not db_path.is_file():
            failures.append(f"missing SQLite database: {db_path}")
        else:
            report["databases"][database_name] = _database(db_path)
            if report["databases"][database_name].get("integrity_check") != "ok":
                failures.append(f"SQLite integrity failure: {db_path}")
            if report["databases"][database_name].get("error"):
                failures.append(f"SQLite schema failure: {db_path}")
            if report["databases"][database_name].get("missing_required_tables"):
                failures.append(f"SQLite missing required tables: {db_path}")
    resource_dir = root / "Resource"
    for name in REQUIRED_CSV:
        path = resource_dir / name
        if not path.is_file():
            failures.append(f"missing CSV: {path}")
        else:
            report["csv"][name] = _csv(path)
            if not report["csv"][name].get("valid"):
                failures.append(f"invalid CSV: {path}")
    font_files = []
    for suffix in ("*.shx", "*.ttf", "*.ttc"):
        font_files.extend(_file(path) for path in resource_dir.rglob(suffix))
    report["fonts"]["files"] = font_files
    if bridge is not None:
        bridge = Path(bridge).resolve()
        report["bridge"] = {"path": str(bridge), "exists": bridge.is_file(), "is_windows_executable": bridge.suffix.lower() == ".exe"}
        if not bridge.is_file():
            failures.append(f"missing bridge executable: {bridge}")
    report["failures"] = failures
    report["status"] = "READY_FOR_CADIMPORT" if not failures else "CHECK_FAILED"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only RoBAS environment preflight")
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = preflight(args.resources, args.bridge)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["status"] == "READY_FOR_CADIMPORT" else 2


if __name__ == "__main__":
    raise SystemExit(main())

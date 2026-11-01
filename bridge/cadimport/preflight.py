"""Resource preflight for real RoBAS DWG and SQLite; no conversion is simulated."""
from __future__ import annotations
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess

DEFAULT_TEMPLATES = {
 "rolling.deep_groove_ball": ("深沟球DWG", ("0_00KS.DWG","0_01KS.DWG","0_02.DWG","0_07.DWG"), "DGBData.db"),
 "rolling.angular_contact_ball": ("角接触DWG", ("6_00_ZDSTW.dwg","6_01SK.DWG","6_02SK.DWG","6_07_ZDST.dwg"), "ACBData.db"),
 "rolling.cylindrical_roller:N": ("单列圆柱DWG", ("N-00.dwg","N-01.dwg","N-02.dwg","N-06.dwg"), "CRBData.db"),
}

def preflight(root: Path) -> dict:
    root = Path(root)
    result = {"status": "RESOURCES_CHECKED_NOT_DWG_CONVERTED", "templates": {}, "databases": {}}
    for bearing_type, (subdir, files, dbname) in DEFAULT_TEMPLATES.items():
        found = []
        directory = root / "Resource" / "哑图" / subdir
        names = {p.name.casefold():p for p in directory.iterdir()} if directory.is_dir() else {}
        for name in files:
            file = names.get(name.casefold())
            if file is None:
                raise FileNotFoundError(f"{bearing_type}: {directory}/{name}")
            signature = file.read_bytes()[:6]
            if not signature.startswith(b"AC10"):
                raise ValueError(f"Invalid DWG signature: {file}")
            found.append({"name": file.name, "size": file.stat().st_size,
                          "sha256": sha256(file.read_bytes()).hexdigest()})
        result["templates"][bearing_type] = found
        db_path = root / "Data" / dbname
        if not db_path.is_file():
            raise FileNotFoundError(db_path)
        with sqlite3.connect("file:"+str(db_path.resolve())+"?mode=ro",uri=True) as connection:
            rows = connection.execute('SELECT "变量名", "变量值" FROM "变量表"').fetchall()
        duplicate = {k:n for k,n in Counter(str(row[0]) for row in rows).items() if n > 1}
        result["databases"][dbname] = {
            "rows":len(rows),"duplicated_names":duplicate,
            "sha256":sha256(db_path.read_bytes()).hexdigest()}
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resources",type=Path,required=True)
    parser.add_argument("--bridge",type=Path)
    parser.add_argument("--sample-key",default="model")
    parser.add_argument("--sample-value",default="PROBE-001")
    parser.add_argument("--outdir",type=Path)
    args=parser.parse_args()
    report=preflight(args.resources)
    if args.bridge:
        if args.outdir is None:
            parser.error("--outdir is required with --bridge")
        args.outdir.mkdir(parents=True,exist_ok=True)
        source=args.resources/"Resource"/"哑图"/"深沟球DWG"/"0_00KS.DWG"
        inspection=subprocess.run([str(args.bridge),"inspect",str(source)],capture_output=True,text=True,timeout=90,check=True)
        metadata=json.loads(inspection.stdout)
        if args.sample_key not in metadata["texts"]:
            raise ValueError("Key is not an exact source DWG CADText; inspect the source first")
        result_file=args.outdir/"real_template_probe.dxf"
        if result_file.exists():
            raise FileExistsError(result_file)
        child=subprocess.run([str(args.bridge),"replace",str(source),str(result_file),args.sample_key,args.sample_value],
                             capture_output=True,text=True,timeout=90,check=True)
        result=json.loads(child.stdout)
        import ezdxf
        document=ezdxf.readfile(str(result_file))
        auditor=document.audit()
        if auditor.errors:
            raise RuntimeError(f"Fatal DXF audit errors: {len(auditor.errors)}")
        # Original RoBAS exported DXFs contain 3-7 nonfatal metadata repairs
        # (ezdxf Auditor code 202). Record and require reference review, rather
        # than reject faithful copies solely for these legacy dictionary fixes.
        if result["exact_match_count"] < 1:
            raise RuntimeError("No replacement occurred")
        report["status"]=("DXF_REQUIRES_REFERENCE_REVIEW" if auditor.fixes
                         else "DWG_BRIDGE_DXF_AUDIT_PASSED")
        report["runtime"]={"replace_count":result["exact_match_count"],
                           "dxf":str(result_file),"entities":len(document.modelspace()),
                           "ezdxf_nonfatal_fixes":len(auditor.fixes),
                           "ezdxf_fix_codes":sorted(set(int(fix.code) for fix in auditor.fixes))}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

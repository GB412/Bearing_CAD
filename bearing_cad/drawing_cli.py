"""Run RoBAS original DWG four-sheet export in a licensed Windows environment.

Usage:
python -m bearing_cad.drawing_cli --request design.json --resources PATH
    --bridge PATH_TO_CadImportBridge.exe --out artifacts/robas-drawings

design.json: {"request": <bearing-cad.request.v1>, "drawing":
{"model":"6208","accuracy_class":"P5","diameter_series":"2",
 "chamfer1_mm":0.6,"chamfer2_mm":0.6,"legacy_values":{...}}}
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .contracts import parse_request
from .drawing_runner import generate_drawing_bundle,verify_drawing_bundle,DrawingExportError

_ALLOWED={"model","accuracy_class","diameter_series","chamfer1_mm",
          "chamfer2_mm","legacy_values","checked_values"}

def _read_request(path: Path):
    if path.stat().st_size > 128*1024:
        raise ValueError("Drawing request is too large")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or set(data)!={"request","drawing"}:
        raise ValueError("Expected request and drawing objects")
    options=data["drawing"]
    if not isinstance(options,dict) or set(options)-_ALLOWED:
        raise ValueError("Unsupported drawing option")
    request=parse_request(data["request"])
    return request,options

def main(argv=None):
    parser=argparse.ArgumentParser(description="Original RoBAS DWG -> DXF, Windows CADImport")
    parser.add_argument("--request",required=True,type=Path)
    parser.add_argument("--resources",required=True,type=Path)
    parser.add_argument("--bridge",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args(argv)
    request,options=_read_request(args.request)
    folder=generate_drawing_bundle(
        resources=args.resources, bridge=args.bridge, output_root=args.out,
        bearing_type=request.bearing_type.value,
        parameters=dict(request.parameters),
        request_hash=request.request_hash,
        configuration=request.parameters.get("configuration"),
        **options,
    )
    result=verify_drawing_bundle(folder,folder.name)
    print(json.dumps({"folder":str(folder),"manifest":result},
                     ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

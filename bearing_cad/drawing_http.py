"""Optional local RoBAS drawing endpoints for the existing CAD-V2 workbench.

The original 3D endpoint remains untouched. Drawing operations are available
only with explicitly configured local Windows CADImport/legacy resources.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
import secrets
import logging
import subprocess

from .contracts import ContractError,parse_request
from .drawing_variables import DrawingDataError
from .drawing_runner import (
    DrawingExportError, generate_drawing_bundle, verify_drawing_bundle, resolve_templates,
)

_DRAW_TOKEN=r"([a-f0-9]{32})"
SHEET_ROUTE=re.compile(r"^/api/v2/cad/drawings/"+_DRAW_TOKEN+r"/files/(assembly|outer_ring|inner_ring|cage|loose_rib)\.(dxf|svg)$")
MANIFEST_ROUTE=re.compile(r"^/api/v2/cad/drawings/"+_DRAW_TOKEN+r"$")
_OPTIONS={"model","accuracy_class","diameter_series","chamfer1_mm","chamfer2_mm","radial_clearance_group","legacy_values","checked_values"}

_REQUIRED_TEMPLATES = {
    "深沟球DWG": ("0_00KS.DWG", "0_01KS.DWG", "0_02.DWG", "0_07.DWG"),
    "角接触DWG": ("6_00_ZDSTW.dwg", "6_01SK.DWG", "6_02SK.DWG", "6_07_ZDST.dwg"),
    "单列圆柱DWG": ("N-00.dwg", "N-01.dwg", "N-02.dwg", "N-06.dwg"),
}
_REQUIRED_DATABASES = ("DGBData.db", "ACBData.db", "CRBData.db")
_REQUIRED_CSV = ("球轴承零件相关系数.csv", "圆柱滚子轴承相关系数.csv", "BallDB.csv", "CylinderRollerDB.csv", "CylinderRollerDiameterDB.csv")


def environment_check(resources: Path | None, bridge: Path | None) -> dict:
    """Return actionable readiness details without treating file presence as CAD success."""
    failures = []
    root = Path(resources).resolve() if resources is not None else None
    if os.name != "nt":
        failures.append("Windows x64 is required")
    if root is None or not root.is_dir():
        failures.append("RoBAS resources directory is missing")
    else:
        for directory, names in _REQUIRED_TEMPLATES.items():
            folder = root / "Resource" / "哑图" / directory
            available = {p.name.casefold(): p for p in folder.iterdir()} if folder.is_dir() else {}
            for name in names:
                path = available.get(name.casefold())
                if path is None:
                    failures.append("Missing DWG template: " + str(folder / name))
                elif path.read_bytes()[:4] != b"AC10":
                    failures.append("Invalid DWG signature: " + str(path))
        for name in _REQUIRED_DATABASES:
            database = root / "Data" / name
            if not database.is_file():
                failures.append("Missing SQLite database: " + name)
                continue
            try:
                import sqlite3
                with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
                    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    required = {"变量表", "倒角尺寸表"}
                    if name == "CRBData.db":
                        required.add("滚道宽度公差")
                    missing = sorted(required - tables)
                    if missing:
                        failures.append(f"SQLite {name} is missing required tables: {', '.join(missing)}")
                    elif "变量表" in tables:
                        columns = {row[1] for row in db.execute('PRAGMA table_info("变量表")')}
                        if not {"变量名", "变量值"}.issubset(columns):
                            failures.append(f"SQLite {name} has an incompatible 变量表 schema")
            except sqlite3.DatabaseError:
                failures.append("Invalid SQLite database: " + name)
        for name in _REQUIRED_CSV:
            csv_path = root / "Resource" / name
            if not csv_path.is_file():
                failures.append("Missing coefficient CSV: " + name)
            elif csv_path.stat().st_size == 0:
                failures.append("Empty coefficient CSV: " + name)
    bridge_path = Path(bridge).resolve() if bridge is not None else None
    if bridge_path is None or not bridge_path.is_file():
        failures.append("CADImport bridge executable is missing")
    elif bridge_path.suffix.lower() != ".exe":
        failures.append("CADImport bridge must be a Windows .exe")
    doctor = None
    if not failures and bridge_path is not None:
        try:
            result = subprocess.run([str(bridge_path), "doctor"], capture_output=True, text=True, timeout=10, check=False)
            doctor = json.loads(result.stdout) if result.stdout.strip() else {"error": result.stderr.strip()}
            if result.returncode != 0 or doctor.get("status") != "READY_FOR_DWG_PROBE":
                failures.append("CADImport bridge doctor failed")
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            failures.append("CADImport bridge doctor unavailable: " + str(error))
    return {"available": not failures, "failures": failures, "doctor": doctor}


def enabled(resources: Path | None,bridge: Path | None) -> bool:
    return environment_check(resources, bridge)["available"]


def drawing_status(handler,resources,bridge):
    check = environment_check(resources, bridge)
    supported = ["rolling.deep_groove_ball", "rolling.angular_contact_ball",
                 "rolling.cylindrical_roller:N"]
    if resources is not None:
        for variant in ("NU", "NJ", "NF", "NUP"):
            try:
                resolve_templates(Path(resources), "rolling.cylindrical_roller", variant)
            except (DrawingExportError, OSError):
                continue
            supported.append("rolling.cylindrical_roller:" + variant)
    handler._respond(200,{
        "available": check["available"],
        "failures": check["failures"],
        "doctor": check["doctor"],
        "mode":"original_robas_dwg_text_replacement",
        "supported_bearings":supported,
        "formats":["dxf"],
        "requires":"licensed Windows CADImportBridge.exe and original DWG/SQLite assets",
    })


def create_drawing(handler,data,root,resources,bridge,build_lock):
    if not enabled(resources,bridge):
        return handler._error(503,"DRAWING_BRIDGE_UNAVAILABLE",
                              "Original RoBAS DWG export requires configured Windows CADImport resources")
    if not isinstance(data,dict) or set(data)!={"design","drawing"}:
        return handler._error(422,"PARAMETER_INVALID","Expected design and drawing objects")
    options=data["drawing"]
    if not isinstance(options,dict) or set(options)-_OPTIONS:
        return handler._error(422,"PARAMETER_INVALID","Unknown drawing option")
    try:
        request=parse_request(data["design"])
    except ContractError as error:
        return handler._error(422,error.error_code,str(error),error.field_path)
    if not build_lock.acquire(blocking=False):
        return handler._error(503,"BUSY","CAD engine is processing another job")
    jid=secrets.token_hex(16)
    handler._set_job(jid,{"status":"running","kind":"robas_drawing"})
    try:
        output=generate_drawing_bundle(
            resources=Path(resources),bridge=Path(bridge),
            output_root=root/"drawings",
            bearing_type=request.bearing_type.value,parameters=dict(request.parameters),
            request_hash=request.request_hash,
            configuration=request.parameters.get("configuration"),
            **options)
        manifest=verify_drawing_bundle(output,output.name)
        if manifest["request_hash"] != request.request_hash:
            raise DrawingExportError("Drawing request hash mismatch")
        handler._set_job(jid,{"status":"succeeded","kind":"robas_drawing",
                             "bundle_key":output.name,"request_hash":request.request_hash})
        handler._respond(201,{"status":"succeeded","job_id":jid,
                              "manifest_url":"/api/v2/cad/drawings/"+jid,
                              "request_hash":request.request_hash})
    except (DrawingDataError,DrawingExportError,ValueError,KeyError) as error:
        handler._set_job(jid,{"status":"failed","kind":"robas_drawing",
                              "error_code":"DRAWING_INVALID"})
        if "license registration is required" in str(error).lower():
            return handler._error(503,"CADIMPORT_LICENSE_REQUIRED",
                                  "CADImport license registration is required before original DWG export",job_id=jid)
        return handler._error(422,"DRAWING_INVALID",str(error),job_id=jid)
    except (OSError,subprocess.SubprocessError) as error:
        logging.exception("Original RoBAS CADImport drawing export failed: %s",jid)
        handler._set_job(jid,{"status":"failed","kind":"robas_drawing",
                              "error_code":"DRAWING_EXPORT_FAILED"})
        detail = str(error)
        if "License is required" in detail or "license registration failed" in detail.lower():
            return handler._error(503,"CADIMPORT_LICENSE_REQUIRED",
                                  "CADImport license registration is required before original DWG export",job_id=jid)
        return handler._error(500,"DRAWING_EXPORT_FAILED",
                              "Original DWG export failed; inspect local server logs",job_id=jid)
    finally:
        build_lock.release()


def serve_drawing(handler,route,root):
    """Return True if this request was handled as a drawing route."""
    matched=SHEET_ROUTE.fullmatch(route or "")
    manifest_match=MANIFEST_ROUTE.fullmatch(route or "")
    if not matched and not manifest_match:
        return False
    job_id=(matched or manifest_match).group(1)
    job=handler._known_job(job_id)
    if not job or job.get("status")!="succeeded" or job.get("kind")!="robas_drawing":
        handler._error(404,"NOT_FOUND","Unknown RoBAS drawing artifact")
        return True
    try:
        base=(root/"drawings").resolve()
        folder=(base/job["bundle_key"]).resolve(strict=True)
        if folder.parent != base:
            raise DrawingExportError("Unsafe drawing artifact directory")
        manifest=verify_drawing_bundle(folder,job["bundle_key"])
        if manifest["request_hash"]!=job["request_hash"]:
            raise DrawingExportError("Drawing manifest request mismatch")
        if manifest_match:
            file_urls = {}
            for row in manifest["sheets"]:
                file_urls[row["file"]] = f"/api/v2/cad/drawings/{job_id}/files/{row['file']}"
                if row.get("preview_file"):
                    file_urls[row["preview_file"]] = f"/api/v2/cad/drawings/{job_id}/files/{row['preview_file']}"
            handler._respond(200,{
                "job_id":job_id,"manifest":manifest,
                "file_urls":file_urls})
            return True
        name=matched.group(2)+"."+matched.group(3)
        path=(folder/name).resolve(strict=True)
        if path.parent!=folder:
            raise DrawingExportError("Unsafe DXF path")
        handler.send_response(200)
        content_type = "application/dxf" if matched.group(3) == "dxf" else "image/svg+xml; charset=utf-8"
        handler.send_header("Content-Type",content_type)
        if matched.group(3) == "dxf":
            handler.send_header("Content-Disposition",f'attachment; filename="{name}"')
        else:
            handler.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        handler.send_header("Content-Length",str(path.stat().st_size))
        handler.send_header("Cache-Control","no-store")
        handler.send_header("X-Content-Type-Options","nosniff")
        handler.end_headers()
        if handler.command!="HEAD":
            with path.open("rb") as stream:
                while chunk:=stream.read(256*1024):
                    handler.wfile.write(chunk)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        handler._error(404,"DRAWING_ARTIFACT_INVALID",
                       "Missing or corrupted RoBAS DXF bundle")
    return True

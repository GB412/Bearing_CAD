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
    DrawingExportError, generate_drawing_bundle, verify_drawing_bundle,
)

_DRAW_TOKEN=r"([a-f0-9]{32})"
SHEET_ROUTE=re.compile(r"^/api/v2/cad/drawings/"+_DRAW_TOKEN+r"/files/(assembly|outer_ring|inner_ring|cage)\.dxf$")
MANIFEST_ROUTE=re.compile(r"^/api/v2/cad/drawings/"+_DRAW_TOKEN+r"$")
_OPTIONS={"model","accuracy_class","diameter_series","chamfer1_mm","chamfer2_mm","legacy_values","checked_values"}


def enabled(resources: Path | None,bridge: Path | None) -> bool:
    return (os.name=="nt" and resources is not None and bridge is not None and
            (Path(resources)/"Data"/"DGBData.db").is_file() and Path(bridge).is_file())


def drawing_status(handler,resources,bridge):
    handler._respond(200,{
        "available": enabled(resources,bridge),
        "mode":"original_robas_dwg_text_replacement",
        "supported_bearings":["rolling.deep_groove_ball","rolling.angular_contact_ball",
                              "rolling.cylindrical_roller:N"],
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
        return handler._error(422,"DRAWING_INVALID",str(error),job_id=jid)
    except (OSError,subprocess.SubprocessError):
        logging.exception("Original RoBAS CADImport drawing export failed: %s",jid)
        handler._set_job(jid,{"status":"failed","kind":"robas_drawing",
                              "error_code":"DRAWING_EXPORT_FAILED"})
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
            handler._respond(200,{
                "job_id":job_id,"manifest":manifest,
                "file_urls":{row["file"]:f"/api/v2/cad/drawings/{job_id}/files/{row['file']}"
                             for row in manifest["sheets"]}})
            return True
        name=matched.group(2)+".dxf"
        path=(folder/name).resolve(strict=True)
        if path.parent!=folder:
            raise DrawingExportError("Unsafe DXF path")
        handler.send_response(200)
        handler.send_header("Content-Type","application/dxf")
        handler.send_header("Content-Disposition",f'attachment; filename="{name}"')
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

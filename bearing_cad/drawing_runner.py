"""Invoke the original RoBAS DWG-template replacement workflow on Windows.

Does NOT derive geometry, infer tolerances, or reconstruct a drawing with OCCT.
This code only publishes outputs after all supplied variables and genuine
CADImport DXF exports have passed independent DXF verification.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile

import ezdxf

from .drawing_variables import prepare_variables, bridge_values

SHEETS = ("assembly", "outer_ring", "inner_ring", "cage")
TEMPLATES = {
    "rolling.deep_groove_ball": ("深沟球DWG",
        ("0_00KS.DWG", "0_01KS.DWG", "0_02.DWG", "0_07.DWG")),
    "rolling.angular_contact_ball": ("角接触DWG",
        ("6_00_ZDSTW.dwg", "6_01SK.DWG", "6_02SK.DWG", "6_07_ZDST.dwg")),
    "rolling.cylindrical_roller:N": ("单列圆柱DWG",
        ("N-00.dwg", "N-01.dwg", "N-02.dwg", "N-06.dwg")),
}


class DrawingExportError(RuntimeError):
    pass


def _digest(file: Path) -> str:
    h = sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_templates(resources: Path, bearing_type: str, configuration: str | None = None):
    kind = bearing_type
    if bearing_type == "rolling.cylindrical_roller":
        kind += ":" + (configuration or "")
    if kind not in TEMPLATES:
        raise DrawingExportError(f"No confirmed original RoBAS drawing templates for {kind}")
    subdir, names = TEMPLATES[kind]
    base = Path(resources) / "Resource" / "哑图" / subdir
    available = {file.name.casefold(): file for file in base.iterdir()} if base.is_dir() else {}
    selected = []
    for name in names:
        match = available.get(name.casefold())
        if match is None or match.is_symlink() or match.read_bytes()[:6] not in {b"AC1015", b"AC1021", b"AC1027"}:
            # Original provided RoBAS templates use AC1021 (DWG 2007),
            # with additional templates using AC1015 (DWG 2000).
            raise DrawingExportError(f"Missing or unsupported original DWG template: {name}")
        selected.append(match)
    return tuple(selected)


def generate_drawing_bundle(*, resources: Path, bridge: Path, output_root: Path,
                            bearing_type: str, parameters: dict,
                            request_hash: str, model: str | None = None,
                            accuracy_class: str | None = None,
                            checked_values: dict[str, str] | None = None,
                            configuration: str | None = None) -> Path:
    """Produce four DXF sheets with RoBAS's original TEXT replacement behavior.

    Empty SQLite variables become blank text as in original ChangeCADTexts.
    No independent 2D-vs-3D outline check or full-table completeness gate.
    The Windows CADImport real-DWG runtime remains mandatory.
    """
    templates = resolve_templates(resources, bearing_type, configuration)
    report = prepare_variables(resources=Path(resources), bearing_type=bearing_type,
                               parameters=parameters, model=model,
                               accuracy_class=accuracy_class,
                               checked_values=checked_values)
    # Faithfully reproduce FrmMain.ChangeCADTexts: all DataTable rows participate
    # in the original replacement loop, including blank/DBNull values.
    # The original software does not require the complete database to be filled.
    if os.name != "nt":
        raise DrawingExportError("CADImport bridge requires licensed Windows/.NET runtime")
    bridge = Path(bridge).resolve()
    if not bridge.is_file():
        raise DrawingExportError("Compiled licensed CADImportBridge.exe not found")
    if not isinstance(request_hash, str) or len(request_hash) != 64 or any(c not in "0123456789abcdef" for c in request_hash):
        raise DrawingExportError("Expected lowercase SHA256 of the confirmed 3D design request")
    target_root = Path(output_root)
    target_root.mkdir(parents=True, exist_ok=True)
    identity = sha256(json.dumps({
        "request_hash": request_hash, "db_sha256": report["database_sha256"],
        "templates_sha256": [_digest(template) for template in templates],
        "variables": bridge_values(report), "engine": "robas.dwg.cadimport.v1",
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    destination = target_root / identity
    if destination.exists():
        raise DrawingExportError("Preexisting drawing bundle requires independent verification")
    with tempfile.TemporaryDirectory(prefix=".drawing-staging-", dir=target_root) as temp:
        folder = Path(temp)
        mapping = folder / "variables.json"
        mapping.write_text(json.dumps(bridge_values(report), ensure_ascii=False), encoding="utf-8")
        sheets = []
        for name, template in zip(SHEETS, templates):
            output = folder / (name + ".dxf")
            result = subprocess.run(
                [str(bridge), "batch", str(template.resolve()), str(output), str(mapping)],
                capture_output=True, text=True, timeout=120, check=True)
            try:
                response = json.loads(result.stdout)
            except ValueError as error:
                raise DrawingExportError(f"CADImport response is not JSON for {name}") from error
            if response.get("exact_match_count", 0) < 1 or not output.is_file():
                raise DrawingExportError(f"CADImport did not replace any TEXT in {name}")
            # Audit the exported DXF only. Template outline versus the 3D
            # model, and reference DXF geometry comparisons, are NOT required
            # by the original RoBAS TEXT-replacement workflow.
            document = ezdxf.readfile(str(output))
            audit = document.audit()
            if audit.errors:
                raise DrawingExportError(
                    f"DXF fatal audit errors in {name}: {len(audit.errors)}")
            sheets.append({
                "view": name, "file": output.name, "size_bytes": output.stat().st_size,
                "sha256": _digest(output), "template_sha256": _digest(template),
                "text_replacements": response["exact_match_count"],
                "dxf_audit_nonfatal_fixes": len(audit.fixes),
                "non_text_entities": response.get("non_text_entity_count"),
            })
        manifest = {
            "schema_version": "robas.drawing.bundle.v1",
            "status": "ROBAS_TEMPLATE_TEXT_EXPORTED_UNREVIEWED",
            "unfilled_database_variable_names": report["unresolved_names"],
            "unfilled_database_variable_count": report["unresolved_count"],
            "manufacturing_approved": False,
            "bearing_type": bearing_type,
            "request_hash": request_hash,
            "database_sha256": report["database_sha256"],
            "bundle_key": identity,
            "engine": "CADImport original DWG template TEXT replacement",
            "sheets": sheets,
        }
        (folder / "drawing_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        mapping.unlink()  # Source variable values remain in the source SQLite DB.
        folder.rename(destination)  # Only complete, audited output is published.
    return destination

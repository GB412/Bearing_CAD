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
from .drawing_reference import compare_reference

SHEETS = ("assembly", "outer_ring", "inner_ring", "cage")
REFERENCE_DXF = {
    "rolling.deep_groove_ball": ("深沟球轴承总图.dxf", "深沟球轴承外圈.dxf", "深沟球轴承内圈.dxf", "深沟球轴承保持架.dxf"),
    "rolling.angular_contact_ball": ("角接触球轴承总图.dxf", "角接触球轴承外圈.dxf", "角接触球轴承内圈.dxf", "角接触球轴承保持架.dxf"),
    "rolling.cylindrical_roller": ("单列圆柱滚子轴承总图.dxf", "单列圆柱滚子轴承外圈.dxf", "单列圆柱滚子轴承内圈.dxf", "单列圆柱滚子轴承保持架.dxf"),
}
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
    """Fail closed unless every drawing variable has an externally known value.

    The original RoBAS database is mostly null. This strict gate remains
    blocked until the full SetCADTextValue/standards mapping has been ported
    and reviewed. No production output is claimed in the meantime.
    """
    templates = resolve_templates(resources, bearing_type, configuration)
    report = prepare_variables(resources=Path(resources), bearing_type=bearing_type,
                               parameters=parameters, model=model,
                               accuracy_class=accuracy_class,
                               checked_values=checked_values)
    if report["unresolved_count"]:
        raise DrawingExportError(
            f"RoBAS drawing data incomplete: {report['unresolved_count']} variable names "
            f"(including {report['unresolved_ratings']}); no DXF generated")
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
            # Original RoBAS reference DXFs contain known recoverable
            # header/dictionary handle fixes (Auditor code 202); those alone
            # do not mean the newly exported geometry is incorrect.
            reference = Path(resources) / "temp" / REFERENCE_DXF[bearing_type][len(sheets)]
            if not reference.is_file():
                raise DrawingExportError(f"Missing original RoBAS reference DXF: {reference.name}")
            fidelity = compare_reference(reference, output)
            if fidelity["blocking_findings"]:
                raise DrawingExportError(f"Generated DXF differs from original non-text drawing geometry: {fidelity['blocking_findings']}")
            sheets.append({
                "view": name, "file": output.name, "size_bytes": output.stat().st_size,
                "sha256": _digest(output), "template_sha256": _digest(template),
                "text_replacements": response["exact_match_count"],
                "reference_comparison": fidelity["status"],
                "reference_review_warnings": fidelity["review_warnings"],
                "audit_fix_count": fidelity["generated"]["audit_fixes"],
                "non_text_entities": response.get("non_text_entity_count"),
            })
        manifest = {
            "schema_version": "robas.drawing.bundle.v1",
            "status": "DXF_EXPORTED_UNREVIEWED",
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
        mapping.unlink()  # Detailed source values stay in the private upstream context.
        folder.rename(destination)  # Only complete, audited output is published.
    return destination

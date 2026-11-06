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
from .drawing_preview import render_svg_preview

from .drawing_variables import prepare_variables, bridge_values, restore_checked_values
from .drawing_legacy_technical import technical_condition_rows, apply_technical_conditions
from .drawing_legacy_chamfer import apply_robas_chamfer
from .drawing_legacy_dimensions import apply_deep_groove_dimensions, apply_angular_contact_dimensions
from .drawing_legacy_roller import apply_cylindrical_roller_dimensions
from .drawing_legacy_ratings import apply_robas_loads
from .drawing_standard_fill import apply_robas_drawing_standards
from .drawing_legacy_design import derive_dgb_drawing_values
from .drawing_legacy_acb_cage import derive_acb_cage_drawing_values
from .drawing_legacy_acb_race import derive_acb_race_drawing_values
from .drawing_legacy_crb_source import derive_crb_source_drawing_values
from .contracts import CageSpec
from .drawing_diagnostics import sheet_variable_diagnostics, bundle_variable_diagnostics

SHEETS = ("assembly", "outer_ring", "inner_ring", "cage")
SHEETS_NUP = (*SHEETS, "loose_rib")
TEMPLATES = {
    "rolling.deep_groove_ball": ("深沟球DWG",
        ("0_00KS.DWG", "0_01KS.DWG", "0_02.DWG", "0_07.DWG")),
    "rolling.angular_contact_ball": ("角接触DWG",
        ("6_00_ZDSTW.dwg", "6_01SK.DWG", "6_02SK.DWG", "6_07_ZDST.dwg")),
    "rolling.cylindrical_roller:N": ("单列圆柱DWG",
        ("N-00.dwg", "N-01.dwg", "N-02.dwg", "N-06.dwg")),
    # These are source-file-backed composition candidates, NOT an original
    # FrmMain.cs switch (that entry only selects N). A Windows CAD/AutoCAD
    # review must confirm shared drawings and the NUP loose-rib designation.
    "rolling.cylindrical_roller:NU": ("单列圆柱DWG",
        ("NU-00.dwg", "NU-01.dwg", "NU-02.dwg", "N-06.dwg")),
    "rolling.cylindrical_roller:NJ": ("单列圆柱DWG",
        ("NJ-00.dwg", "NU-01.dwg", "NJ-02.dwg", "N-06.dwg")),
    "rolling.cylindrical_roller:NF": ("单列圆柱DWG",
        ("NF-00.dwg", "NF-01.dwg", "N-02.dwg", "N-06.dwg")),
    "rolling.cylindrical_roller:NUP": ("单列圆柱DWG",
        ("NUP-00.dwg", "NU-01.dwg", "NUP-02.dwg", "N-06.dwg", "NUP-12.dwg")),
}


class DrawingExportError(RuntimeError):
    pass


def _source_audit_cache_marker(bearing_type: str, evidence: dict | None) -> dict:
    """Re-export DGB outputs when source/CAD shoulder evidence changes.

    Cached drawing manifests are immutable; adding metadata only to the
    manifest without changing the key could keep showing an old diagnosis.
    Other bearing types retain their existing cache identity.
    """
    if bearing_type != "rolling.deep_groove_ball":
        return {}
    evidence = evidence or {}
    return {"dgb_shoulder_source_audit": {
        "source_mm": evidence.get("original_source_shoulder_mm", {}),
        "matches_cad": evidence.get("original_source_shoulder_matches_cad", {}),
    }}


def _acb_cage_getter_cache_marker(bearing_type: str) -> dict:
    """Ensure old ACB manifests cannot mask a revised 2D getter contract.

    Immutable drawing bundles must be regenerated even when rounded TEXT
    happens to be identical but the source provenance fields have changed.
    Other bearing types preserve their previous cache identity.
    """
    return ({"acb_cage_getter_precision": "robas.public-getters.v1"}
            if bearing_type == "rolling.angular_contact_ball" else {})


def _crb_drawing_getter_cache_marker(bearing_type: str) -> dict:
    """Version original CRB getter-parity output without invalidating others."""
    return ({"crb_drawing_getter_parity": "robas.crb-public-getters.v1"}
            if bearing_type == "rolling.cylindrical_roller" else {})


def _digest(file: Path) -> str:
    h = sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()




def verify_drawing_bundle(folder: Path, expected_key: str | None = None) -> dict:
    """Verify a complete previously exported RoBAS four-sheet DXF bundle."""
    folder = Path(folder)
    manifest = json.loads((folder / "drawing_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "robas.drawing.bundle.v1":
        raise DrawingExportError("Unsupported RoBAS drawing manifest")
    if expected_key is not None and manifest.get("bundle_key") != expected_key:
        raise DrawingExportError("RoBAS drawing cache identity mismatch")
    sheets = manifest.get("sheets")
    if not isinstance(sheets, list) or len(sheets) not in {4, 5}:
        raise DrawingExportError("Incomplete RoBAS drawing manifest")
    target_views = (SHEETS_NUP if manifest.get("bearing_type") == "rolling.cylindrical_roller"
                    and manifest.get("configuration") == "NUP" else SHEETS)
    if [sheet.get("view") for sheet in sheets] != list(target_views):
        raise DrawingExportError("Unexpected drawing-sheet order")
    for sheet in sheets:
        name = sheet.get("file")
        if not isinstance(name, str) or name != Path(name).name or name not in {
            "assembly.dxf", "outer_ring.dxf", "inner_ring.dxf", "cage.dxf", "loose_rib.dxf"
        }:
            raise DrawingExportError("Unsafe drawing-sheet filename")
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != sheet.get("size_bytes"):
            raise DrawingExportError("Missing or modified DXF: " + name)
        if _digest(path) != sheet.get("sha256"):
            raise DrawingExportError("DXF checksum mismatch: " + name)
        preview_name = sheet.get("preview_file")
        if preview_name:
            preview = folder / preview_name
            if (preview_name != Path(preview_name).name or
                    preview.suffix.lower() != ".svg" or
                    not preview.is_file() or
                    preview.stat().st_size != sheet.get("preview_size_bytes") or
                    _digest(preview) != sheet.get("preview_sha256")):
                raise DrawingExportError("Missing or modified SVG preview: " + name)
    return manifest


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
                            configuration: str | None = None,
                            diameter_series: str | None = None,
                            radial_clearance_group: str | None = None,
                            chamfer1_mm: float | None = None,
                            chamfer2_mm: float | None = None,
                            legacy_values: dict | None = None,
                            cage: CageSpec | None = None) -> Path:
    """Produce four DXF sheets with RoBAS's original TEXT replacement behavior.

    Empty SQLite variables become blank text as in original ChangeCADTexts.
    No independent 2D-vs-3D outline check or full-table completeness gate.
    The Windows CADImport real-DWG runtime remains mandatory.
    """
    templates = resolve_templates(resources, bearing_type, configuration)
    views = (SHEETS_NUP if bearing_type == "rolling.cylindrical_roller"
             and configuration == "NUP" else SHEETS)
    if len(templates) != len(views):
        raise DrawingExportError("Selected template set has an incorrect number of sheets")
    if os.name != "nt":
        raise DrawingExportError("CADImport bridge requires licensed Windows/.NET runtime")
    # Fail before reading/calculating the large legacy variable set when the
    # required executable is absent. This keeps status and CLI errors specific.
    bridge = Path(bridge).resolve()
    if not bridge.is_file():
        raise DrawingExportError("Compiled licensed CADImportBridge.exe not found")
    report = prepare_variables(resources=Path(resources), bearing_type=bearing_type,
                               parameters=parameters, model=model,
                               accuracy_class=accuracy_class,
                               checked_values=checked_values)
    validated_input_report = report
    if legacy_values is not None and not isinstance(legacy_values, dict):
        raise DrawingExportError("legacy_values must be an explicit mapping")
    auto_evidence = None
    actual_legacy = dict(legacy_values or {})
    if bearing_type == "rolling.deep_groove_ball":
        auto_values, auto_evidence = derive_dgb_drawing_values(
            parameters=parameters, cage=cage, resources=Path(resources),
            chamfer1_mm=chamfer1_mm,
            radial_clearance_group=radial_clearance_group,
            bearing_model=model)
        # Any explicitly supplied, checked old-model value takes precedence.
        actual_legacy = {**auto_values, **actual_legacy}
    if bearing_type == "rolling.angular_contact_ball":
        race_auto, race_evidence = derive_acb_race_drawing_values(parameters)
        cage_auto, cage_evidence = derive_acb_cage_drawing_values(
            parameters=parameters, cage=cage)
        # Reviewed legacy values can override the nominal constructor-derived
        # source labels. Never change the actual OCCT design parameters here.
        actual_legacy = {**race_auto, **cage_auto, **actual_legacy}
        auto_evidence = {
            "source": "RoBAS ACBGeometry and StraightPocketCage",
            "autofilled_input_keys": sorted(set(race_auto) | set(cage_auto)),
            "race": race_evidence,
            "cage": cage_evidence,
            "warnings": race_evidence["warnings"] + cage_evidence["warnings"],
        }
    if bearing_type == "rolling.deep_groove_ball":
        report = apply_deep_groove_dimensions(
            report=report, parameters=parameters, legacy_values=actual_legacy)
    if bearing_type == "rolling.angular_contact_ball":
        report = apply_angular_contact_dimensions(
            report=report, parameters=parameters, legacy_values=actual_legacy)
    if bearing_type == "rolling.cylindrical_roller":
        crb_auto, auto_evidence = derive_crb_source_drawing_values(parameters)
        actual_legacy = {**crb_auto, **actual_legacy}
        report = apply_cylindrical_roller_dimensions(
            report=report, parameters=parameters, legacy_values=actual_legacy,
            resources=Path(resources))
    report = apply_robas_loads(
        report=report, resources=Path(resources),
        bearing_type=bearing_type, parameters=parameters)
    if chamfer1_mm is not None:
        report = apply_robas_chamfer(
            report=report, resources=Path(resources),
            bearing_type=bearing_type,
            chamfer1_mm=chamfer1_mm, chamfer2_mm=chamfer2_mm)
    if diameter_series is not None:
        if accuracy_class is None:
            raise DrawingExportError("RoBAS technical conditions require accuracy_class")
        lookups = technical_condition_rows(
            resources=Path(resources), bearing_type=bearing_type,
            bore_d_mm=parameters["bore_d_mm"],
            outside_d_mm=parameters["outside_d_mm"],
            accuracy_class=accuracy_class,
            diameter_series=diameter_series)
        report = apply_technical_conditions(report, lookups)
    report = apply_robas_drawing_standards(
        report=report, resources=Path(resources),
        bearing_type=bearing_type, bore_d_mm=parameters["bore_d_mm"],
        accuracy_class=accuracy_class, diameter_series=diameter_series,
        radial_clearance_group=radial_clearance_group)
    # Reapply explicitly checked engineering values, validated on input, only
    # after all automatic source calculations and lookup-table overlays.
    report = restore_checked_values(report, validated_input_report, checked_values)
    # Faithfully reproduce FrmMain.ChangeCADTexts: all DataTable rows participate
    # in the original replacement loop, including blank/DBNull values.
    # The original software does not require the complete database to be filled.
    if not isinstance(request_hash, str) or len(request_hash) != 64 or any(c not in "0123456789abcdef" for c in request_hash):
        raise DrawingExportError("Expected lowercase SHA256 of the confirmed 3D design request")
    target_root = Path(output_root)
    target_root.mkdir(parents=True, exist_ok=True)
    identity = sha256(json.dumps({
        "request_hash": request_hash, "db_sha256": report["database_sha256"],
        "templates_sha256": [_digest(template) for template in templates],
        "variables": bridge_values(report), "engine": "robas.dwg.cadimport.v1.svgpreview.v3.variable-diagnostics.v1.standards.v1.design-values.v1",
        "radial_clearance_group": radial_clearance_group,
        **_source_audit_cache_marker(bearing_type, auto_evidence),
        **_acb_cage_getter_cache_marker(bearing_type),
        **_crb_drawing_getter_cache_marker(bearing_type),
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    destination = target_root / identity
    if destination.exists():
        verify_drawing_bundle(destination, identity)
        return destination
    with tempfile.TemporaryDirectory(prefix=".drawing-staging-", dir=target_root) as temp:
        folder = Path(temp)
        mapping = folder / "variables.json"
        mapping.write_text(json.dumps(bridge_values(report), ensure_ascii=False), encoding="utf-8")
        sheets = []
        for name, template in zip(views, templates):
            output = folder / (name + ".dxf")
            try:
                result = subprocess.run(
                    [str(bridge), "batch", str(template.resolve()), str(output), str(mapping)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=120, check=True)
            except subprocess.CalledProcessError as error:
                detail = (error.stderr or error.stdout or "").strip()
                if "license is required" in detail.lower() or "license registration failed" in detail.lower():
                    raise DrawingExportError("CADImport license registration is required") from error
                raise DrawingExportError(
                    f"CADImport bridge failed for {name}: {detail or error}"
                ) from error
            try:
                response = json.loads(result.stdout)
            except ValueError as error:
                raise DrawingExportError(f"CADImport response is not JSON for {name}") from error
            if response.get("exact_match_count", 0) < 1 or not output.is_file():
                raise DrawingExportError(f"CADImport did not replace any TEXT in {name}")
            try:
                variable_diagnostics = sheet_variable_diagnostics(report, response.get("matched_keys"))
            except ValueError as error:
                raise DrawingExportError(f"Invalid CADImport TEXT-key diagnostics in {name}") from error
            # Audit the exported DXF only. Template outline versus the 3D
            # model, and reference DXF geometry comparisons, are NOT required
            # by the original RoBAS TEXT-replacement workflow.
            document = ezdxf.readfile(str(output))
            audit = document.audit()
            if audit.errors:
                raise DrawingExportError(
                    f"DXF fatal audit errors in {name}: {len(audit.errors)}")
            preview = folder / (name + ".svg")
            preview_report = render_svg_preview(output, preview)
            sheets.append({
                "view": name, "file": output.name, "size_bytes": output.stat().st_size,
                "sha256": _digest(output), "template_sha256": _digest(template),
                "preview_file": preview.name, "preview_size_bytes": preview.stat().st_size,
                "preview_sha256": _digest(preview),
                "preview_diagnostics": preview_report,
                "variable_diagnostics": variable_diagnostics,
                "text_replacements": response["exact_match_count"],
                "dxf_audit_nonfatal_fixes": len(audit.fixes),
                "non_text_entities": response.get("non_text_entity_count"),
            })
        drawing_diagnostics = bundle_variable_diagnostics(report, sheets)
        manifest = {
            "schema_version": "robas.drawing.bundle.v1",
            "status": "ROBAS_TEMPLATE_TEXT_EXPORTED_UNREVIEWED",
            "unfilled_database_variable_names": report["unresolved_names"],
            "unfilled_database_variable_count": report["unresolved_count"],
            **drawing_diagnostics,
            "technical_condition_rows": report.get("technical_rows_applied", 0),
            "legacy_design_evidence": auto_evidence,
            "standard_lookup_evidence": report.get("standard_lookup_evidence", []),
            "standard_lookup_warnings": report.get("standard_lookup_warnings", []),
            "radial_clearance_group": radial_clearance_group,
            "diameter_series": diameter_series,
            "chamfer_lookup_warning": report.get("chamfer_lookup_warning"),
            "accuracy_class": accuracy_class,
            "robas_load_evidence": report.get("legacy_load_evidence"),
            "manufacturing_approved": False,
            "bearing_type": bearing_type,
            "configuration": configuration,
            "template_composition_review": (
                "ORIGINAL_FRMMAIN_N_SET" if bearing_type != "rolling.cylindrical_roller"
                or configuration == "N" else "INFERRED_SOURCE_FILES_AUTOCAD_REVIEW_REQUIRED"),
            "request_hash": request_hash,
            "database_sha256": report["database_sha256"],
            "bundle_key": identity,
            "engine": "CADImport original DWG template TEXT replacement",
            "sheets": sheets,
        }
        (folder / "drawing_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        mapping.unlink()  # Source variable values remain in the source SQLite DB.
        verify_drawing_bundle(folder, identity)
        try:
            folder.rename(destination)
        except OSError:
            if not destination.exists():
                raise
            verify_drawing_bundle(destination, identity)
    return destination

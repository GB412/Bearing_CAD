"""Invoke the original RoBAS DWG-template replacement workflow on Windows.

Does NOT derive geometry, infer tolerances, or reconstruct a drawing with OCCT.
This code only publishes outputs after all supplied variables and genuine
CADImport DXF exports have passed independent DXF verification.
"""
from __future__ import annotations

from copy import copy
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile

import ezdxf
from ezdxf.entities import Text
from ezdxf.fonts import fonts
from ezdxf.lldxf.encoding import decode_mif_to_unicode, has_mif_encoding
from ezdxf.math import BoundingBox2d
from ezdxf.addons.drawing import Frontend, RenderContext, layout
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.svg import SVGBackend

from .drawing_variables import prepare_variables, bridge_values
from .drawing_legacy_technical import technical_condition_rows, apply_technical_conditions
from .drawing_legacy_chamfer import apply_robas_chamfer
from .drawing_legacy_dimensions import apply_deep_groove_dimensions, apply_angular_contact_dimensions
from .drawing_legacy_roller import apply_cylindrical_roller_dimensions
from .drawing_legacy_ratings import apply_robas_loads

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


def _preview_cjk_font():
    # Use installed fonts only. ezdxf does not combine a SHX font with its bigfont.
    for name in ("simsun.ttc", "msyh.ttc", "simhei.ttf",
                 "NotoSansCJK-Regular.ttc", "NotoSerifCJK-Regular.ttc"):
        if fonts.font_manager.has_font(name):
            return fonts.font_manager.get_font_face(name)
    return None


class _PreviewFrontend(Frontend):
    """Interpret CAD MIF text for display without editing the source entities."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cjk_font = _preview_cjk_font()
        self.warned_missing_cjk = False

    def draw_text_entity(self, entity, properties):
        if isinstance(entity, Text):
            text = entity.dxf.text
            if has_mif_encoding(text):
                entity = entity.copy()
                entity.dxf.text = text = decode_mif_to_unicode(text)
            if any("\u2e80" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff" for char in text):
                if self.cjk_font is not None:
                    properties = copy(properties)
                    properties.font = self.cjk_font
                elif not self.warned_missing_cjk:
                    logging.getLogger(__name__).warning(
                        "SVG preview: no supported installed CJK font; Chinese glyphs may be missing. "
                        "DXF text and font references are unchanged.")
                    self.warned_missing_cjk = True
        super().draw_text_entity(entity, properties)


def _render_svg_preview(dxf_path: Path, svg_path: Path) -> None:
    """Render the exported DXF itself with a small, per-sheet viewport margin."""
    document = ezdxf.readfile(str(dxf_path))
    backend = SVGBackend()
    config = Configuration(
        color_policy=ColorPolicy.COLOR,
        background_policy=BackgroundPolicy.MODELSPACE,
        lineweight_scaling=0.5,
    )
    _PreviewFrontend(RenderContext(document), backend, config).draw_layout(
        document.modelspace(), finalize=True)
    content = backend.player().bbox()
    if not content.has_data:
        raise DrawingExportError(f"Cannot create SVG preview for empty DXF: {dxf_path.name}")
    min_x, min_y = content.extmin
    max_x, max_y = content.extmax
    margin = max(content.size.x, content.size.y) * 0.04
    render_box = BoundingBox2d((
        (min_x - margin, min_y - margin),
        (max_x + margin, max_y + margin),
    ))
    svg_path.write_text(
        backend.get_string(layout.Page(0, 0), render_box=render_box),
        encoding="utf-8",
    )


def verify_drawing_bundle(folder: Path, expected_key: str | None = None) -> dict:
    """Verify a complete previously exported RoBAS four-sheet DXF bundle."""
    folder = Path(folder)
    manifest = json.loads((folder / "drawing_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "robas.drawing.bundle.v1":
        raise DrawingExportError("Unsupported RoBAS drawing manifest")
    if expected_key is not None and manifest.get("bundle_key") != expected_key:
        raise DrawingExportError("RoBAS drawing cache identity mismatch")
    sheets = manifest.get("sheets")
    if not isinstance(sheets, list) or len(sheets) != 4:
        raise DrawingExportError("Incomplete RoBAS four-sheet manifest")
    if [sheet.get("view") for sheet in sheets] != list(SHEETS):
        raise DrawingExportError("Unexpected drawing-sheet order")
    for sheet in sheets:
        name = sheet.get("file")
        if not isinstance(name, str) or name != Path(name).name or name not in {
            "assembly.dxf", "outer_ring.dxf", "inner_ring.dxf", "cage.dxf"
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
                            chamfer1_mm: float | None = None,
                            chamfer2_mm: float | None = None,
                            legacy_values: dict | None = None) -> Path:
    """Produce four DXF sheets with RoBAS's original TEXT replacement behavior.

    Empty SQLite variables become blank text as in original ChangeCADTexts.
    No independent 2D-vs-3D outline check or full-table completeness gate.
    The Windows CADImport real-DWG runtime remains mandatory.
    """
    templates = resolve_templates(resources, bearing_type, configuration)
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
    if bearing_type == "rolling.deep_groove_ball":
        report = apply_deep_groove_dimensions(
            report=report, parameters=parameters, legacy_values=legacy_values)
    if bearing_type == "rolling.angular_contact_ball":
        report = apply_angular_contact_dimensions(
            report=report, parameters=parameters, legacy_values=legacy_values)
    if bearing_type == "rolling.cylindrical_roller":
        report = apply_cylindrical_roller_dimensions(
            report=report, parameters=parameters, legacy_values=legacy_values,
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
        "variables": bridge_values(report), "engine": "robas.dwg.cadimport.v1.svgpreview.v2",
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
        for name, template in zip(SHEETS, templates):
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
            # Audit the exported DXF only. Template outline versus the 3D
            # model, and reference DXF geometry comparisons, are NOT required
            # by the original RoBAS TEXT-replacement workflow.
            document = ezdxf.readfile(str(output))
            audit = document.audit()
            if audit.errors:
                raise DrawingExportError(
                    f"DXF fatal audit errors in {name}: {len(audit.errors)}")
            preview = folder / (name + ".svg")
            _render_svg_preview(output, preview)
            sheets.append({
                "view": name, "file": output.name, "size_bytes": output.stat().st_size,
                "sha256": _digest(output), "template_sha256": _digest(template),
                "preview_file": preview.name, "preview_size_bytes": preview.stat().st_size,
                "preview_sha256": _digest(preview),
                "text_replacements": response["exact_match_count"],
                "dxf_audit_nonfatal_fixes": len(audit.fixes),
                "non_text_entities": response.get("non_text_entity_count"),
            })
        manifest = {
            "schema_version": "robas.drawing.bundle.v1",
            "status": "ROBAS_TEMPLATE_TEXT_EXPORTED_UNREVIEWED",
            "unfilled_database_variable_names": report["unresolved_names"],
            "unfilled_database_variable_count": report["unresolved_count"],
            "technical_condition_rows": report.get("technical_rows_applied", 0),
            "diameter_series": diameter_series,
            "chamfer_lookup_warning": report.get("chamfer_lookup_warning"),
            "accuracy_class": accuracy_class,
            "robas_load_evidence": report.get("legacy_load_evidence"),
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
        verify_drawing_bundle(folder, identity)
        try:
            folder.rename(destination)
        except OSError:
            if not destination.exists():
                raise
            verify_drawing_bundle(destination, identity)
    return destination

"""Read-only PR-2D-09 acceptance evidence for actual RoBAS CADImport bundles.

Run on Windows AFTER generating fresh DXF/SVG through the licensed bridge.
This audit can also run on Linux fixtures; it never claims that such fixtures
prove Windows CADImport, AutoCAD font/layout, or manufacturing approval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import ezdxf

from .drawing_runner import verify_drawing_bundle

_SCHEMA = "robas.2d.acceptance.v1"
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_REQUIRED_CASES = (
    "rolling.deep_groove_ball",
    "rolling.angular_contact_ball",
    "rolling.cylindrical_roller:N",
    "rolling.cylindrical_roller:NU",
    "rolling.cylindrical_roller:NJ",
    "rolling.cylindrical_roller:NF",
    "rolling.cylindrical_roller:NUP",
)
_ISSUE_TYPES = (
    "SOURCE_CALCULATION",
    "FIELD_APPLICABILITY",
    "CADIMPORT_TEXT_REPLACEMENT",
    "ORIGINAL_DWG_TEMPLATE",
    "SVG_PREVIEW_ONLY",
)


def _case_type(manifest: dict) -> str:
    bearing = manifest["bearing_type"]
    if bearing == "rolling.cylindrical_roller":
        return bearing + ":" + str(manifest.get("configuration") or "")
    return bearing


def inspect_case(label: str, folder: Path) -> dict:
    """Inspect disk evidence without modifying source DXF or the manifest."""
    result = {
        "label": label,
        "bundle_directory": str(folder),
        "automatic_status": "FAILED",
        "windows_cadimport_verified": "NOT_VERIFIED_BY_THIS_TOOL",
        "autocad_reviewed": "NOT_VERIFIED_BY_THIS_TOOL",
        "manufacturing_approved": False,
        "blocking_errors": [],
        "review_items": [],
        "sheets": [],
    }
    try:
        if folder.is_symlink():
            raise ValueError("Bundle directory must not be a symlink")
        manifest = verify_drawing_bundle(folder, expected_key=folder.name)
        if manifest.get("manufacturing_approved") is not False:
            raise ValueError("Manifest must explicitly retain manufacturing_approved=false")
        if not isinstance(manifest.get("drawing_model_consistency"), dict):
            raise ValueError("Stale drawing: missing PR-2D-08 model evidence")
        if not isinstance(manifest.get("legacy_input_override_evidence"), dict):
            raise ValueError("Stale drawing: missing legacy-input provenance")
        if not isinstance(manifest.get("request_hash"), str) or len(manifest["request_hash"]) != 64:
            raise ValueError("Missing confirmed-design request SHA256")
        result.update({
            "case_type": _case_type(manifest),
            "bundle_key": manifest["bundle_key"],
            "request_hash": manifest["request_hash"],
            "database_sha256": manifest.get("database_sha256"),
            "model_consistency": manifest["drawing_model_consistency"],
            "template_composition_review": manifest.get("template_composition_review"),
            "unfilled_template_variables": manifest.get("unfilled_template_variable_names", []),
            "unfilled_database_unused_count": manifest.get("unfilled_database_unused_count"),
            "source_conflict_template_variables": manifest.get(
                "source_conflict_template_variable_names", []),
            "suspected_unmapped_template_texts": manifest.get(
                "suspected_unmapped_template_texts", []),
            "standard_lookup_warnings": manifest.get("standard_lookup_warnings", []),
            "robas_load_evidence": manifest.get("robas_load_evidence"),
            "legacy_design_evidence": manifest.get("legacy_design_evidence"),
        })
        for sheet in manifest["sheets"]:
            required = ("template_file", "template_sha256", "preview_file",
                        "preview_sha256", "variable_diagnostics",
                        "suspected_unmapped_text_diagnostics")
            missing = [name for name in required if name not in sheet]
            if missing:
                raise ValueError("Stale sheet %s: missing %s" %
                                 (sheet["view"], ", ".join(missing)))
            diagnosis = sheet["variable_diagnostics"]
            if not isinstance(diagnosis.get("matched_variable_provenance"), list):
                raise ValueError("Stale sheet: missing matched-variable provenance")
            if type(sheet.get("text_replacements")) is not int or sheet["text_replacements"] < 1:
                raise ValueError("No original CADImport TEXT replacements recorded")
            doc = ezdxf.readfile(str(folder / sheet["file"]))
            audit = doc.audit()
            if audit.errors:
                raise ValueError("Fatal DXF audit errors in %s: %d" %
                                 (sheet["file"], len(audit.errors)))
            entity_types = Counter(entity.dxftype() for entity in doc.modelspace())
            styles = sorted({
                entity.dxf.get("style", "Standard")
                for entity in doc.modelspace()
                if entity.dxftype() in ("TEXT", "MTEXT")
            })
            used_fonts = []
            for name in styles:
                style = doc.styles.get(name)
                used_fonts.append({
                    "style": name,
                    "font_reference": style.dxf.get("font", "") if style else None,
                    "bigfont_reference": style.dxf.get("bigfont", "") if style else None,
                })
            result["sheets"].append({
                "view": sheet["view"],
                "dxf_file": sheet["file"],
                "dxf_sha256": sheet["sha256"],
                "svg_file": sheet["preview_file"],
                "svg_sha256": sheet["preview_sha256"],
                "original_template_file": sheet["template_file"],
                "original_template_sha256": sheet["template_sha256"],
                "cadimport_text_replacements_reported": sheet["text_replacements"],
                "entity_counts": dict(sorted(entity_types.items())),
                "source_matched_variable_provenance": diagnosis["matched_variable_provenance"],
                "source_matched_blank_names": diagnosis.get("unfilled_variable_names", []),
                "suspected_unmapped_texts": sheet["suspected_unmapped_text_diagnostics"],
                "font_references": used_fonts,
                "nonfatal_dxf_audit_fixes": len(audit.fixes),
                "preview_font_warning": (
                    sheet.get("preview_diagnostics") or {}).get("preview_font_warning"),
                "autocad_visual_review": "NOT_REVIEWED",
            })
        if result["unfilled_template_variables"]:
            result["review_items"].append("TEMPLATE_USED_MISSING")
        if result["source_conflict_template_variables"]:
            result["review_items"].append("CONFLICTING_SOURCE_VARIABLE_ROWS")
        if result["suspected_unmapped_template_texts"]:
            result["review_items"].append("UNMAPPED_DXF_TEXT_REQUIRES_AUTOCAD_REVIEW")
        if result["standard_lookup_warnings"]:
            result["review_items"].append("STANDARD_LOOKUP_SOURCE_WARNINGS")
        model = manifest["drawing_model_consistency"]
        if model.get("warnings"):
            result["review_items"].append("MODEL_OR_CATALOG_UNVERIFIED")
        if str(manifest.get("template_composition_review", "")).startswith("INFERRED"):
            result["review_items"].append("INFERRED_CRB_TEMPLATE_COMPOSITION")
        if any(row["preview_font_warning"] for row in result["sheets"]):
            result["review_items"].append("SVG_FONT_PREVIEW_WARNING")
        result["automatic_status"] = "PASS_DXF_INTEGRITY_AUTOCAD_PENDING"
    except Exception as error:
        result["blocking_errors"].append(
            type(error).__name__ + ": " + str(error))
    return result


def _parse_case(spec: str) -> tuple[str, Path]:
    label, separator, location = spec.partition("=")
    if not separator or not _LABEL.fullmatch(label) or not location.strip():
        raise ValueError("Use --case LABEL=PATH (label: letters, digits, _, ., -)")
    return label, Path(location).expanduser().resolve()


def _checklist(cases: list[dict]) -> str:
    lines = [
        "# PR-2D-09 · AutoCAD 人工审图记录（全部待核实）",
        "",
        "**本文件由离线审计生成，不代表任何 AutoCAD 实机检查已经通过。**",
        "请在受授权的 Windows 电脑上打开下表每张真实 DXF，记录日期、",
        "CADImport 许可/版本、AutoCAD 版本、截图文件及人工审查人。",
        "原版 SHX 字体目录需添加到 AutoCAD 支持文件搜索路径；",
        "SVG 可辅助查看，不能替代 DXF 字体及工程标注审查。",
        "",
        "| 案例 | 图纸 | 原模板 | 图框/几何 | 中文/SHX 字体 | 尺寸/公差 | 游隙/粗糙度/技术条件 | 图签/型号/文字 | 截图与审查人 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for case in cases:
        for sheet in case["sheets"]:
            lines.append(
                "| {label} | {view} | {template} | 待审 | 待审 | 待审 | 待审 | 待审 | 待填写 |".format(
                    label=case["label"], view=sheet["view"],
                    template=sheet["original_template_file"]))
    lines.extend([
        "",
        "## 必须记录的五类缺陷",
        "",
        "源计算错误 / 字段适用条件错误 / CADImport TEXT 替换失败 /",
        "原 DWG 模板数据问题 / SVG 仅显示问题。",
        "不要将不同来源的问题合并为同一个原因。",
        "",
        "## 最终结论（须人工填写）",
        "",
        "- Windows CADImport 实际生成与授权记录：**未验证**",
        "- AutoCAD 图框、字体、尺寸、公差、技术文字：**未验证**",
        "- 专业工程审核 / 制造批准：**未批准**",
        "- 仍无法从原版源码/SQLite/CSV核实的字段：**待列出**",
        "",
        "此记录的人工勾选不会自动修改 drawing_manifest.json 的",
        "manufacturing_approved=false；工程批准是独立流程。",
        "",
    ])
    return "\n".join(lines)


def _markdown(report: dict) -> str:
    lines = [
        "# PR-2D-09 · RoBAS 二维真实 DXF 自动审计",
        "",
        "**自动文件审计与 AutoCAD/制造审查严格分离。**",
        "",
        "| 项目 | 结果 |",
        "|---|---|",
        f"| 本次自动检查通过 | {report['automatic_pass_count']} / {len(report['cases'])} |",
        "| Windows CADImport 实机真实性 | 本工具无法独立证实 |",
        "| AutoCAD 字体、尺寸、图签 | 未验收，见人工清单 |",
        "| 制造批准 | 未批准 |",
        "",
        "## 案例与逐张图纸",
        "",
        "| 案例 | 类型 | 自动状态 | 图纸数量 | 模板命中空项 | 来源疑点 |",
        "|---|---|---|---:|---:|---|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['label']} | {case.get('case_type', 'UNKNOWN')} | "
            f"{case['automatic_status']} | {len(case['sheets'])} | "
            f"{len(case.get('unfilled_template_variables', []))} | "
            f"{', '.join(case['review_items']) or '无自动发现'} |")
        for error in case["blocking_errors"]:
            lines.append(f"\n**{case['label']} 自动检查阻断：** {error}\n")
    lines.extend([
        "",
        "## 尚未覆盖的图纸构型（自动文件检查）",
        "",
        ", ".join(report["missing_automatic_cases"]) or "全部七类已提交文件审计",
        "",
        "请参阅 acceptance_report.json 获取每张 DXF 的源 DWG 文件名、",
        "SHA256、TEXT/MTEXT 实际实体数量、引用字体、变量值来源及空白命中项。",
        "这不是尺寸数值的独立 CAD 几何测量，也没有给出制造批准结论。",
        "",
    ])
    return "\n".join(lines)


def create_acceptance_package(specs: list[str], output: Path) -> dict:
    """Emit a new evidence directory; never overwrite existing review evidence."""
    parsed = [_parse_case(spec) for spec in specs]
    labels = [label for label, _ in parsed]
    if len(set(labels)) != len(labels):
        raise ValueError("Duplicate acceptance case labels")
    destination = output.expanduser().resolve()
    if destination.exists():
        raise FileExistsError("Review output already exists; choose a new directory")
    for _, folder in parsed:
        if destination == folder or folder in destination.parents:
            raise ValueError("Evidence output must be outside every source bundle")
    cases = [inspect_case(label, folder) for label, folder in parsed]
    passed_types = {
        case.get("case_type") for case in cases
        if case["automatic_status"] == "PASS_DXF_INTEGRITY_AUTOCAD_PENDING"
    }
    report = {
        "schema_version": _SCHEMA,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "READ_ONLY_DXF_MANIFEST_AUDIT_NOT_WINDOWS_ATTESTATION",
        "automatic_pass_count": len([
            case for case in cases
            if case["automatic_status"] == "PASS_DXF_INTEGRITY_AUTOCAD_PENDING"
        ]),
        "required_automatic_case_types": list(_REQUIRED_CASES),
        "missing_automatic_cases": [
            name for name in _REQUIRED_CASES if name not in passed_types
        ],
        "windows_cadimport_verified": "NOT_VERIFIED_BY_THIS_TOOL",
        "autocad_reviewed": "NOT_VERIFIED_BY_THIS_TOOL",
        "manufacturing_approved": False,
        "cases": cases,
    }
    destination.mkdir(parents=True)
    (destination / "acceptance_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (destination / "acceptance_report.md").write_text(
        _markdown(report), encoding="utf-8")
    (destination / "autocad_review_checklist.md").write_text(
        _checklist(cases), encoding="utf-8")
    with (destination / "defects_template.csv").open(
            "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("case", "sheet", "category", "severity",
                         "source_reference", "description", "screenshot_path",
                         "assignee", "status"))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", action="append", required=True, metavar="LABEL=PATH",
        help="label and absolute/relative path to a freshly generated drawing bundle")
    parser.add_argument(
        "--out", required=True, type=Path,
        help="new directory for local acceptance evidence (not overwritten)")
    args = parser.parse_args(argv)
    try:
        report = create_acceptance_package(args.case, args.out)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({
        "report": str(args.out),
        "automatic_pass_count": report["automatic_pass_count"],
        "case_count": len(report["cases"]),
        "missing_automatic_cases": report["missing_automatic_cases"],
        "autocad_reviewed": report["autocad_reviewed"],
    }, ensure_ascii=False))
    return 0 if report["automatic_pass_count"] == len(report["cases"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

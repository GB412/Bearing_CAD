"""PR-2D-09: audited artifacts are not proof of an AutoCAD review."""
from hashlib import sha256
import json

import ezdxf
import pytest

from bearing_cad.drawing_acceptance import create_acceptance_package, inspect_case, main
from bearing_cad.drawing_runner import SHEETS, SHEETS_NUP


def _sha(path):
    return sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path, name="dgb", kind="rolling.deep_groove_ball", config=None):
    folder = tmp_path / name
    folder.mkdir()
    rows = []
    for view in (SHEETS_NUP if config == "NUP" else SHEETS):
        dxf = folder / (view + ".dxf")
        svg = folder / (view + ".svg")
        doc = ezdxf.new("R2010")
        doc.styles.new("HZ", dxfattribs={"font": "hztxt.shx"})
        doc.modelspace().add_text("6008/P5", dxfattribs={"height": 2, "style": "HZ"})
        doc.modelspace().add_line((0, 0), (15, 0))
        doc.saveas(dxf)
        svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',
                       encoding="utf-8")
        rows.append({
            "view": view, "file": dxf.name, "sha256": _sha(dxf),
            "size_bytes": dxf.stat().st_size, "preview_file": svg.name,
            "preview_sha256": _sha(svg),
            "preview_size_bytes": svg.stat().st_size,
            "preview_diagnostics": {"preview_font_warning": None},
            "template_file": "NUP-12.dwg" if view == "loose_rib" else "source.dwg",
            "template_sha256": "a" * 64,
            "text_replacements": 1,
            "variable_diagnostics": {
                "matched_variable_provenance": [
                    {"name": "model", "source_tags": ["explicit_drawing_context"],
                     "requested_value": "6008/P5"}],
                "unfilled_variable_names": [],
            },
            "suspected_unmapped_text_diagnostics": [],
        })
    manifest = {
        "schema_version": "robas.drawing.bundle.v1", "bundle_key": name,
        "bearing_type": kind, "configuration": config, "request_hash": "b" * 64,
        "database_sha256": "c" * 64,
        "manufacturing_approved": False, "sheets": rows,
        "drawing_model_consistency": {"status": "SOURCE_MODEL_DIMENSIONS_MATCH_REQUEST",
                                      "warnings": []},
        "legacy_input_override_evidence": {"source_value_disagreement_keys": []},
        "template_composition_review": (
            "INFERRED_SOURCE_FILES_AUTOCAD_REVIEW_REQUIRED"
            if config in ("NU", "NJ", "NF", "NUP") else "ORIGINAL_FRMMAIN_N_SET"),
        "unfilled_template_variable_names": [],
        "unfilled_database_unused_count": 0,
        "source_conflict_template_variable_names": [],
        "suspected_unmapped_template_texts": [],
        "standard_lookup_warnings": [],
    }
    (folder / "drawing_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return folder


def _edit(folder, mutate):
    path = folder / "drawing_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_real_dxfs_audited_without_fabricated_windows_or_engineering_approval(tmp_path):
    folder = _fixture(tmp_path)
    unchanged = _sha(folder / "assembly.dxf")
    output = tmp_path / "evidence"
    report = create_acceptance_package([f"DGB6008={folder}"], output)
    assert report["automatic_pass_count"] == 1
    assert report["manufacturing_approved"] is False
    assert report["windows_cadimport_verified"] == "NOT_VERIFIED_BY_THIS_TOOL"
    assert report["autocad_reviewed"] == "NOT_VERIFIED_BY_THIS_TOOL"
    assert "rolling.angular_contact_ball" in report["missing_automatic_cases"]
    sheet = report["cases"][0]["sheets"][0]
    assert sheet["font_references"][0]["font_reference"] == "hztxt.shx"
    assert sheet["entity_counts"]["TEXT"] == 1
    assert sheet["entity_counts"]["LINE"] == 1
    assert sheet["source_matched_variable_provenance"][0]["name"] == "model"
    assert sheet["autocad_visual_review"] == "NOT_REVIEWED"
    assert _sha(folder / "assembly.dxf") == unchanged
    assert "未验证" in (output / "autocad_review_checklist.md").read_text("utf-8")
    assert (output / "defects_template.csv").is_file()


def test_nup_five_sheets_and_inferred_template_warning(tmp_path):
    folder = _fixture(tmp_path, name="crb-nup",
                      kind="rolling.cylindrical_roller", config="NUP")
    result = inspect_case("NUP", folder)
    assert result["automatic_status"] == "PASS_DXF_INTEGRITY_AUTOCAD_PENDING"
    assert len(result["sheets"]) == 5
    assert result["sheets"][-1]["original_template_file"] == "NUP-12.dwg"
    assert "INFERRED_CRB_TEMPLATE_COMPOSITION" in result["review_items"]


@pytest.mark.parametrize("kind, config", [
    ("rolling.deep_groove_ball", None),
    ("rolling.angular_contact_ball", None),
    ("rolling.cylindrical_roller", "N"),
    ("rolling.cylindrical_roller", "NU"),
    ("rolling.cylindrical_roller", "NJ"),
    ("rolling.cylindrical_roller", "NF"),
    ("rolling.cylindrical_roller", "NUP"),
])
def test_supported_case_identity_for_original_and_composed_templates(tmp_path, kind, config):
    folder = _fixture(tmp_path, "case", kind, config)
    result = inspect_case("case", folder)
    assert result["case_type"] == kind + (":" + config if config else "")
    assert result["automatic_status"] == "PASS_DXF_INTEGRITY_AUTOCAD_PENDING"


def test_modified_dxf_blocks_autocheck_without_altering_manifest(tmp_path):
    folder = _fixture(tmp_path)
    with (folder / "assembly.dxf").open("ab") as stream:
        stream.write(b"tampered")
    report = create_acceptance_package([f"BAD={folder}"], tmp_path / "report")
    assert report["automatic_pass_count"] == 0
    assert "DXF checksum mismatch" in report["cases"][0]["blocking_errors"][0]
    assert report["cases"][0]["manufacturing_approved"] is False


def test_stale_manifest_or_missing_source_provenance_is_rejected(tmp_path):
    folder = _fixture(tmp_path)
    _edit(folder, lambda m: m.pop("drawing_model_consistency"))
    assert "missing PR-2D-08 model evidence" in (
        inspect_case("old", folder)["blocking_errors"][0])
    folder2 = _fixture(tmp_path, "second")
    _edit(folder2, lambda m:
          m["sheets"][0]["variable_diagnostics"].pop("matched_variable_provenance"))
    assert "matched-variable provenance" in (
        inspect_case("old", folder2)["blocking_errors"][0])


def test_fake_manufacturing_approval_must_fail_closed(tmp_path):
    folder = _fixture(tmp_path)
    _edit(folder, lambda m: m.__setitem__("manufacturing_approved", True))
    result = inspect_case("bad", folder)
    assert result["automatic_status"] == "FAILED"
    assert "manufacturing_approved=false" in result["blocking_errors"][0]


def test_source_warnings_are_not_automatically_treated_as_reviewed(tmp_path):
    folder = _fixture(tmp_path)
    def mutate(m):
        m["unfilled_template_variable_names"] = ["W16"]
        m["source_conflict_template_variable_names"] = ["X"]
        m["suspected_unmapped_template_texts"] = [{"text": "@DdS", "view": "outer_ring"}]
        m["standard_lookup_warnings"] = ["SOURCE_ROW_MISSING"]
        m["drawing_model_consistency"]["warnings"] = ["NO_CATALOG"]
    _edit(folder, mutate)
    case = inspect_case("warnings", folder)
    assert case["automatic_status"] == "PASS_DXF_INTEGRITY_AUTOCAD_PENDING"
    assert set(case["review_items"]) >= {
        "TEMPLATE_USED_MISSING", "CONFLICTING_SOURCE_VARIABLE_ROWS",
        "UNMAPPED_DXF_TEXT_REQUIRES_AUTOCAD_REVIEW",
        "STANDARD_LOOKUP_SOURCE_WARNINGS", "MODEL_OR_CATALOG_UNVERIFIED"}
    assert case["autocad_reviewed"] == "NOT_VERIFIED_BY_THIS_TOOL"


def test_never_overwrite_review_and_reject_bad_labels(tmp_path):
    folder = _fixture(tmp_path)
    output = tmp_path / "report"
    create_acceptance_package([f"first={folder}"], output)
    prior = (output / "acceptance_report.json").read_bytes()
    with pytest.raises(FileExistsError):
        create_acceptance_package([f"second={folder}"], output)
    assert (output / "acceptance_report.json").read_bytes() == prior
    with pytest.raises(ValueError, match="Duplicate"):
        create_acceptance_package([f"X={folder}", f"X={folder}"], tmp_path / "dup")
    with pytest.raises(ValueError, match="Use --case"):
        create_acceptance_package([f"BAD LABEL={folder}"], tmp_path / "bad")
    with pytest.raises(ValueError, match="outside every source bundle"):
        create_acceptance_package([f"X={folder}"], folder / "evidence")


def test_cli_exit_codes_and_pending_manual_status(capsys, tmp_path):
    folder = _fixture(tmp_path)
    assert main(["--case", f"GOOD={folder}",
                 "--out", str(tmp_path / "cli")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["automatic_pass_count"] == 1
    assert out["autocad_reviewed"] == "NOT_VERIFIED_BY_THIS_TOOL"
    assert main(["--case", f"MISSING={tmp_path / 'does-not-exist'}",
                 "--out", str(tmp_path / "failed")]) == 2
    assert '"manufacturing_approved": false' in (
        tmp_path / "failed" / "acceptance_report.json").read_text("utf-8")

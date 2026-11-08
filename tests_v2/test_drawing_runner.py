"""No fake DWG conversion: test only resource selection and safe fail-closed gates."""
import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

from bearing_cad.drawing_runner import (
    DrawingExportError, generate_drawing_bundle, resolve_templates, SHEETS,
    _source_audit_cache_marker, _acb_cage_getter_cache_marker,
    _crb_drawing_getter_cache_marker,
    _robas_standard_getter_cache_marker,
)

TEMPLATES = {
    "rolling.deep_groove_ball": ("深沟球DWG",("0_00KS.DWG","0_01KS.DWG","0_02.DWG","0_07.DWG")),
    "rolling.angular_contact_ball": ("角接触DWG",("6_00_ZDSTW.dwg","6_01SK.DWG","6_02SK.DWG","6_07_ZDST.dwg")),
    "rolling.cylindrical_roller": ("单列圆柱DWG",("N-00.dwg","N-01.dwg","N-02.dwg","N-06.dwg")),
}
DB = {"rolling.deep_groove_ball":"DGBData.db",
      "rolling.angular_contact_ball":"ACBData.db",
      "rolling.cylindrical_roller":"CRBData.db"}
P = {"bore_d_mm":40, "outside_d_mm":68, "width_mm":15, "ball_d_mm":8,
     "ball_count":10,"roller_d_mm":8,"roller_length_mm":12,
     "roller_count":12,"contact_angle_deg":25}

@pytest.fixture
def resources(tmp_path):
    for kind, (folder,files) in TEMPLATES.items():
        base=tmp_path/"Resource"/"哑图"/folder
        base.mkdir(parents=True,exist_ok=True)
        for file in files:
            (base/file).write_bytes(b"AC1021" + b"synthetic-fixture-only")
        db=tmp_path/"Data"/DB[kind]
        db.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(db) as con:
            con.execute('CREATE TABLE "变量表" ("变量名" TEXT,"变量值" TEXT)')
            values=["Dd","d","B_","Dw","Z","Cr","Cor"] + (
                ["alfa1"] if kind=="rolling.angular_contact_ball" else
                ["Lw"] if kind=="rolling.cylindrical_roller" else [])
            con.executemany('INSERT INTO "变量表" VALUES (?,?)',
                            [(key,None) for key in values])
    return tmp_path

@pytest.mark.parametrize("kind",list(TEMPLATES))
def test_template_selection_uses_real_names(resources,kind):
    paths=resolve_templates(resources,kind,"N" if kind=="rolling.cylindrical_roller" else None)
    assert len(paths)==len(SHEETS)==4
    assert [p.name for p in paths]==list(TEMPLATES[kind][1])

def test_no_nu_drawings_by_substituting_n_templates(resources):
    with pytest.raises(DrawingExportError,match="Missing or unsupported"):
        resolve_templates(resources,"rolling.cylindrical_roller","NU")

@pytest.mark.parametrize("variant,names", [
    ("NU", ("NU-00.dwg", "NU-01.dwg", "NU-02.dwg", "N-06.dwg")),
    ("NJ", ("NJ-00.dwg", "NU-01.dwg", "NJ-02.dwg", "N-06.dwg")),
    ("NF", ("NF-00.dwg", "NF-01.dwg", "N-02.dwg", "N-06.dwg")),
    ("NUP", ("NUP-00.dwg", "NU-01.dwg", "NUP-02.dwg",
             "N-06.dwg", "NUP-12.dwg")),
])
def test_source_backed_roller_template_compositions(resources, variant, names):
    base = resources / "Resource" / "哑图" / "单列圆柱DWG"
    for file in names:
        if not (base / file).exists():
            (base / file).write_bytes(b"AC1021" + b"synthetic-fixture-only")
    selected = resolve_templates(resources, "rolling.cylindrical_roller", variant)
    assert tuple(path.name for path in selected) == names
    assert len(selected) == (5 if variant == "NUP" else 4)


def test_reject_invalid_header(resources):
    p=resources/"Resource"/"哑图"/"深沟球DWG"/"0_00KS.DWG"
    p.write_bytes(b"NOTDWG")
    with pytest.raises(DrawingExportError,match="unsupported original"):
        resolve_templates(resources,"rolling.deep_groove_ball")

def test_original_blank_variables_are_not_a_new_export_gate(resources,tmp_path):
    target=tmp_path/"out"
    # Unlike the first port, an incomplete *database* is not an export
    # blocker: original RoBAS replaces DBNull with empty text.
    # On this Linux test runner, only the missing Windows runtime is blocking.
    with pytest.raises(DrawingExportError) as error:
        generate_drawing_bundle(
            resources=resources,bridge=tmp_path/"fake.exe",output_root=target,
            bearing_type="rolling.deep_groove_ball",parameters=P,
            request_hash="a"*64)
    # Linux stops at the platform gate; Windows proceeds to the missing bridge check.
    assert ("licensed Windows/.NET runtime" in str(error.value)
            or "CADImportBridge.exe" in str(error.value))
    assert not target.exists() or not list(target.iterdir())


def test_dgb_source_audit_changes_bundle_cache_identity_but_not_other_types():
    # Cache identity is derived from JSON variables plus this source audit.
    # A change in matched CAD geometry is not allowed to reuse a manifest
    # containing an earlier diagnosis of source-vs-3D disagreement.
    mismatch = {
        "original_source_shoulder_mm": {"d2": 49.2, "Dd2": 58.81},
        "original_source_shoulder_matches_cad": {"d2": False, "Dd2": False},
    }
    matched = {
        **mismatch,
        "original_source_shoulder_matches_cad": {"d2": True, "Dd2": True},
    }
    kind = "rolling.deep_groove_ball"
    assert _source_audit_cache_marker(kind, mismatch) != (
        _source_audit_cache_marker(kind, matched))
    assert _source_audit_cache_marker(kind, mismatch)["dgb_shoulder_source_audit"] == {
        "source_mm": {"d2": 49.2, "Dd2": 58.81},
        "matches_cad": {"d2": False, "Dd2": False},
    }
    assert _source_audit_cache_marker(
        "rolling.angular_contact_ball", mismatch) == {}
    assert _source_audit_cache_marker(
        "rolling.cylindrical_roller", matched) == {}


def test_acb_cage_rounding_bumps_cache_identity_only_for_angular_contact():
    assert _acb_cage_getter_cache_marker("rolling.angular_contact_ball") == {
        "acb_cage_getter_precision": "robas.public-getters.v1",
    }
    assert _acb_cage_getter_cache_marker("rolling.deep_groove_ball") == {}
    assert _acb_cage_getter_cache_marker("rolling.cylindrical_roller") == {}


def test_crb_original_getter_source_parity_cache_version_is_bearing_scoped():
    assert _crb_drawing_getter_cache_marker("rolling.cylindrical_roller")=={
        "crb_drawing_getter_parity":"robas.crb-public-getters.v1",
    }
    assert _crb_drawing_getter_cache_marker("rolling.angular_contact_ball")=={}
    assert _crb_drawing_getter_cache_marker("rolling.deep_groove_ball")=={}



def test_all_three_source_standard_getter_contracts_bump_drawing_cache_keys():
    for kind in (
        "rolling.deep_groove_ball",
        "rolling.angular_contact_ball",
        "rolling.cylindrical_roller",
    ):
        assert _robas_standard_getter_cache_marker(kind)=={
            "robas_standard_lookup_getter":"bearing-diameter.v2",
        }
    assert _robas_standard_getter_cache_marker("unknown") == {}


def test_nup_fifth_sheet_is_required_in_cached_artifact(tmp_path):
    import json
    from bearing_cad.drawing_runner import (
        SHEETS_NUP, DrawingExportError, verify_drawing_bundle, _digest)
    folder = tmp_path / "nup-evidence"
    folder.mkdir()
    sheets = []
    for view in SHEETS_NUP:
        path = folder / (view + ".dxf")
        path.write_bytes(b"DXF test payload: " + view.encode("ascii"))
        sheets.append({
            "view": view, "file": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _digest(path),
            "template_file": ("NUP-12.dwg" if view == "loose_rib"
                              else "source.dwg"),
        })
    manifest = {
        "schema_version": "robas.drawing.bundle.v1",
        "bundle_key": "fake-nup", "bearing_type": "rolling.cylindrical_roller",
        "configuration": "NUP", "sheets": sheets,
    }
    (folder / "drawing_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    assert verify_drawing_bundle(folder, "fake-nup")["sheets"][-1]["view"] == "loose_rib"
    manifest["sheets"] = manifest["sheets"][:-1]
    (folder / "drawing_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DrawingExportError, match="Unexpected drawing-sheet order"):
        verify_drawing_bundle(folder, "fake-nup")

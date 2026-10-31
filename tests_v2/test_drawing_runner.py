"""No fake DWG conversion: test only resource selection and safe fail-closed gates."""
import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

from bearing_cad.drawing_runner import (
    DrawingExportError, generate_drawing_bundle, resolve_templates, SHEETS,
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
    with pytest.raises(DrawingExportError,match="No confirmed"):
        resolve_templates(resources,"rolling.cylindrical_roller","NU")

def test_reject_invalid_header(resources):
    p=resources/"Resource"/"哑图"/"深沟球DWG"/"0_00KS.DWG"
    p.write_bytes(b"NOTDWG")
    with pytest.raises(DrawingExportError,match="unsupported original"):
        resolve_templates(resources,"rolling.deep_groove_ball")

def test_missing_standard_calculations_prevent_any_output(resources,tmp_path):
    target=tmp_path/"out"
    with pytest.raises(DrawingExportError,match="drawing data incomplete"):
        generate_drawing_bundle(
            resources=resources,bridge=tmp_path/"fake.exe",output_root=target,
            bearing_type="rolling.deep_groove_ball",parameters=P,
            request_hash="a"*64)
    assert not target.exists() or not list(target.iterdir())

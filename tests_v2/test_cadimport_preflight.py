"""Unit contracts for local CADImport preflight, with synthetic fixture files."""
from pathlib import Path
import sqlite3
import pytest
from bridge.cadimport.preflight import preflight

CASES = {
    "rolling.deep_groove_ball": ("深沟球DWG",["0_00KS.DWG","0_01KS.DWG","0_02.DWG","0_07.DWG"],"DGBData.db"),
    "rolling.angular_contact_ball": ("角接触DWG",["6_00_ZDSTW.dwg","6_01SK.DWG","6_02SK.DWG","6_07_ZDST.dwg"],"ACBData.db"),
    "rolling.cylindrical_roller:N": ("单列圆柱DWG",["N-00.dwg","N-01.dwg","N-02.dwg","N-06.dwg"],"CRBData.db"),
}

def _fixtures(tmp_path):
    for folder,names,db in CASES.values():
        path=tmp_path/"Resource"/"哑图"/folder
        path.mkdir(parents=True,exist_ok=True)
        for name in names:
            (path/name).write_bytes(b"AC1027"+"fixture".encode())
        data=tmp_path/"Data"
        data.mkdir(exist_ok=True)
        conn=sqlite3.connect(data/db)
        conn.execute('CREATE TABLE "变量表" ("变量名" TEXT, "变量值" TEXT)')
        conn.executemany('INSERT INTO "变量表" VALUES (?,?)', [("d","40"),("d","41"),("D","68")])
        conn.commit()
        conn.close()
    return tmp_path

def test_full_resources(tmp_path):
    r=preflight(_fixtures(tmp_path))
    assert r["status"]=="RESOURCES_CHECKED_NOT_DWG_CONVERTED"
    assert sum(map(len,r["templates"].values()))==12
    assert set(r["databases"])=={"DGBData.db","ACBData.db","CRBData.db"}
    assert r["databases"]["DGBData.db"]["duplicated_names"]=={"d":2}

def test_missing_template_fails(tmp_path):
    root=_fixtures(tmp_path)
    (root/"Resource"/"哑图"/"深沟球DWG"/"0_02.DWG").unlink()
    with pytest.raises(FileNotFoundError):
        preflight(root)

def test_bad_signature_fails(tmp_path):
    root=_fixtures(tmp_path)
    (root/"Resource"/"哑图"/"深沟球DWG"/"0_02.DWG").write_bytes(b"INVALID")
    with pytest.raises(ValueError,match="signature"):
        preflight(root)

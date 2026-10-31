"""Drawing manifest cache and CLI cannot invent DXFs or modify originals."""
import hashlib
import json
from pathlib import Path
import pytest
from bearing_cad.drawing_runner import verify_drawing_bundle, DrawingExportError
from bearing_cad.drawing_cli import _read_request

SHEETS=("assembly","outer_ring","inner_ring","cage")

def _bundle(folder):
    folder.mkdir()
    records=[]
    for label in SHEETS:
        payload=("fake-"+label).encode()
        p=folder/(label+".dxf")
        p.write_bytes(payload)
        records.append({"view":label,"file":p.name,"sha256":hashlib.sha256(payload).hexdigest(),
                        "size_bytes":len(payload)})
    (folder/"drawing_manifest.json").write_text(json.dumps({
        "schema_version":"robas.drawing.bundle.v1","bundle_key":folder.name,
        "sheets":records}),encoding="utf-8")

def test_valid_existing_manifest_can_be_reused(tmp_path):
    path=tmp_path/("a"*64)
    _bundle(path)
    r=verify_drawing_bundle(path,path.name)
    assert len(r["sheets"])==4

def test_incomplete_manifest_and_mutated_file_rejected(tmp_path):
    folder=tmp_path/("a"*64)
    _bundle(folder)
    (folder/"inner_ring.dxf").write_bytes(b"tampered")
    with pytest.raises(DrawingExportError,match="modified DXF"):
        verify_drawing_bundle(folder,folder.name)
    with pytest.raises(DrawingExportError,match="identity"):
        verify_drawing_bundle(folder,"b"*64)

def test_cli_requires_real_v1_design_request(tmp_path):
    path=tmp_path/"request.json"
    path.write_text(json.dumps({"request":{},"drawing":{}}),encoding="utf-8")
    with pytest.raises(ValueError):
        _read_request(path)
    path.write_text(json.dumps({"request":{},"drawing":{"unrecognized":7}}))
    with pytest.raises(ValueError,match="Unsupported"):
        _read_request(path)

"""Optional RoBAS 2D HTTP endpoint does not disturb original 3D API."""
from pathlib import Path
import hashlib
import json
from threading import Lock
from bearing_cad.drawing_http import (
    enabled,environment_check,drawing_status,create_drawing,serve_drawing,
)

class Dummy:
    def __init__(self):
        self.response=None
        self.errors=[]
        self.headers={}
        self.sent=[]
        self.job=None
        self.command="HEAD"
    def _respond(self,status,payload,**kwargs):
        self.response=(status,payload)
    def _error(self,status,code,message,*args,**kwargs):
        self.errors.append((status,code,message))
        return self._respond(status,{"error":{"error_code":code,"message":message}})
    def _known_job(self,job_id):
        return self.job
    def send_response(self,status):
        self.response=(status,{})
    def send_header(self,name,value):
        self.headers[name]=value
    def end_headers(self):
        pass

def test_missing_windows_bridge_is_unavailable(tmp_path):
    handler=Dummy()
    assert not enabled(None,None)
    assert not enabled(tmp_path,tmp_path/"fake.exe")
    drawing_status(handler,None,None)
    assert handler.response[0]==200
    assert handler.response[1]["available"] is False
    assert handler.response[1]["failures"]
    assert "rolling.cylindrical_roller:N" in handler.response[1]["supported_bearings"]


def test_environment_check_reports_specific_missing_inputs(tmp_path):
    report = environment_check(tmp_path, tmp_path / "missing.exe")
    assert report["available"] is False
    assert any("resources" in item.lower() or "database" in item.lower() for item in report["failures"])
    assert any("bridge" in item.lower() for item in report["failures"])

def test_drawing_export_fails_closed_without_bridge(tmp_path):
    handler=Dummy()
    create_drawing(handler,{"design":{},"drawing":{}},tmp_path,None,None,Lock())
    assert handler.response[0]==503
    assert handler.errors[0][1]=="DRAWING_BRIDGE_UNAVAILABLE"
    assert not (tmp_path/"drawings").exists()

def test_unknown_drawing_job_does_not_leak_files(tmp_path):
    handler=Dummy()
    assert serve_drawing(handler,
      "/api/v2/cad/drawings/"+("a"*32)+"/files/cage.dxf",tmp_path)
    assert handler.response[0]==404
    assert not serve_drawing(handler,"/api/v2/cad/jobs",tmp_path)

def test_svg_preview_route_serves_generated_preview(tmp_path):
    job_id="b"*32
    bundle_key="c"*64
    folder=tmp_path/"drawings"/bundle_key
    folder.mkdir(parents=True)
    sheets=[]
    for name in ("assembly","outer_ring","inner_ring","cage"):
        dxf=folder/(name+".dxf")
        svg=folder/(name+".svg")
        dxf.write_bytes(b"dxf:"+name.encode())
        svg.write_text("<svg/>"+name,encoding="utf-8")
        sheets.append({
            "view":name,"file":dxf.name,"size_bytes":dxf.stat().st_size,
            "sha256":hashlib.sha256(dxf.read_bytes()).hexdigest(),
            "preview_file":svg.name,"preview_size_bytes":svg.stat().st_size,
            "preview_sha256":hashlib.sha256(svg.read_bytes()).hexdigest(),
        })
    manifest={"schema_version":"robas.drawing.bundle.v1","bundle_key":bundle_key,
              "request_hash":"d"*64,"sheets":sheets}
    (folder/"drawing_manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    handler=Dummy()
    handler.job={"status":"succeeded","kind":"robas_drawing",
                 "bundle_key":bundle_key,"request_hash":"d"*64}

    assert serve_drawing(handler,
      f"/api/v2/cad/drawings/{job_id}/files/assembly.svg",tmp_path)
    assert handler.response[0]==200
    assert handler.headers["Content-Type"].startswith("image/svg+xml")

def test_manifest_exposes_dxf_and_svg_preview_urls(tmp_path):
    job_id="e"*32
    bundle_key="f"*64
    folder=tmp_path/"drawings"/bundle_key
    folder.mkdir(parents=True)
    sheets=[]
    for name in ("assembly","outer_ring","inner_ring","cage"):
        dxf=folder/(name+".dxf")
        svg=folder/(name+".svg")
        dxf.write_bytes(b"dxf:"+name.encode())
        svg.write_text("<svg/>"+name,encoding="utf-8")
        sheets.append({
            "view":name,"file":dxf.name,"size_bytes":dxf.stat().st_size,
            "sha256":hashlib.sha256(dxf.read_bytes()).hexdigest(),
            "preview_file":svg.name,"preview_size_bytes":svg.stat().st_size,
            "preview_sha256":hashlib.sha256(svg.read_bytes()).hexdigest(),
        })
    manifest={"schema_version":"robas.drawing.bundle.v1","bundle_key":bundle_key,
              "request_hash":"a"*64,"sheets":sheets}
    (folder/"drawing_manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
    handler=Dummy()
    handler.job={"status":"succeeded","kind":"robas_drawing",
                 "bundle_key":bundle_key,"request_hash":"a"*64}

    assert serve_drawing(handler,f"/api/v2/cad/drawings/{job_id}",tmp_path)
    urls=handler.response[1]["file_urls"]
    assert urls["assembly.dxf"].endswith("/files/assembly.dxf")
    assert urls["assembly.svg"].endswith("/files/assembly.svg")

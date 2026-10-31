"""Optional RoBAS 2D HTTP endpoint does not disturb original 3D API."""
from pathlib import Path
from threading import Lock
from bearing_cad.drawing_http import (
    enabled,drawing_status,create_drawing,serve_drawing,
)

class Dummy:
    def __init__(self):
        self.response=None
        self.errors=[]
    def _respond(self,status,payload,**kwargs):
        self.response=(status,payload)
    def _error(self,status,code,message,*args,**kwargs):
        self.errors.append((status,code,message))
        return self._respond(status,{"error":{"error_code":code,"message":message}})
    def _known_job(self,job_id):
        return None

def test_missing_windows_bridge_is_unavailable(tmp_path):
    handler=Dummy()
    assert not enabled(None,None)
    assert not enabled(tmp_path,tmp_path/"fake.exe")
    drawing_status(handler,None,None)
    assert handler.response[0]==200
    assert handler.response[1]["available"] is False
    assert "rolling.cylindrical_roller:N" in handler.response[1]["supported_bearings"]

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

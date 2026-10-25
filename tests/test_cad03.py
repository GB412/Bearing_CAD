"""Day 3 local CAD bridge tests: status, same-origin guard, real output and safety."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from cad03_server import make_server

class LocalBridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory()
  cls.root=Path(cls.temp.name)
  static=cls.root/"dist";static.mkdir()
  (static/"index.html").write_text("<h1>CAD 03 test</h1>",encoding="utf-8")
  cls.server=make_server("127.0.0.1",0,static,cls.root/"artifacts")
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
  cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5);cls.temp.cleanup()
 def request(self,method,path,payload=None,headers=None):
  conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=35)
  conn.request(method,path,body=payload,headers=headers or {})
  response=conn.getresponse();data=response.read();status=response.status
  conn.close();return status,data
 def post(self,payload,origin=True):
  headers={"Content-Type":"application/json"}
  if origin:headers["Origin"]=f"http://127.0.0.1:{self.server.server_port}"
  return self.request("POST","/api/cad02/generate",json.dumps(payload).encode(),headers)
 def params(self):
  return dict(shaft_d_mm=50,radial_clearance_mm=.05,bush_od_mm=70,length_mm=50,housing_od_mm=86,housing_length_mm=60,
   oil_feed_hole_d_mm=5,annular_groove_width_mm=6,annular_groove_depth_mm=1.2)
 def test_status_and_static(self):
  status,data=self.request("GET","/api/cad02/status")
  self.assertEqual(status,200);self.assertTrue(json.loads(data)["available"])
  self.assertEqual(self.request("GET","/")[0],200)
  self.assertEqual(self.request("GET","/../missing")[0],404)
 def test_reject_foreign_origin_and_fake_confirmation(self):
  self.assertEqual(self.post(self.params(),origin=False)[0],403)
  self.assertEqual(self.post({**self.params(),"approval_state":"CONFIRMED"})[0],422)
  self.assertEqual(self.post({**self.params(),"annular_groove_depth_mm":200})[0],422)
 def test_generate_and_served_artifacts_and_tampering(self):
  status,data=self.post(self.params())
  self.assertEqual(status,200,data)
  bundle=json.loads(data)
  self.assertEqual(bundle["approval_state"],"DRAFT")
  self.assertEqual(len(bundle["geometry_hash"]),64)
  step=bundle["files"]["bearing_assembly.step"]
  svg=bundle["files"]["occt_side.svg"]
  self.assertTrue(self.request("GET",step)[1][:100])
  self.assertIn(b"<svg",self.request("GET",svg)[1])
  self.assertEqual(self.post(self.params())[0],200)
  self.assertEqual(self.request("GET",step.replace("bearing_assembly.step","../../etc/passwd"))[0],404)
  with (self.root/"artifacts"/bundle["cache_key"]/"shaft.step").open("ab") as file:file.write(b"tamper")
  self.assertEqual(self.request("GET",step)[0],404)

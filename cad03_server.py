"""Loopback-only Day-3 exact CAD API and Vite production file server."""
import argparse
import json
import mimetypes
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,unquote
from cad02_pipeline import parse_design,generate,verify_bundle

FILES={"bearing_assembly.step","housing.step","bushing.step","shaft.step","housing.stl","bushing.stl","shaft.stl","occt_projection.dxf","occt_side.svg","occt_end.svg","artifact_manifest.json","design_snapshot.json","housing_section.stl","bushing_section.stl","shaft_section.stl","housing_section.step","bushing_section.step","shaft_section.step","bearing_review_sheet.svg","bearing_review_sheet.dxf"}
RE=re.compile(r"^/api/cad02/files/([a-f0-9]{24})/([a-z0-9_.-]+)$")
MIMES={".step":"model/step",".stl":"model/stl",".svg":"image/svg+xml",".dxf":"application/dxf",".json":"application/json"}

def make_server(host="127.0.0.1",port=8088,static=Path("dist"),artifacts=Path("artifacts/cad02")):
    if host!="127.0.0.1":raise ValueError("Loopback only")
    static=Path(static).resolve(strict=True)
    if not (static/"index.html").is_file():raise ValueError("Please run npm run build first")
    artifacts=Path(artifacts).resolve()
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,data,mime="application/json",download=False):
            self.send_response(status);self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
            if download:self.send_header("Content-Disposition","attachment")
            self.end_headers()
            if self.command!="HEAD":self.wfile.write(data)
        def reply(self,status,value):
            self.send(status,json.dumps(value,ensure_ascii=False).encode("utf-8"))
        def do_POST(self):
            if urlsplit(self.path).path!="/api/cad02/generate":return self.reply(404,{"error":"Not found"})
            if self.headers.get("Origin") not in (f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"):
                return self.reply(403,{"error":"Same-origin requests only"})
            if self.headers.get("Content-Type","").split(";")[0].lower()!="application/json":
                return self.reply(415,{"error":"Expected application/json"})
            try:
                length=int(self.headers.get("Content-Length","-1"))
                if length<1 or length>8192:return self.reply(413,{"error":"Invalid request size"})
                design=parse_design(json.loads(self.rfile.read(length)))
            except (ValueError,TypeError) as err:
                return self.reply(422,{"error":str(err)})
            try:
                directory=generate(design,artifacts)
                manifest=verify_bundle(directory,design.geometry_hash)
                root=f"/api/cad02/files/{manifest['cache_key']}/"
                return self.reply(200,{"geometry_hash":design.geometry_hash,"approval_state":"DRAFT","unit":"mm","cache_key":manifest["cache_key"],
                    "generator_version":manifest["generator_version"],
                    "files":{name:root+name for name in manifest["files"] if name in FILES}})
            except Exception:
                self.log_error("Exact CAD generation failed")
                return self.reply(500,{"error":"CAD generation failed; inspect local service logs"})
        def do_HEAD(self):self.do_GET()
        def do_GET(self):
            route=unquote(urlsplit(self.path).path)
            if route=="/api/cad02/status":return self.reply(200,{"available":True,"approval_state":"DRAFT"})
            match=RE.fullmatch(route)
            if match:
                token,name=match.groups()
                if name not in FILES:return self.reply(404,{"error":"Unknown file"})
                try:
                    folder=artifacts/token
                    metadata=json.loads((folder/"artifact_manifest.json").read_text(encoding="utf-8"))
                    if metadata["cache_key"]!=token:raise ValueError("Hash mismatch")
                    verify_bundle(folder,metadata["geometry_hash_sha256"])
                    if name not in metadata["files"] and name!="artifact_manifest.json":raise ValueError("Unregistered")
                    p=(folder/name).resolve(strict=True)
                    if not p.is_relative_to(folder.resolve()):raise ValueError("Bad path")
                    return self.send(200,p.read_bytes(),MIMES.get(p.suffix,"application/octet-stream"),name.endswith((".step",".stl",".dxf")))
                except (ValueError,OSError,KeyError,RuntimeError,json.JSONDecodeError):
                    return self.reply(404,{"error":"Artifact invalid or missing"})
            if route.startswith("/api/"):return self.reply(404,{"error":"Unknown endpoint"})
            try:
                p=(static/(route.lstrip("/") or "index.html")).resolve(strict=True)
                if not p.is_relative_to(static) or not p.is_file():raise ValueError()
                return self.send(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or "application/octet-stream")
            except (OSError,ValueError):
                return self.reply(404,{"error":"Not found"})
    return ThreadingHTTPServer((host,port),Handler)

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--port",type=int,default=8088);cli.add_argument("--static",type=Path,default=Path("dist"))
    cli.add_argument("--artifacts",type=Path,default=Path("artifacts/cad02"))
    a=cli.parse_args();server=make_server(port=a.port,static=a.static,artifacts=a.artifacts)
    print(f"Day3 CAD demo: http://127.0.0.1:{a.port}",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()

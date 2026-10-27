"""Loopback-only synchronous CAD-V2 HTTP facade.

This module neither authorizes multi-user access nor grants design approval.
Jobs are ephemeral per-process capability IDs, not persistent backend tasks.
"""
from __future__ import annotations

from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import mimetypes
from threading import Lock, RLock
import json
import logging
import re
import secrets
from urllib.parse import urlsplit

from .artifacts import generate_bundle, verify_bundle
from .contracts import ContractError, parse_request, MAX_ROLLING_ELEMENTS, MAX_CAD_DIMENSION_MM

_MAX_BODY = 16 * 1024
_MAX_JOBS = 128
_TOKEN = r"([a-f0-9]{32})"
_JOB_ROUTE = re.compile(r"^/api/v2/cad/jobs/" + _TOKEN + r"$")
_ARTIFACT_ROUTE = re.compile(r"^/api/v2/cad/artifacts/" + _TOKEN + r"$")
_FILE_ROUTE = re.compile(r"^/api/v2/cad/artifacts/" + _TOKEN + r"/files/([a-zA-Z0-9_.-]+)$")
_CONTENT_TYPES = {".step": "model/step", ".stl": "model/stl", ".json": "application/json"}


def make_server(*, port: int = 0, artifacts_root: Path = Path("artifacts/cad-v2"),
                host: str = "127.0.0.1", static_root: Path | None = None) -> ThreadingHTTPServer:
    """Bind to IPv4 loopback only. No network deployment or implicit auth."""
    if host != "127.0.0.1":
        raise ValueError("CAD-V2 API only supports IPv4 loopback")
    root = Path(artifacts_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    static = Path(static_root).resolve(strict=True) if static_root is not None else None
    if static is not None and not (static / "rolling.html").is_file():
        raise ValueError("Build rolling.html with npm run build before serving")
    jobs: OrderedDict[str, dict] = OrderedDict()
    job_lock = RLock()
    build_lock = Lock()  # Single active expensive OCCT generation per process.

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _respond(self, status: int, payload: dict, *, headers: dict[str, str] | None = None):
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if headers:
                for key, value in headers.items():
                    self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _error(self, status: int, code: str, message: str, field: str = "",
                   job_id: str | None = None):
            result = {"error": {"error_code": code,
                                "field_path": field, "message": message}}
            if job_id is not None:
                result["job_id"] = job_id
            self._respond(status, result)

        def _host_allowed(self) -> bool:
            hostname = self.headers.get("Host", "")
            return hostname in {f"127.0.0.1:{self.server.server_port}",
                                f"localhost:{self.server.server_port}"}

        def _origin_allowed(self) -> bool:
            return self.headers.get("Origin") in {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}"}

        def _route(self) -> str | None:
            try:
                parsed = urlsplit(self.path)
            except ValueError:
                return None
            if parsed.query or parsed.fragment or not parsed.path.startswith("/api/v2/cad/"):
                return None
            return parsed.path

        def _known_job(self, job_id: str) -> dict | None:
            with job_lock:
                job = jobs.get(job_id)
                return job.copy() if job else None

        def _set_job(self, job_id: str, record: dict) -> None:
            with job_lock:
                jobs[job_id] = record.copy()
                while len(jobs) > _MAX_JOBS:
                    jobs.popitem(last=False)

        def do_POST(self):
            # Requests rejected before reading the body must not poison keepalive.
            self.close_connection = True
            if not self._host_allowed():
                return self._error(403, "HOST_FORBIDDEN", "Invalid loopback host")
            if self._route() != "/api/v2/cad/jobs":
                return self._error(404, "NOT_FOUND", "Unknown route")
            if not self._origin_allowed():
                return self._error(403, "ORIGIN_FORBIDDEN", "A same-origin browser request is required")
            if self.headers.get("Transfer-Encoding"):
                return self._error(400, "INVALID_BODY", "Chunked requests are not supported")
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                return self._error(415, "UNSUPPORTED_MEDIA_TYPE", "Expected application/json")
            try:
                size = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                size = -1
            if not 1 <= size <= _MAX_BODY:
                self.close_connection = True
                return self._error(413, "INVALID_BODY", "Invalid or oversized request body")
            body = self.rfile.read(size)
            try:
                def _invalid_constant(value):
                    raise ValueError("Non-finite JSON number")
                def _no_duplicate_keys(pairs):
                    obj = {}
                    for key, value in pairs:
                        if key in obj:
                            raise ValueError("Duplicate JSON key")
                        obj[key] = value
                    return obj
                data = json.loads(body.decode("utf-8"), parse_constant=_invalid_constant,
                                  object_pairs_hook=_no_duplicate_keys)
            except (ValueError, UnicodeError, json.JSONDecodeError):
                return self._error(400, "INVALID_JSON", "Malformed JSON document")
            try:
                request = parse_request(data)
            except ContractError as error:
                return self._error(422, error.error_code, str(error), error.field_path)
            if request.bearing_type.value not in {"rolling.deep_groove_ball", "rolling.cylindrical_roller", "rolling.angular_contact_ball"}:
                return self._error(422, "NOT_SUPPORTED", "CAD builder is not implemented", "/bearing_type")
            if request.detail_level != "functional":
                return self._error(422, "NOT_SUPPORTED", "Only functional CAD detail is implemented", "/detail_level")
            # The API cap is a resource limit, not a mechanical standard.
            dimensions = [float(value) for key, value in request.parameters.items()
                          if key not in {"ball_count", "roller_count", "configuration"}]
            if request.cage is not None:
                from dataclasses import asdict
                dimensions.extend(float(value) for value in asdict(request.cage).values()
                                  if type(value) in (float, int))
            count = request.parameters.get("ball_count", request.parameters.get("roller_count", 0))
            if count > MAX_ROLLING_ELEMENTS or max(dimensions) > MAX_CAD_DIMENSION_MM:
                return self._error(422, "RESOURCE_LIMIT", "CAD service resource budget exceeded", "/parameters")
            if not build_lock.acquire(blocking=False):
                return self._error(503, "BUSY", "One CAD build is already running")
            job_id = secrets.token_hex(16)
            self._set_job(job_id, {"status": "running"})
            try:
                output = generate_bundle(request, root)
                manifest = verify_bundle(output)
                if manifest["request_hash"] != request.request_hash:
                    raise ValueError("Artifact request hash mismatch")
                self._set_job(job_id, {"status": "succeeded", "artifact_key": manifest["artifact_key"],
                                       "request_hash": request.request_hash})
                self._respond(201, {"job_id": job_id, "status": "succeeded",
                                    "request_hash": request.request_hash,
                                    "manifest_url": f"/api/v2/cad/artifacts/{job_id}",
                                    "job_url": f"/api/v2/cad/jobs/{job_id}"})
            except ContractError as error:
                self._set_job(job_id, {"status": "failed", "error_code": error.error_code})
                self._error(422, error.error_code, str(error), error.field_path, job_id)
            except Exception:
                logging.exception("CAD-V2 generation failed for job %s", job_id)
                self._set_job(job_id, {"status": "failed", "error_code": "CAD_GENERATION_FAILED"})
                self._error(500, "CAD_GENERATION_FAILED", "CAD generation failed; inspect server logs", job_id=job_id)
            finally:
                build_lock.release()

        def _serve_static(self):
            """Serve only the V2 workbench and Vite hashed assets, not the old demo."""
            if static is None:
                return self._error(404, "NOT_FOUND", "Workbench not configured")
            parsed = urlsplit(self.path)
            route = parsed.path
            if parsed.query or parsed.fragment:
                return self._error(404, "NOT_FOUND", "Unknown route")
            if route in ("/", "/rolling.html"):
                rel = "rolling.html"
            elif re.fullmatch(r"/assets/[A-Za-z0-9_.-]+\.(?:js|css)", route):
                rel = route.lstrip("/")
            else:
                return self._error(404, "NOT_FOUND", "Unknown workbench file")
            try:
                file_path = (static / rel).resolve(strict=True)
                if not file_path.is_relative_to(static) or not file_path.is_file():
                    raise ValueError("Unsafe static path")
                data = file_path.read_bytes()
            except (OSError, ValueError):
                return self._error(404, "NOT_FOUND", "Workbench file unavailable")
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._host_allowed():
                return self._error(403, "HOST_FORBIDDEN", "Invalid loopback host")
            if not urlsplit(self.path).path.startswith("/api/"):
                return self._serve_static()
            route = self._route()
            if route == "/api/v2/cad/status":
                return self._respond(200, {"available": True, "mode": "loopback_synchronous",
                                           "supported_bearings": ["rolling.deep_groove_ball",
                                                                  "rolling.cylindrical_roller",
                                                                  "rolling.angular_contact_ball"]})
            match = _JOB_ROUTE.fullmatch(route or "")
            if match:
                job_id = match.group(1)
                job = self._known_job(job_id)
                if not job:
                    return self._error(404, "NOT_FOUND", "Unknown or expired job")
                return self._respond(200, {"job_id": job_id, **job})
            match = _ARTIFACT_ROUTE.fullmatch(route or "")
            file_match = _FILE_ROUTE.fullmatch(route or "")
            if not match and not file_match:
                return self._error(404, "NOT_FOUND", "Unknown route")
            job_id = (match or file_match).group(1)
            job = self._known_job(job_id)
            if not job or job["status"] != "succeeded":
                return self._error(404, "NOT_FOUND", "Artifact not found")
            key = job["artifact_key"]
            try:
                folder = (root / key).resolve(strict=True)
                if folder.parent != root:
                    raise ValueError("Invalid artifact directory")
                manifest = verify_bundle(folder, key)
                if manifest["request_hash"] != job["request_hash"]:
                    raise ValueError("Request hash mismatch")
                if match:
                    return self._respond(200, {"job_id": job_id, "manifest": manifest,
                                               "file_urls": {name: f"/api/v2/cad/artifacts/{job_id}/files/{name}"
                                                             for name in manifest["files"]}})
                name = file_match.group(2)
                if name not in manifest["files"]:
                    return self._error(404, "NOT_FOUND", "Unregistered artifact file")
                path = (folder / name).resolve(strict=True)
                if path.parent != folder or not path.is_file():
                    raise ValueError("Unsafe artifact file")
                size = path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", _CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                if self.command != "HEAD":
                    with path.open("rb") as stream:
                        while chunk := stream.read(256 * 1024):
                            self.wfile.write(chunk)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                return self._error(404, "ARTIFACT_INVALID", "Artifact missing or integrity check failed")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Loopback-only CAD-V2 service")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/cad-v2"))
    parser.add_argument("--static", type=Path, default=None, help="Vite dist directory for the V2 workbench")
    args = parser.parse_args()
    server = make_server(port=args.port, artifacts_root=args.artifacts, static_root=args.static)
    print(f"CAD-V2 API http://127.0.0.1:{server.server_port}/api/v2/cad/status", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

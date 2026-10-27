"""Content-addressed STEP/mesh bundle. The authoritative CAD geometry is B-Rep.

Staging plus atomic directory rename publishes only verified complete outputs.
Multi-process locks/single-flight and access control belong to the service PR.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile

import cadquery as cq

from .contracts import BearingRequest, BearingType, ContractError
from .cylindrical_roller import build_cylindrical_roller
from .angular_contact import build_angular_contact
from .deep_groove import build_deep_groove
from .geometry_checks import inspect_solid
from .assembly_quality import build_assembly, audit_step_roundtrip

BUNDLE_VERSION = "cad-v2-artifacts/1"
GENERATOR_VERSION = "0.9.5"


def _digest(path: Path) -> str:
    checksum = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _identity(request: BearingRequest) -> str:
    payload = json.dumps(
        {"request_hash": request.request_hash, "bundle_version": BUNDLE_VERSION,
         "generator_version": GENERATOR_VERSION, "cadquery_version": cq.__version__,
         "formats": ["step", "stl"]},
        sort_keys=True, separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def verify_bundle(directory: Path, expected_key: str | None = None) -> dict:
    directory = Path(directory)
    data = json.loads((directory / "artifact_manifest.json").read_text(encoding="utf-8"))
    if expected_key is not None and data.get("artifact_key") != expected_key:
        raise ValueError("Artifact key mismatch")
    if data.get("bundle_version") != BUNDLE_VERSION:
        raise ValueError("Unsupported artifact version")
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Empty artifact manifest")
    for name, metadata in files.items():
        if name != Path(name).name or not isinstance(metadata, dict):
            raise ValueError("Unsafe artifact path")
        candidate = directory / name
        if not candidate.is_file() or candidate.stat().st_size != metadata.get("size_bytes"):
            raise ValueError("Missing or size-mismatched artifact: " + name)
        if _digest(candidate) != metadata.get("sha256"):
            raise ValueError("Artifact hash mismatch: " + name)
    return data


def generate_bundle(request: BearingRequest, output_root: Path) -> Path:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    key = _identity(request)
    final = output_root / key
    if final.exists():
        verify_bundle(final, key)  # Corrupt cache entries fail closed.
        return final

    if request.bearing_type == BearingType.DEEP_GROOVE:
        model = build_deep_groove(request)
    elif request.bearing_type == BearingType.CYLINDRICAL:
        model = build_cylindrical_roller(request)
    elif request.bearing_type == BearingType.ANGULAR_CONTACT:
        model = build_angular_contact(request)
    else:
        raise ContractError("NOT_SUPPORTED", "/bearing_type", "CAD builder not implemented")
    assembly = build_assembly(model)
    with tempfile.TemporaryDirectory(prefix=".cad-v2-staging-", dir=output_root) as temp:
        folder = Path(temp)
        step_path = folder / "bearing_assembly.step"
        assembly.save(str(step_path))
        reread = cq.importers.importStep(str(step_path)).solids().vals()
        quality = audit_step_roundtrip(model, assembly, reread)
        (folder / "geometry_quality.json").write_text(
            json.dumps(quality, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        for component in model.components:
            if not inspect_solid(component.shape).valid:
                raise RuntimeError("Invalid B-Rep component " + component.component_id)
            cq.exporters.export(component.shape, str(folder / (component.component_id + ".stl")),
                                exportType="STL")

        (folder / "design_snapshot.json").write_text(request.canonical_json(), encoding="utf-8")
        files = {path.name: {"sha256": _digest(path), "size_bytes": path.stat().st_size}
                 for path in sorted(folder.iterdir()) if path.is_file()}
        manifest = {
            "bundle_version": BUNDLE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "cadquery_version": cq.__version__,
            "artifact_key": key,
            "request_hash": request.request_hash,
            "geometry_unit": "mm",
            "bearing_type": request.bearing_type.value,
            "configuration": request.parameters.get("configuration"),
            "contact_angle_deg": request.parameters.get("contact_angle_deg"),
            "status": "GEOMETRY_VALIDATED",
            "completeness": (
                "CAGE_OMITTED" if request.cage is None else
                "CYLINDRICAL_WINDOW_CAGE" if request.cage.kind == "cylindrical_window"
                else "STRAIGHT_POCKET_CAGE" if request.cage.kind == "straight_pocket"
                else "STAMPING_DOUBLE_HALF" if request.cage.kind == "stamping_double_half"
                else "SIMPLIFIED_CAGE"
            ),
            "parts": [{"id": part.component_id, "role": part.role} for part in model.components],
            "instances": [
                {"id": inst.instance_id, "part_id": inst.component_id,
                 "translation_mm": list(inst.translation_mm),
                 "rotation_about_z_deg": float(inst.rotation_about_z_deg)}
                for inst in model.instances
            ],
            "files": files,
        }
        (folder / "artifact_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        verify_bundle(folder, key)
        try:
            folder.rename(final)
        except OSError:
            if not final.exists():
                raise
            verify_bundle(final, key)  # Concurrent successful writer.
        return final

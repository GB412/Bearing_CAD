"""Synchronous, server-configured RoBAS quasi-static analysis orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import platform
import re
from uuid import uuid4

from .contracts import BearingType, ContractError, MAX_CAD_DIMENSION_MM, parse_request
from .robas_ball_input import BallDataError, update_ball_data
from .robas_data import dotnet_round
from .robas_results import ResultParseError, parse_static_results
from .robas_roller_input import RollerDataError, update_roller_data
from .robas_solver_probe import SolverProbeError, inspect_executable, inspect_static_input, run_probe


_TIMEOUT_S = 45
_MAX_RETAINED_RUNS = 32
_MAX_PARSED_FILE = 2 * 1024 * 1024
_OUTPUT_NAMES = (
    "a0_Final", "a1_Outer", "a2_Inner", "a3_Cage1", "a4_CaseN", "a5_Roller1",
    "a6_RollerN", "a7_LifePower", "a8_Animation", "a9_User",
)
# Body keys are physical inputs, never DATA record selectors. Indices below
# are ball layout indices. The roller layout has one extra geometry record.
_CONDITIONS = {
    "load_x_n": (29, "appLoadX", -1e6, 1e6),
    "load_y_n": (29, "appLoadY", -1e6, 1e6),
    "load_z_n": (29, "appLoadZ", -1e6, 1e6),
    "outer_speed_rpm": (30, "rpm1", -1e5, 1e5),
    "inner_speed_rpm": (30, "rpm2", -1e5, 1e5),
}


@dataclass(frozen=True)
class ReferenceProfile:
    bearing_type: BearingType
    configuration: str | None
    path: Path
    sha256: str
    source: str


class AnalysisError(ContractError):
    def __init__(self, status: int, code: str, field: str, message: str, **evidence):
        super().__init__(code, field, message)
        self.status = status
        self.evidence = evidence


def load_analysis_profiles(manifest: Path | None) -> dict[str, ReferenceProfile]:
    """Load an operator-owned manifest. Requests can only select one of its IDs."""
    if manifest is None:
        return {}
    manifest = manifest.resolve(strict=True)
    with manifest.open("rb") as stream:
        raw = stream.read(32769)
    if len(raw) > 32768:
        raise ValueError("RoBAS analysis profile manifest exceeds 32 KiB")
    try:
        entries = json.loads(raw)
    except ValueError as exc:
        raise ValueError("RoBAS analysis profile manifest contains invalid JSON") from exc
    if not isinstance(entries, dict) or len(entries) > 16:
        raise ValueError("Expected up to 16 RoBAS analysis profiles by ID")
    profiles = {}
    for key, entry in entries.items():
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) or not isinstance(entry, dict)
                or set(entry) != {"bearing_type", "configuration", "data_file", "sha256", "source"}):
            raise ValueError(f"Invalid RoBAS analysis profile entry {key!r}")
        bearing_type = BearingType(entry["bearing_type"])
        configuration = entry["configuration"]
        if configuration != ("N" if bearing_type is BearingType.CYLINDRICAL else None):
            raise ValueError(f"Invalid source configuration for profile {key!r}")
        digest, source, relative = entry["sha256"], entry["source"], entry["data_file"]
        if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not isinstance(source, str) or not source.strip() or len(source) > 256
                or not isinstance(relative, str) or not relative.strip() or Path(relative).anchor):
            raise ValueError(f"Invalid file, SHA-256 or source for profile {key!r}")
        path = (manifest.parent / relative).resolve()
        if not path.is_relative_to(manifest.parent):
            raise ValueError(f"Profile {key!r} DATA must stay under the manifest directory")
        profiles[key] = ReferenceProfile(bearing_type, configuration, path, digest, source)
    return profiles


def _public_profile(profile: ReferenceProfile) -> dict:
    return {"bearing_type": profile.bearing_type.value, "configuration": profile.configuration,
            "sha256": profile.sha256, "source": profile.source}


def _operating_targets(roller: bool) -> dict:
    return {key: (record + int(roller), field) for key, (record, field, _, _) in _CONDITIONS.items()}


def _effective_conditions(document, targets: dict) -> dict:
    effective = {key: float(document.value(*target)) for key, target in targets.items()}
    effective["free_clearance_mm"] = float(document.value(10, "freeIntCls")) * 1000
    if (any(not low <= effective[key] <= high for key, (_, _, low, high) in _CONDITIONS.items())
            or not 0 <= effective["free_clearance_mm"] <= 10):
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Effective conditions exceed analysis limits")
    return effective


def _check_profile_document(profile: ReferenceProfile, document) -> None:
    if document.reference_data_sha256 != profile.sha256:
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Reference DATA does not match the pinned SHA-256")
    if document.rows[3][1:] != tuple(f"'{name}'" for name in _OUTPUT_NAMES):
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Reference DATA specifies unsupported output filenames")


def _check_reference(profile: ReferenceProfile) -> None:
    roller = profile.bearing_type is BearingType.CYLINDRICAL
    try:
        info = inspect_static_input(profile.path, family="roller" if roller else "ball")
    except (SolverProbeError, OSError) as exc:
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Reference DATA is missing or has an invalid protocol") from exc
    if info["input_sha256"] != profile.sha256:
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Reference DATA does not match the pinned SHA-256")
    try:
        if roller:
            document = update_roller_data(profile.path, None, reference_configuration=profile.configuration,
                                          geometry_mode="legacy_data", operating_updates={})
        else:
            document = update_ball_data(profile.path, None, geometry_mode="legacy_data", operating_updates={})
    except (BallDataError, RollerDataError, OSError, UnicodeError) as exc:
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Reference DATA cannot be used as a supported profile") from exc
    _check_profile_document(profile, document)
    _effective_conditions(document, _operating_targets(roller))


def _check_storage(root: Path) -> Path:
    store = root / "robas-analysis"
    try:
        if store.is_symlink() or (store.exists() and not store.is_dir()):
            raise OSError("Analysis storage must be a real directory")
        if store.is_dir() and sum(path.name.startswith("analysis-") for path in store.iterdir()) >= _MAX_RETAINED_RUNS:
            raise AnalysisError(503, "ANALYSIS_STORAGE_LIMIT", "", "Analysis storage is full; archive completed runs locally")
    except OSError as exc:
        raise AnalysisError(500, "ANALYSIS_STORAGE_FAILED", "", "Cannot inspect local analysis storage") from exc
    return store


def analysis_status(resources: Path | None, profiles: dict[str, ReferenceProfile], *, root: Path) -> dict:
    blocked = None
    if not profiles or resources is None or platform.system() != "Windows":
        blocked = "Windows, RoBAS resources or analysis profiles are unavailable"
    else:
        try:
            inspect_executable(resources)
        except (SolverProbeError, OSError):
            blocked = "The verified RoBAS executable is unavailable"
        if blocked is None:
            try:
                _check_storage(root)
            except AnalysisError as error:
                blocked = str(error)
    statuses = {}
    for key, profile in profiles.items():
        entry = {**_public_profile(profile), "available": False}
        if blocked is None:
            try:
                _check_reference(profile)
            except AnalysisError as error:
                entry["unavailable_reason"] = str(error)
            else:
                entry["available"] = True
        else:
            entry["unavailable_reason"] = blocked
        statuses[key] = entry
    return {"available": any(entry["available"] for entry in statuses.values()), "profiles": statuses,
            "timeout_s": _TIMEOUT_S, **({"unavailable_reason": blocked} if blocked is not None else {})}


def _fields(value, required: set[str], optional: set[str], path: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError("PARAMETER_INVALID", path, "Expected object")
    if extra := sorted(value.keys() - required - optional):
        raise ContractError("PARAMETER_INVALID", f"{path}/{extra[0]}", "Unknown field")
    if missing := sorted(required - value.keys()):
        raise ContractError("PARAMETER_INVALID", f"{path}/{missing[0]}", "Required field is missing")
    return value


def _number(value, path: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ContractError("PARAMETER_INVALID", path, f"Expected a finite number in [{low:g}, {high:g}]")
    return float(value)


def run_analysis(data, *, resources: Path | None, profiles: dict[str, ReferenceProfile], root: Path) -> dict:
    """Run one supplied design snapshot. The HTTP service serializes calls per process."""
    body = _fields(data, {"design", "request_hash", "profile_id", "operating_conditions", "analysis_geometry"},
                   {"allow_reference_geometry_mismatch"}, "")
    try:
        request = parse_request(body["design"])
    except ContractError as exc:
        raise ContractError(exc.error_code, "/design" + exc.field_path, str(exc)) from exc
    except OverflowError as exc:
        raise ContractError("PARAMETER_INVALID", "/design/parameters", "Design numeric value exceeds the supported range") from exc
    if body["request_hash"] != request.request_hash:
        raise AnalysisError(409, "DESIGN_HASH_MISMATCH", "/request_hash", "Design snapshot does not match the supplied request hash")
    roller = request.bearing_type is BearingType.CYLINDRICAL
    acb = request.bearing_type is BearingType.ANGULAR_CONTACT
    if roller and request.parameters["configuration"] != "N":
        raise ContractError("NOT_SUPPORTED", "/design/parameters/configuration", "Only CRB N is supported")
    if roller:
        for field, supported in (("roller_profile", "plain"), ("roller_end_chamfer_mm", 0), ("roller_crown_relief_mm", 0)):
            if request.parameters.get(field, supported) != supported:
                raise ContractError("NOT_SUPPORTED", "/design/parameters/" + field, "Only plain CRB rollers are supported")
    if not roller and request.cage is not None:
        raise ContractError("NOT_SUPPORTED", "/design/cage",
                            "The explicit CAD cage is not mapped to the original RoBAS ball analysis cage")
    if acb and "cage_material" in request.parameters:
        raise ContractError("NOT_SUPPORTED", "/design/parameters/cage_material",
                            "ACB CAD cage material is not mapped to the reference analysis material")

    geometry_fields = set() if roller else {"inner_race_od_mm"}
    if acb:
        geometry_fields.update(("inner_sidewall_mm", "outer_sidewall_mm"))
    geometry = {key: _number(value, "/analysis_geometry/" + key, 0.001, MAX_CAD_DIMENSION_MM)
                for key, value in _fields(body["analysis_geometry"], geometry_fields, set(), "/analysis_geometry").items()}
    p = request.parameters
    if not roller and not p["bore_d_mm"] < geometry["inner_race_od_mm"] < p["pitch_d_mm"]:
        raise ContractError("PARAMETER_INVALID", "/analysis_geometry/inner_race_od_mm",
                            "Analysis inner race OD must lie between the design bore and pitch")
    if acb:
        for race, digits in (("inner", 1), ("outer", 2)):
            key = f"{race}_sidewall_mm"
            shoulders = {dotnet_round(p[f"{race}_shoulder_{side}_d_mm"], digits) for side in ("left", "right")}
            if dotnet_round(geometry[key], digits) not in shoulders:
                raise ContractError("PARAMETER_INVALID", "/analysis_geometry/" + key,
                                    "Select an explicit sidewall from the supplied ACB design snapshot")
    override = body.get("allow_reference_geometry_mismatch", False)
    if type(override) is not bool:
        raise ContractError("PARAMETER_INVALID", "/allow_reference_geometry_mismatch", "Expected boolean")
    conditions = _fields(body["operating_conditions"], set(), set(_CONDITIONS) | {"free_clearance_mm"},
                         "/operating_conditions")
    conditions = {key: _number(value, "/operating_conditions/" + key,
                               *(_CONDITIONS[key][2:] if key in _CONDITIONS else (0, 10)))
                  for key, value in conditions.items()}
    if roller and request.parameters["radial_clearance_mm"] != 0 and "free_clearance_mm" not in conditions:
        raise ContractError("PARAMETER_INVALID", "/operating_conditions/free_clearance_mm",
                            "Supply the independent solver free clearance when the CAD radial gap is nonzero")

    if not profiles or resources is None or platform.system() != "Windows":
        raise AnalysisError(503, "ANALYSIS_UNAVAILABLE", "", "RoBAS analysis needs Windows, resources and configured reference profiles")
    profile_id = body["profile_id"]
    profile = profiles.get(profile_id) if isinstance(profile_id, str) else None
    if profile is None or profile.bearing_type is not request.bearing_type:
        raise ContractError("ANALYSIS_PROFILE_INVALID", "/profile_id", "Select a configured profile for this bearing type")
    family = "roller" if roller else "ball"
    _check_reference(profile)
    indices = _operating_targets(roller)
    updates = {indices[key]: value for key, value in conditions.items() if key in indices}
    clearance = conditions.get("free_clearance_mm")
    common = {"geometry_mode": "cad_geometry", "operating_updates": updates,
              "allow_reference_geometry_mismatch": override}
    try:
        if roller:
            document = update_roller_data(profile.path, request, reference_configuration=profile.configuration,
                                          analysis_free_clearance_mm=clearance, **common)
        else:
            shoulders = (geometry["inner_sidewall_mm"], geometry["outer_sidewall_mm"]) if acb else None
            document = update_ball_data(
                profile.path, request, analysis_inner_race_outside_diameter_mm=geometry["inner_race_od_mm"],
                analysis_shoulder_diameters_mm=shoulders,
                analysis_parameters_mm={"freeIntCls": clearance} if clearance is not None else None, **common,
            )
    except (BallDataError, RollerDataError) as exc:
        field = "/allow_reference_geometry_mismatch" if str(exc).startswith("reference DATA geometry differs") else "/analysis_geometry"
        raise ContractError("ANALYSIS_INPUT_INVALID", field, str(exc)) from exc
    except (OSError, UnicodeError) as exc:
        raise AnalysisError(503, "ANALYSIS_PROFILE_INVALID", "/profile_id", "Reference DATA cannot be read") from exc
    _check_profile_document(profile, document)

    payload = document.render().encode("utf-8")
    data_sha = sha256(payload).hexdigest()
    effective = _effective_conditions(document, indices)
    inherited = {key: value for key, value in effective.items() if key not in conditions}
    run_id = uuid4().hex
    store = _check_storage(root)
    folder = store / ("analysis-" + run_id)
    record = {"schema_version": "bearing-cad.robas-analysis.v1", "run_id": run_id,
              "request_hash": request.request_hash, "design": json.loads(request.canonical_json()),
              "profile": {"id": profile_id, **_public_profile(profile)}, "analysis_geometry": geometry,
              "allow_reference_geometry_mismatch": override, "generated_data_sha256": data_sha,
              "operating_conditions": {"requested": conditions, "inherited": inherited, "effective": effective}}
    try:
        store.mkdir(exist_ok=True)
        folder.mkdir(mode=0o700)
        data_path = folder / "DATA.txt"
        data_path.write_bytes(payload)
        (folder / "analysis_request.json").write_text(json.dumps(record, allow_nan=False), encoding="utf-8")
        report = run_probe(resources=resources, input_path=data_path, family=family,
                           output_dir=folder, timeout_s=_TIMEOUT_S)
    except SolverProbeError as exc:
        raise AnalysisError(503, "ANALYSIS_PREFLIGHT_FAILED", "", str(exc), run_id=run_id) from exc
    except OSError as exc:
        raise AnalysisError(500, "ANALYSIS_STORAGE_FAILED", "", "Cannot write or read isolated analysis evidence", run_id=run_id) from exc

    output_status = report["output_status"]
    execution = {"solver_executed": report["solver_executed"], "exit_code": report["process_exit_code"],
                 "probe_output_status": output_status}
    if output_status != "OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF":
        status = 504 if output_status == "PROCESS_TIMEOUT" else 502
        code = {"PROCESS_TIMEOUT": "ANALYSIS_TIMEOUT", "OUTPUT_ABSENT_OR_INVALID": "ANALYSIS_OUTPUT_INVALID"}.get(
            output_status, "ANALYSIS_EXECUTION_FAILED")
        raise AnalysisError(status, code, "", f"RoBAS reported {output_status}", run_id=run_id, execution=execution)
    try:
        run_directory = Path(report["run_directory"]).resolve(strict=True)
        if run_directory.parent != folder or report["input"]["input_sha256"] != data_sha:
            raise ResultParseError("solver_probe_report.json", "execution evidence differs from the generated input or run directory")
        for name in ("OUT.txt", "a0_Final"):
            file = run_directory / name
            if file.is_file() and file.stat().st_size > _MAX_PARSED_FILE:
                raise ResultParseError(name, "exceeds the analysis API's 2 MiB parsing limit")
        result = parse_static_results(run_directory, family=family, probe_report=report)
        if result["source_binding"]["status"] != "HASH_VERIFIED":
            raise ResultParseError("solver_probe_report.json", "same-run hash binding is required")
    except (ResultParseError, OSError) as exc:
        field = "/result/" + exc.filename if isinstance(exc, ResultParseError) else "/result"
        message = str(exc) if isinstance(exc, ResultParseError) else "Cannot read isolated run output"
        raise AnalysisError(502, "ANALYSIS_RESULT_INVALID", field, message, run_id=run_id, execution=execution) from exc

    response = {**record, "solver_exe_sha256": report["exe"]["sha256"], "result": result}
    try:
        (folder / "analysis_result.json").write_text(json.dumps(response, allow_nan=False), encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(500, "ANALYSIS_STORAGE_FAILED", "", "Cannot save the verified analysis result", run_id=run_id) from exc
    return response

"""Strict JSON boundary for future deterministic bearing builders.

All distances are millimetres, angles in public requests are degrees, and the
bearing axis is Z (mid-plane Z=0). No catalogue dimensions are guessed here.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping
from types import MappingProxyType

SCHEMA_VERSION = "bearing-cad.request.v1"


class ContractError(ValueError):
    def __init__(self, code: str, field_path: str, message: str):
        super().__init__(message)
        self.error_code = code
        self.field_path = field_path

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.error_code, "field_path": self.field_path,
                "message": str(self)}


class BearingType(str, Enum):
    DEEP_GROOVE = "rolling.deep_groove_ball"
    CYLINDRICAL = "rolling.cylindrical_roller"
    ANGULAR_CONTACT = "rolling.angular_contact_ball"


@dataclass(frozen=True)
class CageSpec:
    kind: str
    inner_d_mm: float
    outside_d_mm: float
    width_mm: float
    pocket_clearance_mm: float


@dataclass(frozen=True)
class StampedCageSpec(CageSpec):
    board_thickness_mm: float
    rivet_shaft_d_mm: float
    rivet_head_d_mm: float
    rivet_hole_clearance_mm: float


@dataclass(frozen=True)
class BearingRequest:
    schema_version: str
    bearing_type: BearingType
    unit: str
    detail_level: str
    geometry_strategy: str
    parameters: Mapping[str, float | int | str]
    cage: CageSpec | None = None

    def __post_init__(self) -> None:
        # A frozen dataclass does not freeze nested dictionaries by itself.
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def canonical_json(self) -> str:
        payload = {"schema_version": self.schema_version, "bearing_type": self.bearing_type.value,
                   "unit": self.unit, "detail_level": self.detail_level,
                   "geometry_strategy": self.geometry_strategy,
                   "parameters": dict(self.parameters)}
        if self.cage is not None:
            payload["cage"] = asdict(self.cage)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=True)

    @property
    def request_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ComponentDefinition:
    component_id: str
    role: str
    shape: Any  # An opaque B-Rep reference, never imported into domain layer.


@dataclass(frozen=True)
class ComponentInstance:
    instance_id: str
    component_id: str
    translation_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_about_z_deg: float = 0.0


@dataclass(frozen=True)
class AssemblyModel:
    bearing_type: BearingType
    components: tuple[ComponentDefinition, ...]
    instances: tuple[ComponentInstance, ...]

    def __post_init__(self) -> None:
        ids = [p.component_id for p in self.components]
        instance_ids = [p.instance_id for p in self.instances]
        if len(ids) != len(set(ids)) or len(instance_ids) != len(set(instance_ids)):
            raise ContractError("PARAMETER_INVALID", "/assembly", "Duplicate component or instance IDs")
        if any(p.component_id not in ids for p in self.instances):
            raise ContractError("PARAMETER_INVALID", "/assembly/instances", "Unknown component definition")
        if not self.instances or not self.components:
            raise ContractError("PARAMETER_INVALID", "/assembly", "Assembly must not be empty")
        for item in self.instances:
            values = (*item.translation_mm, item.rotation_about_z_deg)
            if (len(item.translation_mm) != 3 or
                any(type(number) not in (int, float) or not math.isfinite(number)
                    for number in values)):
                raise ContractError("PARAMETER_INVALID", "/assembly/instances",
                                    "Instance transform must be finite X/Y/Z mm and Z rotation degrees")


_COMMON = ("bore_d_mm", "outside_d_mm", "width_mm")
_TYPES: dict[BearingType, tuple[str, ...]] = {
    BearingType.DEEP_GROOVE: (*_COMMON, "ball_d_mm", "pitch_d_mm", "ball_count",
                              "inner_groove_radius_mm", "outer_groove_radius_mm",
                              "inner_shoulder_d_mm", "outer_shoulder_d_mm"),
    BearingType.CYLINDRICAL: (*_COMMON, "roller_d_mm", "roller_length_mm", "pitch_d_mm",
                              "roller_count", "configuration", "radial_clearance_mm",
                              "axial_clearance_mm", "rib_width_mm",
                              "inner_rib_tip_d_mm", "outer_rib_tip_d_mm"),
    BearingType.ANGULAR_CONTACT: (*_COMMON, "ball_d_mm", "pitch_d_mm", "ball_count",
                                  "inner_groove_radius_mm", "outer_groove_radius_mm",
                                  "contact_angle_deg", "inner_shoulder_left_d_mm",
                                  "inner_shoulder_right_d_mm", "outer_shoulder_left_d_mm",
                                  "outer_shoulder_right_d_mm"),
}
_COUNTS = {"ball_count", "roller_count"}
_TEXT = {"configuration"}
# All entry points use the same local CAD resource limit (not a bearing standard).
MAX_ROLLING_ELEMENTS = 64
# Zero geometric clearance is a valid contact case; negative interference is not.
_NONNEGATIVE = {"radial_clearance_mm", "axial_clearance_mm"}


def _closed_object(value: Any, allowed: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ContractError("PARAMETER_INVALID", path, "Expected JSON object with string keys")
    extra = sorted(value.keys() - allowed)
    if extra:
        raise ContractError("PARAMETER_INVALID", f"{path}/{extra[0]}", "Unknown field")
    missing = sorted(allowed - value.keys())
    if missing:
        raise ContractError("PARAMETER_INVALID", f"{path}/{missing[0]}", "Missing required field")
    return value


def parse_request(data: Mapping[str, Any]) -> BearingRequest:
    """Reject unknown/missing inputs; do not silently infer RoBAS parameters."""
    if not isinstance(data, dict):
        raise ContractError("PARAMETER_INVALID", "", "Expected request object")
    cage_present = "cage" in data
    cage_raw = data.get("cage")
    envelope = _closed_object({k:v for k,v in data.items() if k != "cage"},
                              {"schema_version", "bearing_type", "unit",
                               "detail_level", "geometry_strategy", "parameters"}, "")
    if envelope["schema_version"] != SCHEMA_VERSION:
        raise ContractError("SCHEMA_UNSUPPORTED", "/schema_version", "Unsupported schema version")
    try:
        kind = BearingType(envelope["bearing_type"])
    except (ValueError, TypeError):
        raise ContractError("NOT_SUPPORTED", "/bearing_type", "Unsupported bearing type") from None
    for name, allowed in (("unit", {"mm"}), ("detail_level", {"functional", "detailed", "envelope"}),
                          ("geometry_strategy", {"explicit"})):
        if not isinstance(envelope[name], str) or envelope[name] not in allowed:
            raise ContractError("PARAMETER_INVALID", f"/{name}", f"Unsupported {name}")

    fields = _TYPES[kind]
    raw = _closed_object(envelope["parameters"], set(fields), "/parameters")
    params: dict[str, float | int | str] = {}
    for field in fields:
        val = raw[field]
        path = "/parameters/" + field
        if field in _TEXT:
            if not isinstance(val, str) or val not in {"N", "NU", "NJ", "NUP", "NF"}:
                raise ContractError("PARAMETER_INVALID", path, "Invalid roller configuration")
            params[field] = val
        elif field in _COUNTS:
            if type(val) is not int or not 1 <= val <= MAX_ROLLING_ELEMENTS:
                raise ContractError("PARAMETER_INVALID", path, "Expected positive integer (max 64)")
            params[field] = val
        else:
            if type(val) not in (float, int) or (isinstance(val, int) and val.bit_length() > 1024):
                raise ContractError("PARAMETER_INVALID", path, "Expected finite number")
            try:
                finite = math.isfinite(val)
            except OverflowError:
                finite = False
            if not finite:
                raise ContractError("PARAMETER_INVALID", path, "Expected finite number")
            val = float(val)
            if field == "contact_angle_deg":
                if not 0.0 < val < 90.0:
                    raise ContractError("PARAMETER_INVALID", path, "Contact angle must be between 0 and 90 degrees")
            elif val < 0.0 or (val == 0.0 and field not in _NONNEGATIVE):
                raise ContractError("PARAMETER_INVALID", path,
                                    "Dimension must be positive, or nonnegative geometric clearance in mm")
            if val > 1000.0:
                raise ContractError("RESOURCE_LIMIT", path,
                                    "CAD service numeric budget exceeded (1000 mm)")
            params[field] = val
    if params["bore_d_mm"] >= params["outside_d_mm"]:
        raise ContractError("PARAMETER_INVALID", "/parameters/outside_d_mm", "Outer diameter must exceed bore")
    if not params["bore_d_mm"] < params["pitch_d_mm"] < params["outside_d_mm"]:
        raise ContractError("PARAMETER_INVALID", "/parameters/pitch_d_mm", "Pitch diameter must lie between bore and outside diameters")
    cage = None
    if cage_present:
        stamped = (kind == BearingType.DEEP_GROOVE
                   and isinstance(cage_raw, dict)
                   and cage_raw.get("kind") == "stamping_double_half")
        fields = {"kind", "inner_d_mm", "outside_d_mm", "width_mm", "pocket_clearance_mm"}
        if stamped:
            fields |= {"board_thickness_mm", "rivet_shaft_d_mm",
                       "rivet_head_d_mm", "rivet_hole_clearance_mm"}
        obj = _closed_object(cage_raw, fields, "/cage")
        allowed_kind = ("stamping_double_half" if stamped else {
            BearingType.DEEP_GROOVE: "simplified_annular",
            BearingType.CYLINDRICAL: "cylindrical_window",
            BearingType.ANGULAR_CONTACT: "straight_pocket"}[kind])
        if obj["kind"] != allowed_kind:
            raise ContractError("NOT_SUPPORTED", "/cage/kind",
                                f"Cage kind not implemented for {kind.value}")
        values = {}
        for field in fields - {"kind"}:
            value = obj[field]
            if type(value) not in (int, float) or (type(value) is int and value.bit_length() > 1024):
                raise ContractError("PARAMETER_INVALID", f"/cage/{field}", "Expected positive mm")
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite or value <= 0:
                raise ContractError("PARAMETER_INVALID", f"/cage/{field}", "Expected finite positive mm")
            values[field] = float(value)
        if values["inner_d_mm"] >= values["outside_d_mm"]:
            raise ContractError("PARAMETER_INVALID", "/cage/outside_d_mm", "Cage outer must exceed cage inner")
        cage_type = StampedCageSpec if stamped else CageSpec
        cage = cage_type(kind=allowed_kind, **values)
    return BearingRequest(SCHEMA_VERSION, kind, "mm", envelope["detail_level"],
                          "explicit", params, cage)

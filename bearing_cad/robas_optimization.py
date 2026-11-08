"""Source-based DGB multi-objective candidate search, never automatic CAD mutation.

First migration slice of RoBAS DGBOptimizer.Optimizer: the original five
diameter x five count x four pitch search with source model-specific bounds,
radial-load/stiffness formulas and exact source coefficient rows. The original
second-best index bug is deliberately not reproduced: candidates are ranked
and a human chooses which design is applied.

No B-Rep is built here. Returned values are not approved engineering designs.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from .contracts import BearingRequest, BearingType, ContractError, parse_request
from .drawing_consistency import audit_drawing_design
from .drawing_legacy_ratings import _coefficients
from .drawing_standards import original_dotnet_math_round
from .robas_sizing import _read, dgb_radial_clearance_mm


class OptimizationError(ValueError):
    def __init__(self, message: str, field_path: str = "/optimization"):
        super().__init__(message)
        self.field_path = field_path


_MODEL = re.compile(r"^(60|62|63)[0-9]{2,3}$")
_GRADES = {"P0", "P6", "P5", "P4", "P2"}
_CLEARANCE_GROUPS = {"C2", "C0", "C3", "C4", "C5"}
_MAX_RESULTS = 5


def _validate_options(data) -> dict:
    expected = {"model", "accuracy_class", "radial_clearance_group", "weights"}
    if type(data) is not dict or set(data) != expected:
        raise OptimizationError(
            "Expected model, accuracy_class, radial_clearance_group and weights")
    model, grade, group = (
        data["model"], data["accuracy_class"], data["radial_clearance_group"])
    if type(model) is not str or not _MODEL.fullmatch(model):
        raise OptimizationError(
            "RoBAS DGBOptimizer supports source model series 60, 62 and 63",
            "/optimization/model")
    if type(grade) is not str or grade not in _GRADES:
        raise OptimizationError("Unknown RoBAS accuracy class",
                                "/optimization/accuracy_class")
    if type(group) is not str or group not in _CLEARANCE_GROUPS:
        raise OptimizationError("Choose a RoBAS radial clearance group",
                                "/optimization/radial_clearance_group")
    weights = data["weights"]
    if type(weights) is not dict or set(weights) != {"dynamic_load", "radial_stiffness"}:
        raise OptimizationError(
            "Weights must include dynamic_load and radial_stiffness",
            "/optimization/weights")
    for key in ("dynamic_load", "radial_stiffness"):
        x = weights[key]
        if type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1:
            raise OptimizationError("Weights must be finite numbers in [0,1]",
                                    "/optimization/weights/" + key)
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise OptimizationError("Optimization weights must add to 1",
                                "/optimization/weights")
    return {"model": model, "accuracy_class": grade,
            "radial_clearance_group": group,
            "weights": {key: float(weights[key]) for key in
                        ("dynamic_load", "radial_stiffness")}}


def _source_bounds(model: str, bore: float) -> tuple[float, float, float, float]:
    """RoBAS DGBOptimizer.SetCoeffccient: Kwmin/Kwmax/Phimax/Kd."""
    if not 0 < bore <= 240:
        raise OptimizationError("RoBAS DGB coefficient ranges end at d=240 mm",
                                "/design/parameters/bore_d_mm")
    prefix = model[:2]
    if prefix == "60":
        intervals = ((.24, .30), (.30, .32), (.29, .33))
        return (*intervals[0 if bore <= 35 else 1 if bore <= 120 else 2],
                195.0, .35)
    if prefix == "62":
        intervals = ((.24, .31), (.30, .32), (.28, .32))
        return (*intervals[0 if bore <= 35 else 1 if bore <= 120 else 2],
                194.0, .35 if bore <= 25 else .40)
    intervals = ((.25, .32), (.30, .33), (.29, .32))
    return (*intervals[0 if bore <= 35 else 1 if bore <= 120 else 2],
            193.0, .35 if bore <= 25 else .40)


def _normalize(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if math.isclose(high, low, rel_tol=0, abs_tol=1e-12):
        # The original BaseOptimizer divided by zero here; a tied objective
        # provides no discriminatory information, so score all ties equally.
        return [0.0] * len(values)
    return [(value - low) / (high - low) for value in values]


def _nearest_diameter(values: list[float], target: float) -> float:
    # BaseOptimizer.DetermineRollerDiameter uses relative deviation.
    return min(values, key=lambda value: abs(1 - target / value))


def _candidate_design(request: BearingRequest, ball: float, count: int,
                      pitch: float, clearance: float, kd: float) -> dict | None:
    params = dict(request.parameters)
    bore, outside, width = (
        float(params["bore_d_mm"]), float(params["outside_d_mm"]),
        float(params["width_mm"]))
    ir, or_ = .51 * ball, .53 * ball
    inner_groove_d = pitch - ball
    outer_groove_d = pitch + ball + clearance
    inner_shoulder = inner_groove_d + kd * ball
    outer_shoulder = outer_groove_d - kd * ball

    if not (bore < inner_shoulder < pitch < outer_shoulder < outside):
        return None
    if not (pitch / 2 - ir > bore / 2 and
            pitch / 2 + or_ < outside / 2 and
            pitch * math.sin(math.pi / count) > ball):
        return None

    params.update({
        "ball_d_mm": ball, "ball_count": count, "pitch_d_mm": pitch,
        "inner_groove_radius_mm": ir, "outer_groove_radius_mm": or_,
        "inner_shoulder_d_mm": inner_shoulder,
        "outer_shoulder_d_mm": outer_shoulder,
    })
    design = json.loads(request.canonical_json())
    design["parameters"] = params
    if request.cage is not None:
        if request.cage.kind != "simplified_annular":
            raise OptimizationError(
                "Stamped cage geometry must be recomputed separately; "
                "disable the cage or select simplified_annular first",
                "/design/cage/kind")
        inner_cage = 1.02 * inner_shoulder
        outer_cage = .98 * outer_shoulder
        if not inner_shoulder < inner_cage < outer_cage < outer_shoulder:
            return None
        design["cage"] = {
            "kind": "simplified_annular",
            "inner_d_mm": inner_cage,
            "outside_d_mm": outer_cage,
            "width_mm": .95 * width,
            "pocket_clearance_mm": request.cage.pocket_clearance_mm,
        }
    try:
        parse_request(design)
    except ContractError:
        return None
    return design


def optimize_dgb_candidates(*, resources: Path, design: dict,
                            optimization: dict) -> dict:
    """Return top source-scored geometry candidates without applying any."""
    options = _validate_options(optimization)
    if not isinstance(design, dict):
        raise OptimizationError("Expected a complete current CAD design request",
                                "/design")
    request = parse_request(design)
    if request.bearing_type != BearingType.DEEP_GROOVE:
        raise OptimizationError(
            "Only DGB multi-objective optimizer is migrated in this PR",
            "/design/bearing_type")
    if request.cage is not None and request.cage.kind != "simplified_annular":
        raise OptimizationError(
            "The optimizer cannot reuse an unchanged stamped cage for a new ball arrangement",
            "/design/cage/kind")

    root = Path(resources)
    table = root / "Resource" / "BallDB.csv"
    coefficient = root / "Resource" / "球轴承零件相关系数.csv"
    for path in (table, coefficient):
        if not path.is_file() or path.is_symlink():
            raise OptimizationError("Missing original RoBAS CSV: " + path.name,
                                    "/optimization")
    try:
        diameter_rows = _read(table, ("diameter(mm)",))
    except (ValueError, OSError, UnicodeError) as error:
        raise OptimizationError("Invalid RoBAS ball diameter CSV: " + str(error)) from error
    balls = [row["diameter(mm)"] for row in diameter_rows]
    if len(balls) < 5 or any(a >= b for a, b in zip(balls, balls[1:])):
        raise OptimizationError("RoBAS BallDB.csv must contain ascending unique diameters")

    bore = float(request.parameters["bore_d_mm"])
    outside = float(request.parameters["outside_d_mm"])
    width = float(request.parameters["width_mm"])
    catalog = audit_drawing_design(
        resources=root, bearing_type=request.bearing_type.value,
        parameters=dict(request.parameters),
        model_label=options["model"] + "/" + options["accuracy_class"],
        configuration=None, accuracy_class=options["accuracy_class"],
        diameter_series=options["model"][1])
    kw_min, kw_max, phi_max, kd = _source_bounds(options["model"], bore)
    radial_clearance = dgb_radial_clearance_mm(bore)
    if radial_clearance is None:
        raise OptimizationError("Original radial clearance rule does not cover this bore",
                                "/design/parameters/bore_d_mm")

    span = outside - bore
    middle = .5 * (outside + bore)
    d0 = _nearest_diameter(balls, .30 * span)
    min_ball = _nearest_diameter(balls, kw_min * span)
    max_ball = _nearest_diameter(balls, kw_max * span)
    source_index = balls.index(d0)
    first = max(0, min(source_index - 2, len(balls) - 5))
    grid = balls[first:first + 5]
    angle = math.degrees(2 * math.asin(d0 / middle))
    nominal_count = int(186.0 / angle) + 1
    results = []
    for ball in grid:
        if not min_ball <= ball <= max_ball:
            continue
        for count in range(nominal_count - 2, nominal_count + 3):
            if not 2 <= count <= 64:
                continue
            for step in range(4):
                pitch = middle + .5 * step
                if pitch > .515 * (outside + bore):
                    continue
                if not 0 < ball < pitch:
                    continue
                fill_angle = math.degrees(2 * math.asin(ball / pitch)) * (count - 1)
                if not 180 <= fill_angle <= phi_max:
                    continue
                candidate_design = _candidate_design(
                    request, ball, count, pitch, radial_clearance, kd)
                if candidate_design is None:
                    continue
                gamma = original_dotnet_math_round(ball / pitch, 2)
                fc, fo, matched = _coefficients(root, gamma)
                if not matched or fc <= 0 or fo <= 0:
                    continue
                cr = 1.3 * fc * count ** (2.0 / 3.0) * ball ** 1.8 * (
                    1 if ball <= 25.4 else 3.467)
                cor = fo * count * ball ** 2
                radial_stiffness = 1180.0 * (
                    ball * .2 * cr * count * count) ** (1.0 / 3.0)
                if not all(math.isfinite(value) and value > 0
                           for value in (cr, cor, radial_stiffness)):
                    continue
                candidate_id = hashlib.sha256(
                    (request.request_hash + json.dumps(
                        candidate_design["parameters"], sort_keys=True)).encode()
                ).hexdigest()[:16]
                results.append({
                    "candidate_id": candidate_id,
                    "design": candidate_design,
                    "metrics": {
                        "dynamic_load_n": cr, "static_load_n": cor,
                        "radial_stiffness_source_units": radial_stiffness,
                        "fill_angle_deg": fill_angle,
                    },
                    "coefficient_lookup": {
                        "gamma": gamma, "fc": fc, "fo": fo,
                        "csv_file": coefficient.name,
                    },
                })
    if not results:
        raise OptimizationError(
            "No source-backed DGB candidates satisfy the original grid, "
            "filling-angle, geometric and coefficient constraints")

    norm_cr = _normalize([row["metrics"]["dynamic_load_n"] for row in results])
    norm_kr = _normalize([
        row["metrics"]["radial_stiffness_source_units"] for row in results])
    weights = options["weights"]
    for index, item in enumerate(results):
        item["score"] = (weights["dynamic_load"] * norm_cr[index] +
                         weights["radial_stiffness"] * norm_kr[index])
    # Unlike the RoBAS secondMaxIndex selection defect, return the actual
    # descending score list for explicit human confirmation.
    results.sort(key=lambda item: item["score"], reverse=True)
    winners = results[:_MAX_RESULTS]
    for rank, item in enumerate(winners, 1):
        item["rank"] = rank
    return {
        "schema_version": "bearing-cad.robas-dgb-optimization.v1",
        "candidate_only": True,
        "applied": False,
        "bearing_type": request.bearing_type.value,
        "source_design_hash": request.request_hash,
        "source_model": options["model"],
        "optimization": options,
        "source_catalog_evidence": catalog,
        "total_valid_candidates": len(results),
        "candidates": winners,
        "source_basis": [
            "RoBAS DGBOptimizer.Optimizer grid and DGBOptimizer.SetCoeffccient",
            "RoBAS DGBOptimizer.CalcuDynamicLoad",
            "RoBAS DGBOptimizer.CalcuRadialStiffness",
            "RoBAS Resource/BallDB.csv and 球轴承零件相关系数.csv",
        ],
        "warnings": [
            "CANDIDATE_ONLY_NOT_CAD_BREP_VERIFIED_OR_MANUFACTURING_APPROVED",
            "SOURCE_DGB_SECOND_BEST_SELECTION_BUG_NOT_REPRODUCED",
            "SOURCE_OPTIMIZER_WEIGHTS_DO_NOT_INCLUDE_APPLIED_LOAD_OR_RPM",
            "ACCURACY_AND_CLEARANCE_SELECTION_RECORDED_NOT_APPLIED_TO_OBJECTIVE_FORMULAS",
            *catalog.get("warnings", []),
        ],
    }

"""RoBAS ACBOptimizer sourced multi-objective search; candidate only.

Original C#:
- ACBOptimizer.SetCoeffccient: model series 70/72/73, width and bore bounds
- CalcuBallNum: cage-material-dependent ball count
- Optimizer: five BallDB diameters and counts, Dpw from mid-diameter in 0.05 mm
- CalcuSpinRatio/CalcuDynamicLoad/CalcuRadialStaticLoad/CalcuAxialStiffness
- GetIndexEvaluationFunctionMax: three normalized *maximization* objectives

The original ACB geometry describes a single shoulder diameter per race,
while Bearing_CAD requires asymmetric left/right shoulder diameters. This
adapter records that extra geometric construction explicitly; it is NOT a
claim of exact original C# B-Rep parity. No candidate changes CAD until
the user confirms it in the workbench.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re

from .contracts import BearingType, ContractError, parse_request
from .drawing_legacy_ratings import _coefficients
from .drawing_standards import original_dotnet_math_round
from .robas_sizing import _read
from .robas_optimization import OptimizationError, _normalize, _nearest_diameter

_MODEL = re.compile(r"^7[023]\d{2,3}$")
_MATERIALS = {"engineering_plastic", "phenolic"}
_GRADES = {"P0", "P6", "P5", "P4", "P2"}
_MAX_RESULTS = 5


def _finite_positive(value, path: str) -> float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or not 0 < value <= 1000:
        raise OptimizationError("Expected a finite positive number", path)
    return float(value)


def _initial(data) -> dict:
    expected = {
        "bearing_type", "bore_d_mm", "outside_d_mm", "width_mm",
        "contact_angle_deg", "cage_material", "cage",
    }
    if type(data) is not dict or set(data) != expected:
        raise OptimizationError("Expected ACB d/D/B, contact angle, cage material and cage", "/initial")
    if data["bearing_type"] != BearingType.ANGULAR_CONTACT.value:
        raise OptimizationError("Only ACB is supported by this optimizer", "/initial/bearing_type")
    if data["cage"] is not None:
        raise OptimizationError(
            "ACB cage must be recalculated after ball optimization; disable it "
            "until a source-backed cage adapter is verified", "/initial/cage")
    if data["cage_material"] not in _MATERIALS or type(data["cage_material"]) is not str:
        raise OptimizationError("Choose original engineering_plastic or phenolic material",
                                "/initial/cage_material")
    cleaned = {"bearing_type": data["bearing_type"], "cage": None,
               "cage_material": data["cage_material"]}
    for key in ("bore_d_mm", "outside_d_mm", "width_mm"):
        cleaned[key] = _finite_positive(data[key], "/initial/" + key)
    if cleaned["outside_d_mm"] <= cleaned["bore_d_mm"]:
        raise OptimizationError("Outside diameter must exceed bore", "/initial/outside_d_mm")
    alpha = _finite_positive(data["contact_angle_deg"], "/initial/contact_angle_deg")
    # RoBAS SetCoeffccient implements shoulder coefficients for 15, 25
    # and an "else" branch (normally 40); these are the audited modes.
    if alpha not in (15., 25., 40.):
        raise OptimizationError("Source ACB optimization supports 15, 25 or 40 degrees",
                                "/initial/contact_angle_deg")
    cleaned["contact_angle_deg"] = alpha
    return cleaned


def _options(data) -> dict:
    if type(data) is not dict or set(data) != {
        "model", "accuracy_class", "preload_n", "weights",
    }:
        raise OptimizationError("Expected ACB model, accuracy_class, preload_n, weights")
    model = data["model"]
    if type(model) is not str or not _MODEL.fullmatch(model):
        raise OptimizationError("RoBAS ACBOptimizer source model must be 70, 72 or 73 series",
                                "/optimization/model")
    grade = data["accuracy_class"]
    if type(grade) is not str or grade not in _GRADES:
        raise OptimizationError("Invalid accuracy class", "/optimization/accuracy_class")
    preload = _finite_positive(data["preload_n"], "/optimization/preload_n")
    weights = data["weights"]
    targets = ("spin_ratio", "axial_stiffness", "dynamic_load")
    if type(weights) is not dict or set(weights) != set(targets):
        raise OptimizationError("Expected spin_ratio, axial_stiffness, dynamic_load weights",
                                "/optimization/weights")
    converted = {}
    for key in targets:
        x = weights[key]
        try:
            valid = type(x) in (int, float) and math.isfinite(x)
        except OverflowError:
            valid = False
        if not valid or not 0 <= x <= 1:
            raise OptimizationError("Weights must be finite numbers in [0,1]",
                                    "/optimization/weights/" + key)
        converted[key] = float(x)
    if not math.isclose(sum(converted.values()), 1.0, abs_tol=1e-9, rel_tol=0):
        raise OptimizationError("ACB objective weights must add to 1",
                                "/optimization/weights")
    return {"model": model, "accuracy_class": grade,
            "preload_n": preload, "weights": converted}


def _source_bounds(model: str, bore: float, alpha: float) -> tuple[float, float, float, float]:
    """RoBAS ACBOptimizer.SetCoeffccient; return Kwmin, Kwmax, K2i, K2e."""
    series = model[:2]
    if series == "70":
        kwmin, kwmax = (.24, .30) if bore <= 35 else (.30, .32)
        k2i, k2e = .35, .35
    elif series == "72":
        kwmin, kwmax = (.24, .31) if bore <= 35 else (.30, .32)
        k2i, k2e = ((.35, .35) if bore <= 25 else (.40, .40)) if alpha in (15, 25) else (.65, .60)
    else:
        if bore > 120:
            raise OptimizationError("RoBAS ACB 73 series has no source bounds for d>120 mm",
                                    "/initial/bore_d_mm")
        kwmin, kwmax = (.25, .32) if bore <= 35 else (.30, .33)
        k2i, k2e = ((.35, .35) if bore <= 25 else (.40, .40)) if alpha in (15, 25) else (.65, .60)
    return kwmin, kwmax, k2i, k2e


def _ball_count(ball: float, pitch: float, material: str) -> int:
    """C# ACBOptimizer.CalcuBallNum truncates the ratio to an int."""
    if material == "engineering_plastic":
        kz = 1.01 + 1.5 / ball if ball <= 15 else 1.11
    else:
        kz = 1.01 + 1.9 / ball if ball <= 15 else 1.134
    return int(math.pi * pitch / (kz * ball))


def _candidate_geometry(initial: dict, dw: float, z: int, dpw: float,
                        k2i: float, k2e: float) -> dict | None:
    """Adapt source single race shoulder values to our 4-sided CAD profile.

    The additional smaller inner-right and larger outer-left shoulders are
    *explicit adapter dimensions*, not dimensions from RoBAS ACBOptimizer.
    """
    d, D, B = (initial[key] for key in (
        "bore_d_mm", "outside_d_mm", "width_mm"))
    alpha = math.radians(initial["contact_angle_deg"])
    cosine, sine = math.cos(alpha), math.sin(alpha)
    ri, ro = .515 * dw, .525 * dw
    di = dpw - 2 * ri + (2 * ri - dw) * cosine
    de = dpw + 2 * ro - (2 * ro - dw) * cosine
    inner_left = di + k2i * dw
    inner_right = inner_left - .15 * dw
    outer_right = de - k2e * dw
    outer_left = outer_right + .15 * dw

    if not (d < inner_right < inner_left < dpw < outer_right < outer_left < D):
        return None
    if dpw * math.sin(math.pi / z) <= dw:
        return None
    # The following three checks are current Bearing_CAD geometric constraints,
    # not an assertion that original RoBAS would use the same B-Rep profile.
    inner_centre_r = dpw / 2 + (ri - dw / 2) * cosine
    outer_centre_r = dpw / 2 - (ro - dw / 2) * cosine
    if inner_centre_r - ri <= d / 2 or outer_centre_r + ro >= D / 2:
        return None
    if max(abs((ri - dw / 2) * sine) + ri,
           abs((ro - dw / 2) * sine) + ro) >= B / 2:
        return None
    if not (inner_centre_r - ri < inner_right / 2 and
            inner_left < dpw and
            dpw < outer_right and outer_left / 2 < outer_centre_r + ro):
        return None

    params = {
        "bore_d_mm": d, "outside_d_mm": D, "width_mm": B,
        "ball_d_mm": dw, "ball_count": z, "pitch_d_mm": dpw,
        "inner_groove_radius_mm": ri, "outer_groove_radius_mm": ro,
        "contact_angle_deg": initial["contact_angle_deg"],
        "cage_material": initial["cage_material"],
        "inner_shoulder_left_d_mm": inner_left,
        "inner_shoulder_right_d_mm": inner_right,
        "outer_shoulder_left_d_mm": outer_left,
        "outer_shoulder_right_d_mm": outer_right,
    }
    design = {
        "schema_version": "bearing-cad.request.v1",
        "bearing_type": BearingType.ANGULAR_CONTACT.value,
        "unit": "mm", "detail_level": "functional",
        "geometry_strategy": "explicit", "parameters": params,
    }
    try:
        parse_request(design)
    except ContractError:
        return None
    return design


def optimize_acb_candidates(*, resources: Path, initial: dict,
                            optimization: dict) -> dict:
    """Return five ranked candidates; never update CAD or claim B-Rep validity."""
    initial = _initial(initial)
    options = _options(optimization)
    root = Path(resources)
    table = root / "Resource" / "BallDB.csv"
    coefficient = root / "Resource" / "球轴承零件相关系数.csv"
    for path in (table, coefficient):
        if path.is_symlink() or not path.is_file():
            raise OptimizationError("Missing original RoBAS CSV: " + path.name)
    try:
        rows = _read(table, ("diameter(mm)",))
    except (ValueError, OSError, UnicodeError) as error:
        raise OptimizationError("Invalid original RoBAS BallDB.csv") from error
    balls = [row["diameter(mm)"] for row in rows]
    if len(balls) < 5 or any(a >= b for a,b in zip(balls, balls[1:])):
        raise OptimizationError("RoBAS BallDB.csv needs five increasing ball diameters")

    d, D, B = (initial[key] for key in (
        "bore_d_mm", "outside_d_mm", "width_mm"))
    alpha = math.radians(initial["contact_angle_deg"])
    cos_alpha, sin_alpha = math.cos(alpha), math.sin(alpha)
    kwmin, kwmax, k2i, k2e = _source_bounds(
        options["model"], d, initial["contact_angle_deg"])
    centre = .5 * (D + d)
    pitch_max = .515 * (D + d)
    dwk = _nearest_diameter(balls, .3 * (D - d))
    count_centre = _ball_count(dwk, centre, initial["cage_material"])
    lower_ball = _nearest_diameter(balls, kwmin * (D - d))
    upper_ball = _nearest_diameter(balls, kwmax * (D - d))
    first = max(0, min(balls.index(dwk)-2, len(balls)-5))
    ball_grid = balls[first:first+5]
    # Actual C# ACB optimizer loops pitch by 0.05 mm to the range boundary.
    count_steps = min(4096, int(math.floor((pitch_max-centre)/.05 + 1e-8)) + 1)
    request_id = sha256(json.dumps(
        {"initial":initial,"optimization":options},
        sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode("utf-8")).hexdigest()
    candidates = []
    for ball in ball_grid:
        if not lower_ball <= ball <= upper_ball:
            continue
        for z in range(count_centre-2, count_centre+3):
            if not 2 <= z <= 64 or z > _ball_count(ball, pitch_max, initial["cage_material"]):
                continue
            for n in range(count_steps):
                pitch = centre + .05*n
                if pitch > pitch_max + 1e-9:
                    continue
                cad_design = _candidate_geometry(initial, ball, z, pitch, k2i, k2e)
                if cad_design is None:
                    continue
                gamma = original_dotnet_math_round(ball*cos_alpha/pitch, 2)
                fc, fo, matched = _coefficients(root, gamma)
                if not matched or not (fc > 0 and fo > 0):
                    continue
                beta = math.atan(sin_alpha/(cos_alpha + ball/pitch))
                spin_ratio = (1-ball*cos_alpha/pitch)*math.tan(alpha-beta) + (ball/pitch)*sin_alpha
                cr = (1.3*fc*cos_alpha**.7 * z**(2./3.) *
                      (ball**1.8 if ball<=25.4 else 3.647*ball**1.4))
                cor = fo*z*ball**2*cos_alpha
                ka = 3.43*(z*z*ball*sin_alpha**5)**(1./3.)*options["preload_n"]**(1./3.)
                if not all(math.isfinite(v) and v>0 for v in (spin_ratio,cr,cor,ka)):
                    continue
                cid = sha256((request_id+json.dumps(cad_design["parameters"],
                               sort_keys=True)).encode("utf-8")).hexdigest()[:16]
                candidates.append({
                    "candidate_id": cid, "design": cad_design,
                    "metrics": {
                        "spin_ratio": spin_ratio, "axial_stiffness_source_units": ka,
                        "dynamic_load_n": cr, "static_load_n": cor,
                    },
                    "coefficient_lookup": {
                        "gamma": gamma, "fc": fc, "fo": fo,
                        "csv_file": coefficient.name,
                    },
                    "source_geometry": {
                        "inner_groove_d_mm": pitch-2*.515*ball+(2*.515-1)*ball*cos_alpha,
                        "outer_groove_d_mm": pitch+2*.525*ball-(2*.525-1)*ball*cos_alpha,
                        "adapter_shoulder_offset_ratio_dw": .15,
                    },
                })
    if not candidates:
        raise OptimizationError(
            "No ACB candidate satisfies RoBAS search bounds, source coefficients "
            "and current CAD geometry constraints")
    by_spin = _normalize([x["metrics"]["spin_ratio"] for x in candidates])
    by_ka = _normalize([x["metrics"]["axial_stiffness_source_units"] for x in candidates])
    by_cr = _normalize([x["metrics"]["dynamic_load_n"] for x in candidates])
    weights = options["weights"]
    for i,row in enumerate(candidates):
        row["score"] = (weights["spin_ratio"]*by_spin[i] +
                        weights["axial_stiffness"]*by_ka[i] +
                        weights["dynamic_load"]*by_cr[i])
    candidates.sort(key=lambda x:(-x["score"],x["candidate_id"]))
    selected = candidates[:_MAX_RESULTS]
    for rank,row in enumerate(selected,1):
        row["rank"] = rank
    return {
        "schema_version": "bearing-cad.robas-acb-optimization.v1",
        "candidate_only": True, "applied": False,
        "bearing_type": initial["bearing_type"],
        "source_initial_hash": request_id,
        "source_model": options["model"],
        "optimization": options,
        "total_valid_candidates": len(candidates),
        "candidates": selected,
        "source_basis": [
            "RoBAS ACBOptimizer.Optimizer, SetCoeffccient and CalcuBallNum",
            "RoBAS ACBOptimizer.CalcuSpinRatio and CalcuAxialStiffness",
            "RoBAS ACBOptimizer.CalcuDynamicLoad and CalcuRadialStaticLoad",
            "RoBAS Resource/BallDB.csv and 球轴承零件相关系数.csv",
        ],
        "warnings": [
            "SOURCE_ACB_MODEL_CATALOG_EMPTY_NO_MODEL_DIMENSION_CERTIFICATION",
            "SOURCE_OPTIMIZER_MAXIMIZES_SPIN_RATIO_ENGINEERING_DIRECTION_UNREVIEWED",
            "ACB_CAD_REQUIRES_EXTRA_ASYMMETRIC_SHOULDER_ADAPTER_NOT_SOURCE_EXACT",
            "CANDIDATE_ONLY_NOT_BREP_VERIFIED_NOT_MANUFACTURING_APPROVED",
            "SOURCE_ACCURACY_CLASS_RECORDED_NOT_APPLIED_TO_OPTIMIZATION_OBJECTIVES",
        ],
    }

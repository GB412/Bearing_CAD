"""7-case RoBAS-to-OCCT geometry evidence baseline (not Eyeshot equivalence).

Read explicit regression cases, build existing STEP bundles, and summarize
B-Rep measurements. The original commercial Eyeshot solids are unavailable;
legacy geometry fields MUST remain UNVERIFIED without real reference files.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cadquery as cq

from .artifacts import generate_bundle, verify_bundle
from .contracts import parse_request

CASES_FILE = Path(__file__).resolve().parent.parent / "tests_v2" / "fixtures" / "robas_3d_cases.json"
REPORT_SCHEMA = "bearing-cad.robas-comparison.v1"
UNKNOWN_REFERENCE = "NOT_AVAILABLE"
UNVERIFIED = "UNVERIFIED"


def load_fixtures(path: Path = CASES_FILE) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (data.get("schema_version") != "bearing-cad.migration-cases.v1"
            or data.get("reference_step_status") != UNKNOWN_REFERENCE
            or data.get("measurement_unit") != "mm"):
        raise ValueError("Unexpected or unsupported migration fixture metadata")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Migration cases must be a nonempty list")
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)) or any(not cid.replace("_", "").isalnum() for cid in ids):
        raise ValueError("Invalid or duplicate benchmark case ID")
    for case in cases:
        if not case.get("legacy_source_refs") or not case.get("legacy_call_path"):
            raise ValueError("Every case needs explicitly cited legacy source paths")
        parse_request(case["request"])
    return data


def analytic_legacy_probe(case: dict) -> dict:
    """Only simple source-level equations, never a fabricated Eyeshot metric."""
    request = case["request"]
    params = request["parameters"]
    if request["bearing_type"] == "rolling.deep_groove_ball":
        d, D, ball = params["bore_d_mm"], params["outside_d_mm"], params["ball_d_mm"]
        geometry_pitch, scalar_pitch = (d + D) / 2, d
        def legacy_count(pitch):
            return int(186 / math.degrees(2 * math.asin(ball / pitch))) + 1
        return {
            "legacy_geometry_constructor_pitch_d_mm": geometry_pitch,
            "legacy_scalar_constructor_pitch_d_mm": scalar_pitch,
            "legacy_geometry_count_expression": legacy_count(geometry_pitch),
            "legacy_scalar_count_expression": legacy_count(scalar_pitch),
            "legacy_geometry_inner_outer_groove_radius_mm": [0.51 * ball, 0.53 * ball],
            "legacy_scalar_inner_outer_groove_radius_mm": [0.52 * ball, 0.54 * ball],
            "python_explicit_pitch_d_mm": params["pitch_d_mm"],
            "python_explicit_inner_outer_groove_radius_mm": [
                params["inner_groove_radius_mm"], params["outer_groove_radius_mm"]
            ],
            "caution": "Two C# constructors differ; these are analytic probes, not Eyeshot solids."
        }
    if request["bearing_type"] == "rolling.angular_contact_ball":
        degrees = params["contact_angle_deg"]
        return {
            "passed_angle_numeric": degrees,
            "legacy_raw_MathCos_of_numeric": math.cos(degrees),
            "legacy_deg_to_rad_MathCos": math.cos(math.radians(degrees)),
            "caution": "Old C# call paths have angle-unit ambiguity and 3-degree tapered race faces."
        }
    return {
        "python_configuration": params["configuration"],
        "caution": "NUP detachable ring is a deliberate new part; no original Eyeshot reference solid."
    }


def evaluate_case(case: dict, root: Path) -> dict:
    """Run the real CAD builder/STEP verifier and reject mismatched expectations."""
    request = parse_request(case["request"])
    folder = generate_bundle(request, root / "bundles")
    manifest = verify_bundle(folder)
    quality = json.loads((folder / "geometry_quality.json").read_text(encoding="utf-8"))
    expected = case["expected"]

    part_ids = [part["id"] for part in manifest["parts"]]
    instances = manifest["instances"]
    if part_ids != expected["component_ids"] or len(instances) != expected["instance_count"]:
        raise AssertionError(f"{case['case_id']}: component identity/instance count mismatch")
    if manifest["request_hash"] != request.request_hash or manifest["geometry_unit"] != "mm":
        raise AssertionError(f"{case['case_id']}: request hash or unit mismatch")
    if quality["instance_count"] != len(instances) or quality["component_count"] != len(part_ids):
        raise AssertionError(f"{case['case_id']}: quality report does not match manifest")
    if quality["step_roundtrip"]["solid_count"] != len(instances):
        raise AssertionError(f"{case['case_id']}: STEP solid count mismatch")

    rolling_name = expected["rolling_component_id"]
    rollers = [inst for inst in instances if inst["part_id"] == rolling_name]
    count = expected["rolling_count"]
    if len(rollers) != count:
        raise AssertionError(f"{case['case_id']}: rolling element count mismatch")
    pitch_radius = request.parameters["pitch_d_mm"] / 2
    maximum_radial_error = 0.0
    maximum_phase_error_mm = 0.0
    for index, inst in enumerate(rollers):
        x, y, z = inst["translation_mm"]
        theoretical_x = pitch_radius * math.cos(2 * math.pi * index / count)
        theoretical_y = pitch_radius * math.sin(2 * math.pi * index / count)
        maximum_radial_error = max(maximum_radial_error,
                                   abs(math.hypot(x, y) - pitch_radius), abs(z))
        maximum_phase_error_mm = max(maximum_phase_error_mm,
                                     math.hypot(x-theoretical_x, y-theoretical_y))
    if max(maximum_radial_error, maximum_phase_error_mm) > 1e-6:
        raise AssertionError(f"{case['case_id']}: pitch circle or phase mismatch")

    if request.cage and request.cage.kind == "stamping_double_half":
        rivets = [inst for inst in instances if inst["part_id"] == "rivet"]
        if len(rivets) != count:
            raise AssertionError(f"{case['case_id']}: rivet count mismatch")
        for index, inst in enumerate(rivets):
            x, y, z = inst["translation_mm"]
            theta = (index + .5) * 2 * math.pi / count
            if math.dist((x, y, z), (pitch_radius*math.cos(theta),
                                      pitch_radius*math.sin(theta), 0)) > 1e-6:
                raise AssertionError(f"{case['case_id']}: rivet pitch phase mismatch")

    source_bounds = quality["step_roundtrip"]["source_bounds_mm"]
    observed_d = max(source_bounds[1] - source_bounds[0],
                     source_bounds[3] - source_bounds[2])
    observed_b = source_bounds[5] - source_bounds[4]
    if (abs(observed_d - request.parameters["outside_d_mm"]) > 1e-3
            or abs(observed_b - request.parameters["width_mm"]) > 1e-3):
        raise AssertionError(f"{case['case_id']}: overall envelope disagrees with input")

    return {
        "case_id": case["case_id"],
        "bearing_type": request.bearing_type.value,
        "request_hash": request.request_hash,
        "artifact_key": manifest["artifact_key"],
        "cadquery_version": manifest["cadquery_version"],
        "generator_version": manifest["generator_version"],
        "legacy_call_path": case["legacy_call_path"],
        "legacy_source_refs": case["legacy_source_refs"],
        "legacy_analytic_probe": analytic_legacy_probe(case),
        "legacy_step_status": UNKNOWN_REFERENCE,
        "legacy_step_metrics": None,
        "solid_equivalence_status": UNVERIFIED,
        "python_measurements": {
            "component_ids": part_ids,
            "component_count": quality["component_count"],
            "instance_count": len(instances),
            "component_metrics": quality["component_metrics"],
            "assembly_bounds_mm": source_bounds,
            "rolling_element_count": count,
            "rolling_pitch_radius_mm": pitch_radius,
            "max_pitch_circle_radial_error_mm": maximum_radial_error,
            "max_rolling_phase_error_mm": maximum_phase_error_mm,
            "step_roundtrip": quality["step_roundtrip"],
        },
    }


def run_baseline(cases_path: Path, output_root: Path) -> dict:
    fixtures = load_fixtures(cases_path)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    measured = [evaluate_case(case, output_root) for case in fixtures["cases"]]
    report = {
        "report_schema": REPORT_SCHEMA,
        "result": "OCCT_BASELINE_COMPLETE_EYESHOT_UNVERIFIED",
        "legacy_source_archive_sha256": fixtures["legacy_source_archive_sha256"],
        "unit": "mm",
        "case_count": len(measured),
        "eyeshoot_reference_step_files_provided": False,
        "cases": measured,
        "limitations": [
            "RoBAS C# source equations are not equivalent to actual Eyeshot B-Rep measurements",
            "STEP interchange tolerance is not a legacy equivalence tolerance",
            "Geometric validity does not certify load capacity, tolerances, or manufacture",
        ],
    }
    (output_root / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8"
    )
    rows = [
        "# 3D-MIG-07A · RoBAS / Bearing_CAD 三维对照基线",
        "",
        "这份报告由当前 CadQuery/OCCT 实测生成。RoBAS Eyeshot 原版 STEP 未提供，"
        "**不包含新旧实体等价性结论**。",
        "",
        "| 案例 | 轴承 | 零件原型 | 实例 | STEP 体积差最大值 | 原版实体 | 几何等价性 |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for record in measured:
        m = record["python_measurements"]
        rows.append("| {cid} | {kind} | {parts} | {instances} | {diff:.6%} | {legacy} | {eq} |".format(
            cid=record["case_id"], kind=record["bearing_type"],
            parts=m["component_count"], instances=m["instance_count"],
            diff=m["step_roundtrip"]["worst_relative_solid_volume_error"],
            legacy=record["legacy_step_status"], eq=record["solid_equivalence_status"]
        ))
    rows += ["", "RoBAS 路径、解析公式差异、组件体积、装配包围盒及哈希等详见 `comparison.json`。",
             "这不是制造级验收，也不是 RoBAS 与 OCCT 实体等价证明。", ""]
    (output_root / "comparison.md").write_text("\n".join(rows), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a seven-case RoBAS/OCCT 3D evidence baseline")
    parser.add_argument("--cases", type=Path, default=CASES_FILE, help="Committed explicit JSON cases")
    parser.add_argument("--output", type=Path, required=True, help="Report output directory")
    args = parser.parse_args()
    result = run_baseline(args.cases, args.output)
    print(f"3D-MIG-07A: {result['case_count']} OCCT baseline cases, Eyeshot solids UNVERIFIED")


if __name__ == "__main__":
    main()

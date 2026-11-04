"""RoBAS CSV-based initial geometry suggestions (not approved design)."""
from __future__ import annotations
import csv
import hashlib
import math
from pathlib import Path

_BEARINGS = {"rolling.deep_groove_ball", "rolling.angular_contact_ball", "rolling.cylindrical_roller"}

def _read(path: Path, keys: tuple[str, ...]) -> list[dict[str, float]]:
    if not path.is_file():
        raise ValueError(f"RoBAS reference table missing: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        if not rows.fieldnames or not set(keys).issubset(rows.fieldnames):
            raise ValueError(f"Invalid reference columns: {path.name}")
        data = []
        for row in rows:
            numbers = {key: float(row[key]) for key in keys}
            if any(not math.isfinite(x) or x <= 0 for x in numbers.values()):
                raise ValueError(f"Invalid reference value: {path.name}")
            data.append(numbers)
            if len(data) > 3000:
                raise ValueError("Reference table too long")
        if not data:
            raise ValueError(f"Empty reference table: {path.name}")
        return data

def _nearest(target: float, values: list[float]) -> float:
    # Same relative error criterion as BaseOptimizer.DetermineRollerDiameter,
    # but always return a real table entry (the legacy fallback could return
    # the unlisted raw target when the first table row was closest).
    return min(values, key=lambda candidate: abs(1 - target / candidate))


def dgb_radial_clearance_mm(bore_d_mm: float) -> float | None:
    """RoBAS DGBOptimizer.CalcuRadialClearance; integer arithmetic, mm output."""
    if type(bore_d_mm) not in (int, float) or not math.isfinite(bore_d_mm) or bore_d_mm <= 0:
        raise ValueError("Bore must be a positive finite mm dimension")
    for lower, upper, raw in (
        (10, 18, (4, 11)), (18, 30, (5, 12)),
        (30, 50, (9, 17)), (50, 80, (12, 22)),
        (80, 120, (18, 30)), (120, 160, (24, 38)),
        (160, 180, (30, 45)), (180, 200, (36, 53)),
    ):
        if lower <= bore_d_mm < upper:
            return ((raw[0] + raw[1]) // 2) / 1000
    return None


def dgb_geometry_profile(*, bore_d_mm: float, outside_d_mm: float,
                         width_mm: float, tables_dir: str | Path) -> dict:
    """Reproduce the RoBAS DGBGeometry constructor as an explicit CAD preset.

    This is a source-backed initial geometry path, not DGBOptimizer.Optimizer,
    not the conflicting DeepGrooveBallBearing scalar constructor, and not an
    approved bearing design.
    """
    initial = preliminary_sizes(
        bearing_type="rolling.deep_groove_ball",
        bore_d_mm=bore_d_mm, outside_d_mm=outside_d_mm,
        width_mm=width_mm, tables_dir=tables_dir,
    )
    ball = initial["ball_or_roller_d_mm"]
    pitch = initial["pitch_d_mm"]
    if not 0 < ball < pitch:
        raise ValueError("RoBAS DGB geometry requires 0 < ball diameter < pitch diameter")

    # DGBGeometry.cs:58; 186 degrees is an empirical selection heuristic.
    count = math.trunc(186 / math.degrees(2 * math.asin(ball / pitch))) + 1
    if (not 1 <= count <= 64 or
            (count > 1 and pitch * math.sin(math.pi / count) <= ball)):
        raise ValueError("RoBAS DGB empirical ball count exceeds CAD limits or causes ball overlap")

    # DGBOptimizer.CalcuRadialClearance uses integer literals in C#.
    radial_clearance = dgb_radial_clearance_mm(bore_d_mm)
    if radial_clearance is None:
        raise ValueError(
            "RoBAS DGB radial-clearance table is undefined for this bore; "
            "the original zero fallback is not accepted as a design value"
        )

    sidewall_factor = 0.35 if bore_d_mm <= 25 else 0.40
    inner_groove_radius = 0.51 * ball
    outer_groove_radius = 0.53 * ball
    inner_groove_diameter = pitch - ball
    outer_groove_diameter = pitch + ball + radial_clearance
    inner_shoulder = inner_groove_diameter + sidewall_factor * ball
    outer_shoulder = outer_groove_diameter - sidewall_factor * ball

    if not (bore_d_mm < inner_shoulder < pitch < outer_shoulder < outside_d_mm):
        raise ValueError("RoBAS DGBGeometry shoulder equations do not fit the supplied envelope")
    if (pitch / 2 - inner_groove_radius <= bore_d_mm / 2 or
            pitch / 2 + outer_groove_radius >= outside_d_mm / 2):
        raise ValueError("RoBAS DGB raceway cuts through the bore or outside envelope")

    # These are DGBGeometry cageOutDia/cageInDia/cageWidth properties.
    # They are only offered for the simplified annular CAD cage; they are NOT
    # the StampingCage board-thickness, rivet, or pocket manufacturing inputs.
    cage_inner = 1.02 * inner_shoulder
    cage_outside = 0.98 * outer_shoulder
    cage_width = 0.95 * width_mm
    if not (inner_shoulder < cage_inner < cage_outside < outer_shoulder):
        raise ValueError("RoBAS DGBGeometry cage envelope does not fit between race shoulders")

    return {
        "schema_version": "bearing-cad.robas-dgb-geometry.v1",
        "bearing_type": "rolling.deep_groove_ball",
        "method": "RoBAS DGBGeometry(outsideDia, insideDia, width)",
        "candidate_only": True,
        "units": "mm",
        "parameters": {
            "bore_d_mm": float(bore_d_mm),
            "outside_d_mm": float(outside_d_mm),
            "width_mm": float(width_mm),
            "ball_d_mm": ball,
            "pitch_d_mm": pitch,
            "ball_count": count,
            "inner_groove_radius_mm": inner_groove_radius,
            "outer_groove_radius_mm": outer_groove_radius,
            "inner_shoulder_d_mm": inner_shoulder,
            "outer_shoulder_d_mm": outer_shoulder,
        },
        "intermediate": {
            "radial_clearance_mm": radial_clearance,
            "sidewall_factor": sidewall_factor,
            "inner_groove_d_mm": inner_groove_diameter,
            "outer_groove_d_mm": outer_groove_diameter,
        },
        "simplified_cage_dimensions": {
            "inner_d_mm": cage_inner,
            "outside_d_mm": cage_outside,
            "width_mm": cage_width,
        },
        "source_files": initial["source_files"],
        "legacy_source_archive_sha256": "69b39ec937bcc942d223601995c7279573c629d81c652e56a3146b4f2c95d23d",
        "source_refs": [
            "RoBAS/Core/BaseOptimizer.cs:27-49",
            "RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:53-92",
            "RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBOptimizer.cs:566-604",
        ],
        "warnings": [
            "候选初始几何，不是 DGBOptimizer.Optimizer 的搜索/评价结果。",
            "186° 球数规则是原版经验式；源码未给出其推导，不能视为最优球数或承载校核。",
            "原版 BaseOptimizer 在首个 CSV 项恰为最近项时可能返回未收录的原始目标值；本实现始终返回实际 CSV 表项。",
            "简化保持架尺寸来自 DGBGeometry 的 Cage* 属性；不代表 StampingCage 的板厚、球兜、铆钉或制造参数。",
            "简化保持架球兜间隙不是原版 DGBGeometry 参数，仍由用户显式提供。",
            "未采用 DeepGrooveBallBearing(string,...) 的另一套节圆/曲率构造路径。",
        ],
    }

def preliminary_sizes(*, bearing_type: str, bore_d_mm: float, outside_d_mm: float,
                      width_mm: float, tables_dir: str | Path) -> dict:
    if bearing_type not in _BEARINGS:
        raise ValueError("Unsupported bearing type")
    dimensions = (bore_d_mm, outside_d_mm, width_mm)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in dimensions):
        raise ValueError("Dimensions must be positive finite mm")
    if bore_d_mm >= outside_d_mm:
        raise ValueError("Bore must be smaller than outside")
    root = Path(tables_dir)
    is_roller = bearing_type == "rolling.cylindrical_roller"
    source = root / ("CylinderRollerDiameterDB.csv" if is_roller else "BallDB.csv")
    column = "Dw" if is_roller else "diameter(mm)"
    diameter = _nearest(.3 * (outside_d_mm-bore_d_mm), [r[column] for r in _read(source, (column,))])
    pitch = (outside_d_mm + bore_d_mm) / 2
    if diameter >= pitch:
        raise ValueError("Selected rolling element larger than pitch")
    result = {
        "bearing_type": bearing_type, "candidate_only": True, "units": "mm",
        "ball_or_roller_d_mm": diameter, "pitch_d_mm": pitch,
        "source_files": {source.name: hashlib.sha256(source.read_bytes()).hexdigest()},
        "warnings": ["RoBAS initial geometry heuristic, not approved design",
                     "Determine shoulders, raceways, cage and counts before CAD",
                     "Do not interpret suggestions as solver-validated parameters"],
    }
    if is_roller:
        length_file = root / "CylinderRollerDB.csv"
        rows = _read(length_file, ("Dw", "Lw"))
        lengths = [row["Lw"] for row in rows if abs(row["Dw"]-diameter) < 1e-7]
        if not lengths:
            raise ValueError("No length choices for selected roller diameter")
        ratio = .60 if outside_d_mm <= 60 else .73 if outside_d_mm < 200 else .75
        result["roller_length_mm"] = _nearest(ratio*width_mm, lengths)
        kz = 1.35 if diameter <= 6 else 1.225 if diameter < 50 else 1.3
        count = max(1, math.floor(math.pi*pitch/(kz*diameter)))
        while count > 1 and pitch*math.sin(math.pi/count) <= diameter:
            count -= 1
        result["preliminary_roller_count"] = count
        result["source_files"][length_file.name] = hashlib.sha256(length_file.read_bytes()).hexdigest()
    else:
        result["warnings"].append("RoBAS's unexplained 186-degree ball-count formula is not auto-applied")
    return result

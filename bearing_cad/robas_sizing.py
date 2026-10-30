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

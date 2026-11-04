"""Source-backed RoBAS StampingCage candidate-to-CAD parameter adapter.

C# source: RoBAS/BearingModel/Cage/StampingCage.cs. This computes original
constructor values then explicitly *adapts* its radial Width into separate
CAD annulus diameters and axial height; it is not a manufacturing approval.
"""
from __future__ import annotations

import math
import re

_STANDARD_BOARD_MM = (0.5, 0.7, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5)
# StampingCage.DetermineRivetHoleDiameter / DetermineRivetTopDiameter:
_RIVET_BY_BOARD_MM = {
    0.5: (0.8, 1.2), 0.7: (1.0, 1.6), 1.0: (1.2, 1.9),
    1.2: (1.5, 2.4), 1.5: (2.5, 4.0), 2.0: (3.0, 5.6),
    2.5: (3.5, 5.6), 3.0: (4.0, 6.4), 3.5: (4.0, 6.4),
}


def _positive(value, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1000:
        raise ValueError(f"{name} must be a finite positive dimension <= 1000 mm")
    return float(value)


def robas_stamping_profile(
    *, bearing_model: str, ball_d_mm: float, pitch_d_mm: float,
    ball_count: int, bearing_width_mm: float,
    inner_shoulder_d_mm: float, outer_shoulder_d_mm: float,
    rivet_hole_clearance_mm: float,
) -> dict:
    """Map StampingCage's source constructor to an explicit existing CAD cage.

    RoBAS Width is radial annulus band thickness (diameters Dpw ± Width), not
    the axial total width bearing-cad.request.v1 uses as cage.width_mm. The latter must be computed
    as 2 * (SphereRadius + BoardThickness) to match Draw3DCage.
    """
    if type(bearing_model) is not str or not re.fullmatch(r"(60|62|63)[0-9]{2,4}[A-Z0-9-]{0,8}", bearing_model):
        raise ValueError("bearing_model must identify a RoBAS 60/62/63 series")
    dw = _positive(ball_d_mm, "ball_d_mm")
    pitch = _positive(pitch_d_mm, "pitch_d_mm")
    axial_b = _positive(bearing_width_mm, "bearing_width_mm")
    inner_shoulder = _positive(inner_shoulder_d_mm, "inner_shoulder_d_mm")
    outer_shoulder = _positive(outer_shoulder_d_mm, "outer_shoulder_d_mm")
    hole_clearance = _positive(rivet_hole_clearance_mm, "rivet_hole_clearance_mm")
    if type(ball_count) is not int or not 2 <= ball_count <= 64:
        raise ValueError("ball_count must be an integer between 2 and 64")
    family = bearing_model[:2]
    if ((family == "60" and not 4 < dw <= 35)
            or (family == "62" and not 4 < dw <= 45)
            or (family == "63" and not 5 < dw < 55)):
        raise ValueError("RoBAS CalculateBoardThickness is not defined for this series/ball diameter")
    if family == "60":
        nominal_s = math.sqrt(dw / 3.174 + 1.25 ** 2) - 1.25
    elif family == "62":
        nominal_s = math.sqrt(dw / 6.3 - 0.5) - 0.04
    else:
        nominal_s = math.sqrt(dw / 8.5 - 0.5) + (0.15 if dw <= 45 else 0.4)

    # The C# loop retains the earlier standard on an exact tie.
    board_s = min(_STANDARD_BOARD_MM, key=lambda s: abs(s - nominal_s))
    hole_d, head_d = _RIVET_BY_BOARD_MM[board_s]
    radial_w = (0.48 if family == "60" and dw > 20 else 0.45) * dw
    sphere_r = 0.55 * dw
    axial_half_height = sphere_r + board_s
    cage_inner, cage_outer = pitch - radial_w, pitch + radial_w
    axial_total = 2 * axial_half_height

    if not (0 < dw < pitch and
            inner_shoulder < cage_inner < pitch < cage_outer < outer_shoulder):
        raise ValueError("RoBAS stamped cage does not fit the supplied ring shoulders")
    if axial_total > axial_b:
        raise ValueError("RoBAS stamped cage axial envelope exceeds bearing width")
    if hole_d + 2 * hole_clearance >= head_d:
        raise ValueError("CAD-only rivet hole clearance leaves no retained rivet head")
    if pitch * math.sin(math.pi / (2 * ball_count)) <= (
            sphere_r + head_d / 2):
        raise ValueError("RoBAS ball-to-rivet spacing is too small for the derived cup and head")

    # StampingCage.determineTravel has an exact Dw=6 gap: leave that
    # parameter unfilled rather than silently treating zero as a design.
    if dw == 6:
        travel = None
    elif dw < 6:
        travel = 0.03
    elif dw <= 10:
        travel = 0.04
    elif dw <= 14:
        travel = 0.05
    elif dw <= 18:
        travel = 0.06
    elif dw <= 24:
        travel = 0.07
    elif dw <= 32:
        travel = 0.09
    elif dw <= 40:
        travel = 0.10
    else:
        travel = 0.12
    flat_r = (
        pitch * math.sin(math.pi / (2 * ball_count))
        - math.sqrt((dw / 2 + board_s) ** 2 - board_s ** 2)
        - head_d / 2 - 0.3
    )
    if flat_r <= 0:
        raise ValueError("RoBAS flat-to-sphere radius is not positive for this cage")

    cad_cage = {
        "kind": "stamping_double_half",
        "inner_d_mm": cage_inner,
        "outside_d_mm": cage_outer,
        "width_mm": axial_total,
        "pocket_clearance_mm": sphere_r - dw / 2,
        "board_thickness_mm": board_s,
        "rivet_shaft_d_mm": hole_d,
        "rivet_head_d_mm": head_d,
        "rivet_hole_clearance_mm": hole_clearance,
    }
    return {
        "schema_version": "bearing-cad.robas-stamping-adapter.v1",
        "candidate_only": True,
        "method": "RoBAS StampingCage(ballDia,pitchDia,ballNum,bearingModel)",
        "units": "mm",
        "bearing_model": bearing_model,
        "cad_cage": cad_cage,
        "source_dimensions": {
            "width_radial_mm": radial_w,
            "board_thickness_mm": board_s,
            "sphere_radius_mm": sphere_r,
            "pocket_depth_mm": dw / 2 + travel if travel is not None else None,
            "rivet_hole_d_mm": hole_d,
            "rivet_head_d_mm": head_d,
            "half_cage_axial_height_mm": axial_half_height,
            "flat_to_sphere_radius_mm": flat_r,
            "pocket_to_pocket_mm": pitch * math.sin(math.pi / ball_count),
            "pocket_to_rivet_mm": pitch * math.sin(math.pi / (2 * ball_count)),
        },
        "source_refs": [
            "RoBAS/BearingModel/Cage/StampingCage.cs:166-188",
            "RoBAS/BearingModel/Cage/StampingCage.cs:226-299",
            "RoBAS/BearingModel/Cage/StampingCage.cs:324-409",
            "RoBAS/BearingModel/Cage/StampingCage.cs:501-620",
        ],
        "warnings": [
            "原版 Width 对应径向环带厚度（内外直径为 Dpw±Width），不是 CAD 的轴向总宽度。",
            "CAD 使用当前显式参数双半笼构造器；铆钉孔净距为调用方显式 CAD 余量，不是原版给定值。",
            "原版 Draw3DCage 用 rivetHoleDiameter 作为铆钉圆柱直径；本转换按此处理，不把它当作独立钻孔公差。",
            "保留原版计算公式，但当前 OCCT 球面布尔和铆钉孔处理不等于已验证 Eyeshot 实体逐点等价。",
            "仅几何候选，不是承载性能、冲压工艺或制造批准。",
        ] + (["原版在 Dw=6 mm 的兜孔径向游动量分支未赋值；PocketDepth 置空。"]
             if travel is None else []),
    }

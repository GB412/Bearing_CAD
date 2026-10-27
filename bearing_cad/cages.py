"""RoBAS CylinderPocketCage-inspired annulus with Z axial cylindrical windows.

This ports the recognizable C# boolean construction, not its unaudited
dimension optimizer (RoBAS/CylinderPocketCage.cs:124-160).
"""
from __future__ import annotations

import math

from .contracts import CageSpec, ContractError
from .geometry import annulus, cylindrical_roller, circular_positions
from .geometry_checks import inspect_solid


def cylindrical_window_cage(
    spec: CageSpec, *, pitch_d_mm: float, roller_d_mm: float,
    roller_length_mm: float, roller_count: int, bearing_width_mm: float,
    inner_rib_tip_d_mm: float, outer_rib_tip_d_mm: float,
):
    """Cut exactly roller_count centered axial windows; widths in mm.

    pocket_clearance_mm is a CAD construction allowance applied radially AND
    axially, not a validated manufacturing tolerance.
    """
    if spec.kind != "cylindrical_window":
        raise ContractError("NOT_SUPPORTED", "/cage/kind", "Expected cylindrical_window cage")
    if not (inner_rib_tip_d_mm < spec.inner_d_mm < pitch_d_mm <
            spec.outside_d_mm < outer_rib_tip_d_mm):
        raise ContractError("PARAMETER_INVALID", "/cage",
                            "Cage must straddle the roller pitch circle between flange tips")
    if spec.width_mm > bearing_width_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm",
                            "Cage exceeds bearing axial envelope")
    window_d = roller_d_mm + 2 * spec.pocket_clearance_mm
    window_length = roller_length_mm + 2 * spec.pocket_clearance_mm
    if window_length >= spec.width_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm",
                            "Windows would open through both axial rim faces")
    if roller_count > 1 and window_d >= pitch_d_mm * math.sin(math.pi / roller_count):
        raise ContractError("PARAMETER_INVALID", "/cage/pocket_clearance_mm",
                            "Adjacent roller windows intersect")
    # A shared cutter is translated to the exact same pitch centers as rollers.
    shell = annulus(spec.inner_d_mm, spec.outside_d_mm, spec.width_mm)
    pocket = cylindrical_roller(window_d, window_length)
    blank_volume = shell.val().Volume()
    for centre in circular_positions(pitch_d_mm, roller_count):
        shell = shell.cut(pocket.translate(centre))
    if not inspect_solid(shell).valid or shell.val().Volume() >= blank_volume:
        raise ContractError("BREP_INVALID", "/cage",
                            "Cylinder window cutting invalid or disconnected")
    return shell


def straight_pocket_cage(
    spec: CageSpec, *, pitch_d_mm: float, ball_d_mm: float,
    ball_count: int, bearing_width_mm: float,
    max_inner_shoulder_d_mm: float, min_outer_shoulder_d_mm: float,
):
    """RoBAS StraightPocketCage-inspired ring with Z radial cylinders.

    The cutter is a cylinder whose axis passes along the radial direction at
    each ball pitch angle, *not* a Z-axis cylinder (unlike cylindrical rollers).
    A single explicit allowance replaces unaudited 1.004*Dw+0.12 defaults.
    """
    import cadquery as cq
    if spec.kind != "straight_pocket":
        raise ContractError("NOT_SUPPORTED", "/cage/kind", "Expected straight_pocket cage")
    if not (max_inner_shoulder_d_mm < spec.inner_d_mm < pitch_d_mm <
            spec.outside_d_mm < min_outer_shoulder_d_mm):
        raise ContractError("PARAMETER_INVALID", "/cage",
                            "Cage must straddle pitch diameter between inner and outer shoulders")
    if spec.width_mm > bearing_width_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm", "Cage exceeds bearing width")
    window_d = ball_d_mm + 2 * spec.pocket_clearance_mm
    if window_d >= spec.width_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm",
                            "Radial windows would pierce axial rim faces")
    if window_d <= max(pitch_d_mm - spec.inner_d_mm,
                       spec.outside_d_mm - pitch_d_mm):
        raise ContractError("PARAMETER_INVALID", "/cage",
                            "Radial window does not cross entire cage wall")
    if ball_count > 1 and window_d >= pitch_d_mm * math.sin(math.pi / ball_count):
        raise ContractError("PARAMETER_INVALID", "/cage",
                            "Adjacent radial windows intersect")

    cage = annulus(spec.inner_d_mm, spec.outside_d_mm, spec.width_mm)
    blank_volume = cage.val().Volume()
    # RoBAS StraightPocketCage.cs:346-357 uses Y-axis cylinders; fix original
    # i <= pocketNum duplicate 360° cut by doing exactly range(ball_count).
    cutter = cq.Solid.makeCylinder(
        window_d / 2, window_d,
        cq.Vector(0, (pitch_d_mm - window_d) / 2, 0),
        cq.Vector(0, 1, 0),
    )
    for index in range(ball_count):
        angle = index * 360 / ball_count
        cage = cage.cut(cutter.rotate((0, 0, 0), (0, 0, 1), angle))
    if not inspect_solid(cage).valid or cage.val().Volume() >= blank_volume:
        raise ContractError("BREP_INVALID", "/cage", "Radial windows invalid or did not remove material")
    return cage

"""Deep-groove ball bearing exact B-Rep (cage intentionally omitted).

RoBAS references: DGBGeometry; SingleRowDeepGrooveInnerRace and
SingleRowDeepGrooveOuterRace; BallRoller. Only the independent geometric
construction method is migrated; no unaudited empirical dimensions inferred.
"""
from __future__ import annotations

import math
import cadquery as cq

from .contracts import (
    AssemblyModel, BearingType, BearingRequest,
    ComponentDefinition, ComponentInstance, ContractError,
)
from .geometry import annulus, sphere, circular_positions
from .geometry_checks import inspect_solid, interference_volume


def build_deep_groove(request: BearingRequest) -> AssemblyModel:
    """Use explicit shoulder, raceway and ball parameters in mm."""
    if request.bearing_type != BearingType.DEEP_GROOVE:
        raise ContractError("NOT_SUPPORTED", "/bearing_type", "Expected deep-groove ball bearing")
    p = request.parameters
    d, D, B = (p["bore_d_mm"], p["outside_d_mm"], p["width_mm"])
    pitch, ball_d, count = (p["pitch_d_mm"], p["ball_d_mm"], p["ball_count"])
    inner_shoulder, outer_shoulder = (p["inner_shoulder_d_mm"], p["outer_shoulder_d_mm"])
    inner_groove, outer_groove = (p["inner_groove_radius_mm"], p["outer_groove_radius_mm"])

    if not (d < inner_shoulder < pitch < outer_shoulder < D):
        raise ContractError("PARAMETER_INVALID", "/parameters", "Expected d < inner shoulder < pitch < outer shoulder < D")
    if inner_groove <= ball_d / 2 or outer_groove <= ball_d / 2:
        raise ContractError("PARAMETER_INVALID", "/parameters", "Groove curvature must exceed ball radius")
    if not (pitch - 2 * inner_groove < inner_shoulder < pitch - ball_d + 2 * inner_groove):
        raise ContractError("PARAMETER_INVALID", "/parameters/inner_shoulder_d_mm", "Inner shoulder does not intersect raceway")
    if not (pitch + ball_d - 2 * outer_groove < outer_shoulder < pitch + 2 * outer_groove):
        raise ContractError("PARAMETER_INVALID", "/parameters/outer_shoulder_d_mm", "Outer shoulder does not intersect raceway")
    if pitch / 2 - inner_groove <= d / 2 or pitch / 2 + outer_groove >= D / 2:
        raise ContractError("PARAMETER_INVALID", "/parameters", "Raceway cuts through bore or outside envelope")
    if count > 1 and pitch * math.sin(math.pi / count) <= ball_d:
        raise ContractError("PARAMETER_INVALID", "/parameters/ball_count", "Adjacent balls overlap")

    # A toroidal cutting solid carves actual concave raceways into distinct rings.
    inner = annulus(d, inner_shoulder, B).cut(cq.Solid.makeTorus(pitch / 2, inner_groove))
    outer = annulus(outer_shoulder, D, B).cut(cq.Solid.makeTorus(pitch / 2, outer_groove))
    ball = sphere(ball_d)
    pieces = (("inner_ring", inner), ("outer_ring", outer), ("ball", ball))
    for name, shape in pieces:
        if not inspect_solid(shape).valid:
            raise ContractError("BREP_INVALID", f"/geometry/{name}", "Invalid solid after raceway cut")
    if interference_volume(inner, outer) > 1e-7:
        raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry", "Inner and outer races overlap")

    positions = circular_positions(pitch, count)
    # Races are axisymmetric: a single ball/race interference test is sufficient.
    reference_ball = ball.translate(positions[0])
    if max(interference_volume(inner, reference_ball), interference_volume(outer, reference_ball)) > 1e-6:
        raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry", "Ball penetrates a raceway")

    components = (
        ComponentDefinition("inner_ring", "inner_ring", inner),
        ComponentDefinition("outer_ring", "outer_ring", outer),
        ComponentDefinition("ball", "rolling_element", ball),
    )
    instances = (
        ComponentInstance("inner_ring", "inner_ring"),
        ComponentInstance("outer_ring", "outer_ring"),
    ) + tuple(
        ComponentInstance(f"ball_{i+1:03d}", "ball", position)
        for i, position in enumerate(positions)
    )
    return AssemblyModel(BearingType.DEEP_GROOVE, components, instances)

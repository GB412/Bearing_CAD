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
from .geometry import annulus, sphere, cylindrical_roller, circular_positions
from .geometry_checks import inspect_solid, interference_volume
from .contracts import StampedCageSpec
from .stamping import stamped_cage_components


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

    if isinstance(request.cage, StampedCageSpec):
        upper, lower, rivet, rivet_centers = stamped_cage_components(
            request.cage, pitch_d_mm=pitch, ball_d_mm=ball_d,
            ball_count=count, bearing_width_mm=B,
            inner_shoulder_d_mm=inner_shoulder,
            outer_shoulder_d_mm=outer_shoulder,
        )
        for shape in (upper, lower):
            if interference_volume(shape, inner) > 1e-6 or interference_volume(shape, outer) > 1e-6:
                raise ContractError("ASSEMBLY_INTERFERENCE", "/cage", "Stamped cage penetrates ring")
        placed_rivet = rivet.translate(rivet_centers[0])
        if (interference_volume(placed_rivet, inner) > 1e-6 or
            interference_volume(placed_rivet, outer) > 1e-6 or
            interference_volume(placed_rivet, reference_ball) > 1e-6):
            raise ContractError("ASSEMBLY_INTERFERENCE", "/cage", "Rivet penetrates bearing")
        components = (
            ComponentDefinition("inner_ring", "inner_ring", inner),
            ComponentDefinition("outer_ring", "outer_ring", outer),
            ComponentDefinition("ball", "rolling_element", ball),
            ComponentDefinition("cage_upper", "cage", upper),
            ComponentDefinition("cage_lower", "cage", lower),
            ComponentDefinition("rivet", "cage", rivet),
        )
        instances = (
            ComponentInstance("inner_ring", "inner_ring"),
            ComponentInstance("outer_ring", "outer_ring"),
            ComponentInstance("cage_upper", "cage_upper"),
            ComponentInstance("cage_lower", "cage_lower"),
        ) + tuple(ComponentInstance(f"ball_{i+1:03d}", "ball", location)
                  for i, location in enumerate(positions)) + tuple(
            ComponentInstance(f"rivet_{i+1:03d}", "rivet", location)
            for i, location in enumerate(rivet_centers))
        return AssemblyModel(BearingType.DEEP_GROOVE, components, instances)

    cage_shape = None
    if request.cage is not None:
        cage_spec = request.cage
        if not (inner_shoulder < cage_spec.inner_d_mm < cage_spec.outside_d_mm < outer_shoulder):
            raise ContractError("PARAMETER_INVALID", "/cage", "Cage must lie radially between shoulders")
        # Concept-only alternative to spherical boolean pockets: two axial rims
        # connected by one bridge in each gap between adjacent balls.
        # Rim/bridge proportions are visual-geometry heuristics, not RoBAS
        # manufacturing rules or an approved engineering cage design.
        rim_thickness = cage_spec.width_mm / 11.0
        bridge_diameter = ball_d / 8.0
        if not (ball_d / 2 + cage_spec.pocket_clearance_mm <
                cage_spec.width_mm / 2 - rim_thickness):
            raise ContractError("PARAMETER_INVALID", "/cage/width_mm", "Insufficient axial ball clearance")
        if pitch * math.sin(math.pi / count) - ball_d/2 <= bridge_diameter/2 + cage_spec.pocket_clearance_mm:
            raise ContractError("PARAMETER_INVALID", "/cage", "Insufficient tangential bridge clearance")
        upper = annulus(cage_spec.inner_d_mm, cage_spec.outside_d_mm, rim_thickness).translate(
            (0, 0, (cage_spec.width_mm-rim_thickness)/2))
        lower = annulus(cage_spec.inner_d_mm, cage_spec.outside_d_mm, rim_thickness).translate(
            (0, 0, -(cage_spec.width_mm-rim_thickness)/2))
        cage_shape = upper.union(lower)
        bridge_length = cage_spec.width_mm - 2*rim_thickness + 0.2
        for i in range(count):
            angle = 2 * math.pi * (i+0.5) / count
            bridge = cylindrical_roller(bridge_diameter, bridge_length).translate(
                (pitch/2 * math.cos(angle), pitch/2 * math.sin(angle), 0))
            cage_shape = cage_shape.union(bridge)
        if not inspect_solid(cage_shape).valid:
            raise ContractError("BREP_INVALID", "/cage", "Disconnected or invalid cage")
        if (interference_volume(cage_shape, inner) > 1e-6 or
            interference_volume(cage_shape, outer) > 1e-6 or
            interference_volume(cage_shape, reference_ball) > 1e-6):
            raise ContractError("ASSEMBLY_INTERFERENCE", "/cage", "Cage overlaps races or rolling elements")

    components = (
        ComponentDefinition("inner_ring", "inner_ring", inner),
        ComponentDefinition("outer_ring", "outer_ring", outer),
        ComponentDefinition("ball", "rolling_element", ball),
    )
    if cage_shape is not None:
        components += (ComponentDefinition("cage", "cage", cage_shape),)
    instances = (
        ComponentInstance("inner_ring", "inner_ring"),
        ComponentInstance("outer_ring", "outer_ring"),
    ) + tuple(
        ComponentInstance(f"ball_{i+1:03d}", "ball", position)
        for i, position in enumerate(positions)
    )
    if cage_shape is not None:
        instances += (ComponentInstance("cage", "cage"),)
    return AssemblyModel(BearingType.DEEP_GROOVE, components, instances)

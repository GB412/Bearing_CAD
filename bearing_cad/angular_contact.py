"""Functional angular-contact ball bearing, exact B-Rep, positive-angle orientation.

RoBAS ACBGeometry and SingleRowAngularContact*Race supply the modeling intent,
not unquestioned dimensions: RoBAS has ambiguous degree/radian call paths.
All distances in mm, axis Z, balls in XY mid-plane, input contact angle degrees.
This model has nominal geometric contact, not a load/clearance design.
"""
from __future__ import annotations

import math
import cadquery as cq

from .contracts import (AssemblyModel, BearingRequest, BearingType, ComponentDefinition,
                        ComponentInstance, ContractError)
from .geometry import circular_positions, revolve_radial_profile, sphere
from .geometry_checks import inspect_solid, interference_volume


def _raceway_centres(pitch_radius: float, ball_radius: float,
                     inner_groove_radius: float, outer_groove_radius: float,
                     angle_deg: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """(R,Z) torus centres for a +Z outer contact normal.

    Ball centre is (pitch_radius, 0). For each race the distance from the
    ball centre to the torus section centre equals groove_r - ball_r.
    Contact normals point radially inward/-Z on the inner race and outward/+Z
    on the outer race. Convert degrees at precisely this boundary.
    """
    alpha = math.radians(angle_deg)
    cosine, sine = math.cos(alpha), math.sin(alpha)
    inner_offset = inner_groove_radius - ball_radius
    outer_offset = outer_groove_radius - ball_radius
    return ((pitch_radius + inner_offset * cosine, inner_offset * sine),
            (pitch_radius - outer_offset * cosine, -outer_offset * sine))


def build_angular_contact(request: BearingRequest) -> AssemblyModel:
    """Build distinct asymmetric raceways and balls without a cage.

    Shoulder diameters are explicit and unequal: inner left is higher than
    inner right; outer right is higher than outer left (smaller bore). The
    contact direction is fixed to positive Z on the outer race in v1.
    """
    if request.bearing_type != BearingType.ANGULAR_CONTACT:
        raise ContractError("NOT_SUPPORTED", "/bearing_type", "Expected angular-contact ball bearing")
    if request.cage is not None:
        raise ContractError("NOT_SUPPORTED", "/cage", "Angular-contact cage not implemented")
    if request.detail_level != "functional":
        raise ContractError("NOT_SUPPORTED", "/detail_level", "Only functional B-Rep is supported")

    p = request.parameters
    d, D, B = p["bore_d_mm"], p["outside_d_mm"], p["width_mm"]
    pitch, ball_d, count = p["pitch_d_mm"], p["ball_d_mm"], p["ball_count"]
    ri, ro = p["inner_groove_radius_mm"], p["outer_groove_radius_mm"]
    angle = p["contact_angle_deg"]
    il = p["inner_shoulder_left_d_mm"] / 2
    ir = p["inner_shoulder_right_d_mm"] / 2
    ol = p["outer_shoulder_left_d_mm"] / 2
    oright = p["outer_shoulder_right_d_mm"] / 2
    ball_r, pitch_r = ball_d / 2, pitch / 2

    if ri <= ball_r or ro <= ball_r:
        raise ContractError("PARAMETER_INVALID", "/parameters", "Raceway curvature must exceed ball radius")
    if not (d / 2 < ir < il < pitch_r < oright < ol < D / 2):
        raise ContractError("PARAMETER_INVALID", "/parameters",
                            "Expected bore < inner right < inner left < pitch < outer right < outer left < outside")
    if count > 256:
        raise ContractError("PARAMETER_INVALID", "/parameters/ball_count", "Exceeds CAD builder instance budget")
    if count > 1 and pitch * math.sin(math.pi / count) <= ball_d:
        raise ContractError("PARAMETER_INVALID", "/parameters/ball_count", "Adjacent balls overlap")

    inner_center, outer_center = _raceway_centres(pitch_r, ball_r, ri, ro, angle)
    # Full toroidal cutter must stay inside the ring wall and axial envelope.
    if inner_center[0] - ri <= d / 2 or outer_center[0] + ro >= D / 2:
        raise ContractError("PARAMETER_INVALID", "/parameters",
                            "Raceway cuts through the bore or outside diameter")
    if max(abs(inner_center[1]) + ri, abs(outer_center[1]) + ro) >= B / 2:
        raise ContractError("PARAMETER_INVALID", "/parameters/width_mm",
                            "Raceway cutter crosses the axial end face")
    if not (inner_center[0] - ri < ir and il < pitch_r
            and pitch_r < oright and ol < outer_center[0] + ro):
        raise ContractError("PARAMETER_INVALID", "/parameters",
                            "Shoulders do not create observable asymmetric raceways")

    low, high = -B / 2, B / 2
    # The mid-plane changes shoulder height. The toroidal groove smooths the
    # active rolling path; the step itself is concept-only, not a chamfer.
    inner_section = ((d / 2, low), (il, low), (il, 0),
                     (ir, 0), (ir, high), (d / 2, high))
    outer_section = ((D / 2, low), (ol, low), (ol, 0),
                     (oright, 0), (oright, high), (D / 2, high))
    inner_cut = cq.Solid.makeTorus(inner_center[0], ri,
                                  pnt=cq.Vector(0, 0, inner_center[1]))
    outer_cut = cq.Solid.makeTorus(outer_center[0], ro,
                                  pnt=cq.Vector(0, 0, outer_center[1]))
    inner_ring = revolve_radial_profile(inner_section).cut(inner_cut)
    outer_ring = revolve_radial_profile(outer_section).cut(outer_cut)
    ball = sphere(ball_d)
    parts = (("inner_ring", inner_ring), ("outer_ring", outer_ring), ("ball", ball))
    for name, shape in parts:
        try:
            report = inspect_solid(shape)
        except (RuntimeError, ValueError) as error:
            raise ContractError("BREP_INVALID", f"/geometry/{name}", str(error)) from error
        if not report.valid:
            raise ContractError("BREP_INVALID", f"/geometry/{name}", "Invalid or disconnected solid")

    if interference_volume(inner_ring, outer_ring) > 1e-6:
        raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry", "Inner and outer rings intersect")
    positions = circular_positions(pitch, count)
    # All rings are axisymmetric; checking one ball is geometrically sufficient.
    reference_ball = ball.translate(positions[0])
    for shape in (inner_ring, outer_ring):
        if interference_volume(shape, reference_ball) > 1e-6:
            raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry", "Ball penetrates a raceway")

    components = tuple(ComponentDefinition(name, "rolling_element" if name == "ball" else name, shape)
                       for name, shape in parts)
    instances = (ComponentInstance("inner_ring", "inner_ring"),
                 ComponentInstance("outer_ring", "outer_ring")) + tuple(
                     ComponentInstance(f"ball_{i+1:03d}", "ball", position)
                     for i, position in enumerate(positions))
    return AssemblyModel(BearingType.ANGULAR_CONTACT, components, instances)

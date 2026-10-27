"""Two pressed halves and separate rivets, inspired by RoBAS StampingCage.cs.

All dimensions are explicit mm. This is not certified manufacturer geometry.
"""
from __future__ import annotations
import math
import cadquery as cq
from .contracts import ContractError, StampedCageSpec
from .geometry import annulus, cylindrical_roller, circular_positions, sphere
from .geometry_checks import inspect_solid, interference_volume


def stamped_cage_components(spec: StampedCageSpec, *, pitch_d_mm: float,
                            ball_d_mm: float, ball_count: int,
                            bearing_width_mm: float, inner_shoulder_d_mm: float,
                            outer_shoulder_d_mm: float):
    """Return upper half, lower half, one rivet B-Rep and rivet centers."""
    if spec.kind != "stamping_double_half":
        raise ContractError("NOT_SUPPORTED", "/cage/kind", "Expected stamping_double_half")
    if not (inner_shoulder_d_mm < spec.inner_d_mm < pitch_d_mm <
            spec.outside_d_mm < outer_shoulder_d_mm):
        raise ContractError("PARAMETER_INVALID", "/cage", "Cage must fit between shoulders")
    if spec.width_mm > bearing_width_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm", "Stamped assembly exceeds bearing width")
    head_radius = spec.rivet_head_d_mm / 2
    if spec.rivet_shaft_d_mm >= spec.rivet_head_d_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/rivet_head_d_mm", "Rivet head must exceed shaft")
    if head_radius >= min((pitch_d_mm-spec.inner_d_mm)/2,
                          (spec.outside_d_mm-pitch_d_mm)/2):
        raise ContractError("PARAMETER_INVALID", "/cage/rivet_head_d_mm", "Head exceeds cage band")
    half_height = spec.width_mm / 2 - head_radius
    ball_radius = ball_d_mm / 2
    if half_height <= ball_radius + spec.pocket_clearance_mm + spec.board_thickness_mm:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm", "Insufficient pocket-side board material")
    if ball_count > 1 and pitch_d_mm*math.sin(math.pi/(2*ball_count)) <= (
            ball_radius + head_radius + spec.pocket_clearance_mm):
        raise ContractError("PARAMETER_INVALID", "/cage/rivet_head_d_mm", "Rivets too close to balls")

    positions = circular_positions(pitch_d_mm, ball_count)
    rivet_positions = tuple((
        pitch_d_mm/2*math.cos((i+.5)*2*math.pi/ball_count),
        pitch_d_mm/2*math.sin((i+.5)*2*math.pi/ball_count), 0.
    ) for i in range(ball_count))
    pocket = sphere(ball_d_mm + 2*spec.pocket_clearance_mm)
    bore = cylindrical_roller(spec.rivet_shaft_d_mm+2*spec.rivet_hole_clearance_mm,
                              2*half_height+.2)
    halves=[]
    for sign in (1,-1):
        half=annulus(spec.inner_d_mm,spec.outside_d_mm,half_height)
        half=half.translate((0,0,sign*half_height/2))
        for position in positions:
            half=half.cut(pocket.translate(position))
        for position in rivet_positions:
            half=half.cut(bore.translate(position))
        if not inspect_solid(half).valid:
            raise ContractError("BREP_INVALID", "/cage", "Stamped half invalid or disconnected")
        halves.append(half)

    shaft=cylindrical_roller(spec.rivet_shaft_d_mm,2*half_height+.2)
    head=sphere(spec.rivet_head_d_mm)
    side=4*head_radius
    above=cq.Workplane("XY").box(side,side,2*head_radius).translate((0,0,head_radius))
    below=cq.Workplane("XY").box(side,side,2*head_radius).translate((0,0,-head_radius))
    rivet=shaft.union(head.intersect(above).translate((0,0,half_height)))
    rivet=rivet.union(head.intersect(below).translate((0,0,-half_height)))
    if not inspect_solid(rivet).valid:
        raise ContractError("BREP_INVALID", "/cage/rivet", "Rivet B-Rep invalid")
    reference_ball=sphere(ball_d_mm).translate(positions[0])
    reference_rivet=rivet.translate(rivet_positions[0])
    for half in halves:
        if interference_volume(half,reference_ball)>1e-6:
            raise ContractError("ASSEMBLY_INTERFERENCE", "/cage", "Half penetrates a ball")
        if interference_volume(half,reference_rivet)>1e-6:
            raise ContractError("ASSEMBLY_INTERFERENCE", "/cage", "Rivet penetrates half")
    if interference_volume(halves[0],halves[1])>1e-6:
        raise ContractError("ASSEMBLY_INTERFERENCE", "/cage", "Halves overlap")
    return halves[0],halves[1],rivet,rivet_positions

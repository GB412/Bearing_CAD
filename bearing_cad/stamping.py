"""Two pressed spherical-cup halves and separate rivets, inspired by RoBAS StampingCage.cs.

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
    half_height = spec.width_mm / 2
    ball_radius = ball_d_mm / 2
    thickness = spec.board_thickness_mm
    if half_height <= ball_radius + spec.pocket_clearance_mm + thickness:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm", "Insufficient envelope for spherical shell")
    if thickness + head_radius > half_height:
        raise ContractError("PARAMETER_INVALID", "/cage/width_mm", "Rivet head exceeds axial cage envelope")
    if ball_count > 1 and pitch_d_mm*math.sin(math.pi/(2*ball_count)) <= (
            ball_radius + head_radius + spec.pocket_clearance_mm):
        raise ContractError("PARAMETER_INVALID", "/cage/rivet_head_d_mm", "Rivets too close to balls")

    positions = circular_positions(pitch_d_mm, ball_count)
    rivet_positions = tuple((
        pitch_d_mm/2*math.cos((i+.5)*2*math.pi/ball_count),
        pitch_d_mm/2*math.sin((i+.5)*2*math.pi/ball_count), 0.
    ) for i in range(ball_count))
    # RoBAS StampingCage.halfCage construction: subtract two annuli
    # with differently sized spherical pockets. The remainder is a thin
    # joining board and curved spherical cup wall, not a full-thickness ring.
    pocket = sphere(ball_d_mm + 2*spec.pocket_clearance_mm)
    offset_pocket = sphere(ball_d_mm + 2*(spec.pocket_clearance_mm + thickness))
    first = annulus(spec.inner_d_mm,spec.outside_d_mm,half_height)
    first = first.translate((0,0,half_height/2))
    inset = annulus(spec.inner_d_mm,spec.outside_d_mm,half_height-thickness)
    inset = inset.translate((0,0,(half_height+thickness)/2))
    for position in positions:
        first = first.cut(pocket.translate(position))
        inset = inset.cut(offset_pocket.translate(position))
    upper = first.cut(inset)
    # Rivets pierce only the flat central joining board.
    hole = cylindrical_roller(spec.rivet_shaft_d_mm+2*spec.rivet_hole_clearance_mm,
                              thickness+.2)
    for position in rivet_positions:
        upper = upper.cut(hole.translate((position[0],position[1],thickness/2)))
    if not inspect_solid(upper).valid:
        raise ContractError("BREP_INVALID", "/cage", "Stamped shell invalid or disconnected")
    upper_solid = upper.val()
    lower_solid = upper_solid.mirror("XY")
    if not inspect_solid(lower_solid).valid:
        raise ContractError("BREP_INVALID", "/cage", "Mirrored stamped shell invalid")
    halves = [upper_solid, lower_solid]

    shaft=cylindrical_roller(spec.rivet_shaft_d_mm,2*thickness+.2)
    head=sphere(spec.rivet_head_d_mm)
    side=4*head_radius
    above=cq.Workplane("XY").box(side,side,2*head_radius).translate((0,0,head_radius))
    below=cq.Workplane("XY").box(side,side,2*head_radius).translate((0,0,-head_radius))
    rivet=shaft.union(head.intersect(above).translate((0,0,thickness)))
    rivet=rivet.union(head.intersect(below).translate((0,0,-thickness)))
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

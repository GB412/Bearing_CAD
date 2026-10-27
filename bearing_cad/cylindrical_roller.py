"""Functional cylindrical roller bearing B-Rep with explicit flange geometry.

Based on the audited RoBAS CRB configuration and roller-array ideas, not
copied Eyeshot code. Nominal contact/end-face details are not manufacturing
ready. All distances are mm, the axis is Z, and the midplane is Z=0.
"""
from __future__ import annotations

import math

from .contracts import (AssemblyModel, BearingRequest, BearingType,
                        ComponentDefinition, ComponentInstance, ContractError)
from .geometry import circular_positions, cylindrical_roller, revolve_radial_profile, annulus
from .geometry_checks import inspect_solid, interference_volume
from .cages import cylindrical_window_cage

# Integral flanges: left (-Z), right (+Z). NUP includes a distinct loose rib.
_CONFIGURATIONS = {
    "N": ("both", "none", False),
    "NU": ("none", "both", False),
    "NJ": ("left", "both", False),
    "NF": ("both", "left", False),
    "NUP": ("left", "both", True),
}


def _ring_profile(*, is_inner: bool, bore: float, outside: float,
                  race: float, tip: float, low: float, high: float,
                  flange_width: float, sides: str):
    """Make one fully connected stepped annular ring using a revolved section."""
    left = sides in {"left", "both"}
    right = sides in {"right", "both"}
    first = bore if is_inner else outside
    start_surface = tip if left else race
    outline = [(first, low), (start_surface, low)]
    if left:
        outline.extend([(tip, low + flange_width), (race, low + flange_width)])
    if right:
        outline.extend([(race, high - flange_width),
                        (tip, high - flange_width), (tip, high)])
    else:
        outline.append((race, high))
    outline.append((first, high))
    return revolve_radial_profile(outline)


def build_cylindrical_roller(request: BearingRequest) -> AssemblyModel:
    """Construct N, NU, NJ, NF or NUP races and separate Z-axis rollers.

    Every shape-defining clearance and flange dimension is supplied explicitly.
    The cage is omitted; no unreviewed RoBAS optimization formula is used.
    """
    if request.bearing_type != BearingType.CYLINDRICAL:
        raise ContractError("NOT_SUPPORTED", "/bearing_type", "Expected cylindrical roller bearing")
    p = request.parameters
    config = p["configuration"]
    if config not in _CONFIGURATIONS:
        raise ContractError("NOT_SUPPORTED", "/parameters/configuration", "Unknown flange arrangement")
    inner_sides, outer_sides, loose = _CONFIGURATIONS[config]
    d, D, B = p["bore_d_mm"], p["outside_d_mm"], p["width_mm"]
    roller_d, roller_length, count = p["roller_d_mm"], p["roller_length_mm"], p["roller_count"]
    pitch = p["pitch_d_mm"]
    radial_gap, axial_gap, rib_width = p["radial_clearance_mm"], p["axial_clearance_mm"], p["rib_width_mm"]
    inner_tip = p["inner_rib_tip_d_mm"] / 2
    outer_tip = p["outer_rib_tip_d_mm"] / 2
    roller_radius, pitch_radius = roller_d / 2, pitch / 2
    inner_race = pitch_radius - roller_radius - radial_gap
    outer_race = pitch_radius + roller_radius + radial_gap
    if not (d / 2 < inner_race < inner_tip < outer_tip < outer_race < D / 2):
        raise ContractError("PARAMETER_INVALID", "/parameters", "Invalid radial raceway/flange order or ring wall thickness")
    if not (roller_length / 2 + axial_gap < B / 2 - rib_width):
        raise ContractError("PARAMETER_INVALID", "/parameters/rib_width_mm", "No axial end clearance for ribs")
    if count > 1 and pitch * math.sin(math.pi / count) <= roller_d:
        raise ContractError("PARAMETER_INVALID", "/parameters/roller_count", "Adjacent rollers overlap")
    if count > 256:
        raise ContractError("PARAMETER_INVALID", "/parameters/roller_count", "Exceeds local geometry budget")

    lower, upper = -B / 2, B / 2
    inner_upper = upper - rib_width if loose else upper
    inner = _ring_profile(is_inner=True, bore=d / 2, outside=D / 2,
                          race=inner_race, tip=inner_tip, low=lower,
                          high=inner_upper, flange_width=rib_width, sides=inner_sides)
    outer = _ring_profile(is_inner=False, bore=d / 2, outside=D / 2,
                          race=outer_race, tip=outer_tip, low=lower,
                          high=upper, flange_width=rib_width, sides=outer_sides)
    roller = cylindrical_roller(roller_d, roller_length)
    components = [ComponentDefinition("inner_ring", "inner_ring", inner),
                  ComponentDefinition("outer_ring", "outer_ring", outer),
                  ComponentDefinition("roller", "rolling_element", roller)]
    instances = [ComponentInstance("inner_ring", "inner_ring"),
                 ComponentInstance("outer_ring", "outer_ring")]
    positions = circular_positions(pitch, count)
    for i, pos in enumerate(positions):
        instances.append(ComponentInstance(f"roller_{i+1:03d}", "roller", pos))
    if loose:
        # This detachable collar abuts, but is NOT fused to, the main inner ring.
        collar = annulus(d, 2 * inner_tip, rib_width).translate((0, 0, upper - rib_width / 2))
        components.append(ComponentDefinition("loose_rib", "loose_rib", collar))
        instances.append(ComponentInstance("loose_rib", "loose_rib"))

    for component in components:
        try:
            good = inspect_solid(component.shape).valid
        except (ValueError, RuntimeError) as error:
            raise ContractError("BREP_INVALID", f"/geometry/{component.component_id}", str(error)) from error
        if not good:
            raise ContractError("BREP_INVALID", f"/geometry/{component.component_id}", "Invalid closed B-Rep")
    # Analytic construction enforces ring separation and roller spacing. Validate
    # a representative roller with OCCT to catch geometric implementation errors.
    first_roller = roller.translate(positions[0])
    for component in components:
        if component.component_id == "roller":
            continue
        if interference_volume(component.shape, first_roller) > 1e-6:
            raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry", "A roller penetrates a ring/rib")
    if interference_volume(inner, outer) > 1e-6:
        raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry", "Inner and outer rings intersect")
    if loose and interference_volume(inner, components[-1].shape) > 1e-6:
        raise ContractError("ASSEMBLY_INTERFERENCE", "/geometry/loose_rib", "Loose rib penetrates inner ring")
    if request.cage is not None:
        cage = cylindrical_window_cage(
            request.cage, pitch_d_mm=pitch, roller_d_mm=roller_d,
            roller_length_mm=roller_length, roller_count=count,
            bearing_width_mm=B, inner_rib_tip_d_mm=2 * inner_tip,
            outer_rib_tip_d_mm=2 * outer_tip,
        )
        for part in components:
            if part.component_id != "roller" and interference_volume(cage, part.shape) > 1e-6:
                raise ContractError("ASSEMBLY_INTERFERENCE", "/cage",
                                    "Window cage overlaps " + part.component_id)
        if interference_volume(cage, first_roller) > 1e-6:
            raise ContractError("ASSEMBLY_INTERFERENCE", "/cage",
                                "Window cage penetrates a roller")
        components.append(ComponentDefinition("cage", "cage", cage))
        instances.append(ComponentInstance("cage", "cage"))
    return AssemblyModel(BearingType.CYLINDRICAL, tuple(components), tuple(instances))

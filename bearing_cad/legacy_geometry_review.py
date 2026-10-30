"""Read-only source-level audit of RoBAS vs current angular-contact CAD.

Not an Eyeshot-vs-OCCT solid equivalence measurement. Do not change
production groove/taper geometry without drawing and solid evidence.
"""
from __future__ import annotations

import math
from typing import Mapping


LEGACY_SOURCES = (
    "RoBAS/BearingModel/Race/InnerRace/SingleRowAngularContactInnerRace.cs:380-400",
    "RoBAS/BearingModel/Race/OuterRace/SingleRowAngularContactOuterRace.cs:303-328",
    "RoBAS/Core/BallBearing/AngularContactBallBearing/ACBGeometry.cs:64-79",
)


def review_angular_contact(parameters: Mapping[str, float]) -> dict:
    """Return a machine-readable analytical comparison, dimensions in mm."""
    required = ("width_mm", "ball_d_mm", "pitch_d_mm", "contact_angle_deg",
                "inner_groove_radius_mm", "outer_groove_radius_mm")
    p = {key: float(parameters[key]) for key in required}
    if any(not math.isfinite(x) for x in p.values()):
        raise ValueError("Non-finite angular-contact geometry")
    if p["width_mm"] <= 0 or p["ball_d_mm"] <= 0 or p["pitch_d_mm"] <= 0:
        raise ValueError("Invalid dimensions")
    if not 0 < p["contact_angle_deg"] < 90:
        raise ValueError("Contact angle must lie in (0,90) degrees")
    ball_r = p["ball_d_mm"] / 2
    if min(p["inner_groove_radius_mm"], p["outer_groove_radius_mm"]) <= ball_r:
        raise ValueError("Groove radii must exceed ball radius")
    angle = math.radians(p["contact_angle_deg"])
    inner_z = (p["inner_groove_radius_mm"] - ball_r) * math.sin(angle)
    outer_z = -(p["outer_groove_radius_mm"] - ball_r) * math.sin(angle)
    taper_angle = 3.0
    return {
        "status": "STATIC_SOURCE_COMPARISON_ONLY",
        "not_proven": ["Legacy Eyeshot surface equivalence", "Manufacturing accuracy",
                       "Whether legacy drawing groove positions reflect intended design"],
        "source_paths": LEGACY_SOURCES,
        "geometry": {
            "legacy_draw_torus_center_z_mm": 0.0,
            "occt_inner_torus_center_z_mm": inner_z,
            "occt_outer_torus_center_z_mm": outer_z,
            "legacy_cone_half_angle_deg": taper_angle,
            "legacy_cone_half_width_radial_change_mm":
                p["width_mm"] / 2 * math.tan(math.radians(taper_angle)),
            "current_nominal_contact_angle_deg": p["contact_angle_deg"],
            "cross_section": "RoBAS uses 3-deg cones; current OCCT uses stepped shoulders",
        },
        "recommended_action": "Retain current production geometry until matched legacy IGES/solid and reviewed drawings are available",
    }

"""RoBAS original Cr/Cor values used by SetCADTextValue, in N -> kN text.

Sources: BaseOptimizer.SearchCoeffcient, DGBOptimizer, ACBOptimizer,
CRBOptimizer. Coefficients are read from user's original Resource/*.csv.
This is legacy drawing-data parity, not a DLAP replacement/approval.
"""
from __future__ import annotations

import csv
from pathlib import Path
import math
from .drawing_variables import DrawingDataError
from .drawing_legacy_dimensions import number,overlay

_BALL_TYPES={"rolling.deep_groove_ball","rolling.angular_contact_ball"}
_ROLLER="rolling.cylindrical_roller"

def _coefficients(resources, bearing_type, gamma):
    file=Path(resources)/"Resource"/(
        "圆柱滚子轴承相关系数.csv" if bearing_type==_ROLLER
        else "球轴承零件相关系数.csv")
    if not file.is_file() or file.is_symlink():
        raise DrawingDataError("Missing original RoBAS coefficient CSV: "+file.name)
    if file.stat().st_size > 250_000:
        raise DrawingDataError("Oversized original coefficient CSV")
    try:
        with file.open(encoding="utf-8-sig",newline="") as stream:
            reader=csv.DictReader(stream)
            columns=("Dw/Dpw","fc") if bearing_type==_ROLLER else ("Dw/Dpw","fc","fo")
            if not reader.fieldnames or not set(columns).issubset(reader.fieldnames):
                raise DrawingDataError("RoBAS coefficient table schema mismatch")
            for row in reader:
                g=float(row["Dw/Dpw"].strip())
                if abs(g-gamma)<1e-10:
                    fc=float(row["fc"])
                    fo=0.0 if bearing_type==_ROLLER else float(row["fo"])
                    if not math.isfinite(fc) or not math.isfinite(fo):
                        raise DrawingDataError("Non-finite RoBAS coefficient")
                    return fc,fo,True
    except (OSError,UnicodeError,ValueError,KeyError) as exc:
        raise DrawingDataError("RoBAS coefficient lookup failed") from exc
    # Original BaseOptimizer/CRBOptimizer initialize fc and fo to 0 and
    # leave them at zero when a rounded gamma row is not found.
    return 0.,0.,False

def calculate_robas_loads(*,resources,bearing_type,parameters):
    """Return original C# load formulas in Newton, no standards correction."""
    if bearing_type not in _BALL_TYPES|{_ROLLER}:
        raise DrawingDataError("Unsupported RoBAS bearing type")
    is_roller=bearing_type==_ROLLER
    diameter=number(parameters["roller_d_mm" if is_roller else "ball_d_mm"],"Dw")
    pitch=number(parameters["pitch_d_mm"],"Dpw")
    count=parameters["roller_count" if is_roller else "ball_count"]
    if diameter<=0 or pitch<=0 or type(count) is not int or count<1:
        raise DrawingDataError("Invalid RoBAS rolling-element design")
    gamma=round(diameter/pitch,2)  # System.Math.Round( ,2), midpoint-to-even.
    fc,fo,matched=_coefficients(resources,bearing_type,gamma)
    if is_roller:
        length=number(parameters["roller_length_mm"],"Lw")
        if length<=0:raise DrawingDataError("Invalid roller length")
        cr=1.89*fc*length**(7/9)*count**(3/4)*diameter**(29/27)
        cor=21.6*count*length*diameter
    elif bearing_type=="rolling.deep_groove_ball":
        bm=1.3
        cr=bm*fc*count**(2/3)*diameter**1.8*(1 if diameter<=25.4 else 3.467)
        cor=fo*count*diameter**2
    else:
        bm=1.3
        alpha=math.radians(number(parameters["contact_angle_deg"],"alpha"))
        cos=math.cos(alpha)
        if not 0<alpha<math.pi/2:raise DrawingDataError("Invalid contact angle")
        factor=bm*fc*(cos**0.7)*count**(2/3)
        cr=factor*diameter**1.8 if diameter<=25.4 else 3.647*factor*diameter**1.4
        cor=fo*count*diameter**2*cos
    return {"dynamic_load_n":cr,"static_load_n":cor,"gamma":gamma,
            "fc":fc,"fo":fo,"coefficient_found":matched,
            "status":"RO BAS_LEGACY_CALCULATION".replace(" ",""),
            "warning":None if matched else "RoBAS originally defaults coefficients to zero if gamma is absent"}

def apply_robas_loads(*,report,resources,bearing_type,parameters):
    load=calculate_robas_loads(resources=resources,bearing_type=bearing_type,
                               parameters=parameters)
    revised=overlay(report,{"Cr":f"{load['dynamic_load_n']/1000:.2f}",
                            "Cor":f"{load['static_load_n']/1000:.2f}"},
                    "robas_optimizer_original")
    revised["legacy_load_evidence"]={
        "gamma":load["gamma"],"fc":load["fc"],"fo":load["fo"],
        "coefficient_found":load["coefficient_found"],
        "warning":load["warning"],
    }
    return revised

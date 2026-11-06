"""Cylinder roller SetCADTextValue dimensions and roller groove-width lookup.

Follows RoBAS/Core and DataControl.GetRollerGrooveWidthDeviation:
SQL first matching rollerLength >= Lw, preserve C# integer truncation.
"""
from __future__ import annotations
import math
from pathlib import Path
import sqlite3
from .drawing_variables import DrawingDataError
from .drawing_legacy_dimensions import (number,text,overlay,common_dimensions,
                                        groove_position_tolerance)

def roller_groove_width_deviation(resources: Path, roller_length_mm: float) -> dict:
    length=number(roller_length_mm,"roller length")
    if length <= 0:
        raise DrawingDataError("Roller length must be positive")
    db_path=Path(resources)/"Data"/"CRBData.db"
    if not db_path.is_file() or db_path.is_symlink():
        raise DrawingDataError("Missing original CRB SQLite database")
    try:
        with sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True) as db:
            row=db.execute('SELECT * FROM "滚道宽度公差" WHERE rollerLength>=? LIMIT 1',
                           (length,)).fetchone()
    except sqlite3.Error as ex:
        raise DrawingDataError("RoBAS roller groove width lookup failed") from ex
    # RoBAS leaves DataTable empty if no row; preserve preexisting variable values.
    return {} if row is None else {
        "E_Upper":"" if row[1] is None else str(row[1]),
        "E_Lower":"" if row[2] is None else str(row[2]),
    }

def apply_cylindrical_roller_dimensions(*,report,parameters,
                                        legacy_values=None,resources=None):
    """Original CRB E/E1/E2, groove, shoulder and width-deviation TEXT.

    For old-model InnerRaceGroovePosition, supply its actual value rather than
    assuming the current OCCT N/NUP race geometry has identical dimensions.
    """
    old=legacy_values or {}
    if not isinstance(old,dict):
        raise DrawingDataError("legacy_values must be a mapping")
    # Original CylinderRollerBearing.BearingWidth and Bore getters round to
    # 0.01 mm; CylinderRoller.RollerLength rounds to 0.01 mm, while
    # CRBOptimizer.RollerDiameter rounds to 0.0001 mm. SetCADTextValue reads
    # these public getters before calculating a/a2/E/E1/E2 and the original
    # SQLite groove-width deviation lookup. Do not mutate the CAD input.
    source_parameters=dict(parameters)
    source_parameters["bore_d_mm"]=round(number(parameters["bore_d_mm"],"bore"),2)
    source_parameters["outside_d_mm"]=round(number(parameters["outside_d_mm"],"outside"),2)
    source_parameters["width_mm"]=round(number(parameters["width_mm"],"width"),2)
    v=common_dimensions(source_parameters,old,"rolling.cylindrical_roller")
    bore=source_parameters["bore_d_mm"]
    width=source_parameters["width_mm"]
    length=round(number(parameters["roller_length_mm"],"roller length"),2)
    roller=round(number(parameters["roller_d_mm"],"roller diameter"),4)
    if length<=0:
        raise DrawingDataError("Original RoBAS rounded roller length is nonpositive")
    pt=groove_position_tolerance(bore)
    half=(width-length)/2
    v["a"]=text(half)+"±"+text(pt)
    v["a2"]=text(half-.05*roller)
    v["E"]=text(length)
    if "inner_groove_position_mm" in old:
        # RollerGeometry.InnerRaceGroovePosition is a 0.01-mm getter. E1/E2
        # have no valid inferred position for an arbitrary OCCT assembly;
        # preserve the explicit, reviewed legacy input requirement.
        position=round(number(old["inner_groove_position_mm"],"inner groove position"),2)
        # C# explicit int cast truncates toward zero (not Python floor).
        step=math.trunc((position-.05*roller)/.5)*.5
        v["E1"]=text(width-2*step)
        v["E2"]=text(width-position-step)
    if resources is not None:
        v.update(roller_groove_width_deviation(resources,length))
    for label,field in (("Cr","dynamic_load_n"),("Cor","static_load_n")):
        if field in old:
            v[label]=f"{number(old[field],field)/1000:.2f}"
    return overlay(report,v,"robas_crb_SetCADTextValue")

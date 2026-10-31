"""RoBAS drawing labels: component dimensions and old tolerance rules.

Ported from MachineElement.cs and DeepGrooveBallBearingServer.SetCADTextValue.
This does not redraw DWG geometry or infer absent legacy groove/cage data.
"""
from __future__ import annotations
import math
from .drawing_variables import DrawingDataError

def number(v, name):
    if type(v) not in (int,float) or not math.isfinite(v):
        raise DrawingDataError("Invalid RoBAS number: "+name)
    return float(v)

def text(v):
    return format(v,'.15g')

def lookup(d, thresholds):
    for upper,val in thresholds:
        if d <= upper: return val
    return 0

def groove_d_tolerance(d):
    return lookup(number(d,"d"),((30,.01),(80,.015),(120,.02),(180,.025),
                               (250,.03),(315,.04),(math.inf,.05)))

def groove_position_tolerance(d,angular=False):
    d=number(d,"d")
    if angular:
        return lookup(d,((10,.02),(18,.02),(30,.02),(50,.025),(80,.03),
                         (120,.035),(180,.04),(250,.045),(math.inf,.045)))
    return lookup(d,((10,.01),(18,.015),(30,.02),(50,.025),(80,.03),
                     (120,.04),(180,.045),(250,.05),(315,.06),
                     (400,.07),(500,.08)))

def groove_radius_tolerance(d):
    return lookup(number(d,"ball diameter"),((6,.03),(10,.04),(18,.06),
                  (24,.09),(30,.12),(40,.14),(50,.18),(60,.22)))

def sidewall_d_tolerance(d):
    return lookup(number(d,"bore"),((18,.18),(30,.21),(50,.25),(80,.30),
                (120,.35),(180,.40),(250,.46),(315,.52),(400,.57),(500,.63)))

def overlay(report, updates, source):
    if report.get("schema_version")!="robas.drawing.variables.v1":
        raise DrawingDataError("Unknown RoBAS variable contract")
    rows=[dict(r) for r in report["variables"]]
    for r in rows:
        if r["name"] in updates:
            r["value"]=str(updates[r["name"]])
            r["source"]=source
    output=dict(report)
    output["variables"]=rows
    output["unresolved_names"]=sorted({r["name"] for r in rows if not r["value"]})
    output["unresolved_count"]=len(output["unresolved_names"])
    output["unresolved_ratings"]=[k for k in ("Cr","Cor") if k in output["unresolved_names"]]
    output["status"]="DRAFT_INCOMPLETE" if output["unresolved_count"] else "VARIABLES_POPULATED_UNREVIEWED"
    return output

def common_dimensions(p, legacy, kind):
    bore=number(p["bore_d_mm"],"bore")
    element=number(p.get("ball_d_mm",p.get("roller_d_mm")),"rolling diameter")
    position_d=p["outside_d_mm"] if kind=="rolling.angular_contact_ball" else bore
    gt=groove_d_tolerance(bore)
    pt=groove_position_tolerance(position_d,angular=kind=="rolling.angular_contact_ball")
    rt=groove_radius_tolerance(element)
    st=sidewall_d_tolerance(bore)
    values={}
    if kind!="rolling.cylindrical_roller":
        for k,src in (("Ri","inner_groove_radius_mm"),("Re","outer_groove_radius_mm")):
            if src in p:
                values[k]=f"{number(p[src],src):.2f}"
                values[k+"_Upper"]="+"+text(rt)
                values[k+"_Lower"]="0"
    for k,src in (("De","outer_groove_d_mm"),("di","inner_groove_d_mm")):
        if src in legacy: values[k]=f"{number(legacy[src],src):.3f}±{text(gt)}"
    if kind!="rolling.cylindrical_roller" and "inner_groove_position_mm" in legacy:
        values["a"]=f"{number(legacy['inner_groove_position_mm'],'a'):.1f}±{text(pt)}"
    for k,key in (("Dd2","outer_shoulder_d_mm"),("d2","inner_shoulder_d_mm")):
        alias="outer_sidewall_d_mm" if k=="Dd2" else "inner_sidewall_d_mm"
        v=legacy.get(alias,p.get(key))
        if v is not None:
            values[k]=f"{number(v,k):.1f}"
            values[k+"_Upper"]="+"+text(st) if k=="Dd2" else "0"
            values[k+"_Lower"]="0" if k=="Dd2" else text(-st)
    return values

def apply_deep_groove_dimensions(*,report,parameters,legacy_values=None):
    old=legacy_values or {}
    if not isinstance(old,dict): raise DrawingDataError("legacy_values must be a mapping")
    v=common_dimensions(parameters,old,"rolling.deep_groove_ball")
    for k,key in (("C_","cage_pocket_spacing_mm"),("C1_","cage_pocket_rivet_spacing_mm")):
        if key in old:v[k]=text(number(old[key],key))+"±0.025"
    for k,key in (("S_","cage_board_thickness_mm"),("rrc","cage_flat_to_sphere_radius_mm"),
                  ("Rc","cage_sphere_radius_mm"),("K_","cage_pocket_depth_mm"),
                  ("tc","cage_rivet_hole_d_mm")):
        if key in old:v[k]=text(number(old[key],key))
    for k,key,tol in (("Dcp","cage_pitch_d_mm","cage_pitch_tolerance_mm"),
                      ("Dc","cage_outer_d_mm","cage_outer_tolerance_mm"),
                      ("Dc1","cage_inner_d_mm","cage_inner_tolerance_mm")):
        if key in old and tol in old:
            v[k]=text(number(old[key],key))+"±"+text(number(old[tol],tol))
    for k,key in (("Rc_Upper","cage_sphere_upper_tolerance_mm"),
                  ("K_Upper","cage_pocket_upper_tolerance_mm"),
                  ("tc_Upper","rivet_hole_upper_tolerance_mm"),
                  ("tc_Lower","rivet_hole_lower_tolerance_mm")):
        if key in old:v[k]="+"+text(number(old[key],key))
    if "cage_sphere_upper_tolerance_mm" in old:v["Rc_Lower"]="0"
    if "cage_pocket_upper_tolerance_mm" in old:v["K_Lower"]="0"
    ball=number(parameters["ball_d_mm"],"ball diameter")
    count=parameters["ball_count"]
    if type(count) is not int or count<1:raise DrawingDataError("Invalid ball count")
    mass=round(math.pi*ball**3*7.8/6_000_000,5)
    v.update(W04=text(mass),W04Z=text(count*mass),W09="0",W09Z="0")
    for k,key,digits in (("W01","outer_race_weight_kg",3),("W02","inner_race_weight_kg",3),
                         ("W07","half_cage_weight_kg",5)):
        if key in old:v[k]=f"{number(old[key],key):.{digits}f}"
    if "half_cage_weight_kg" in old:
        v["W07Z"]=f"{2*number(old['half_cage_weight_kg'],'cage'):.5f}"
    if all(key in old for key in ("outer_race_weight_kg","inner_race_weight_kg","half_cage_weight_kg")):
        total=(sum(number(old[key],key) for key in ("outer_race_weight_kg","inner_race_weight_kg"))+
               2*number(old["half_cage_weight_kg"],"cage")+count*mass)
        v["W"]=f"{total:.3f}"
    for k,key in (("Cr","dynamic_load_n"),("Cor","static_load_n")):
        if key in old:v[k]=f"{number(old[key],key)/1000:.2f}"
    return overlay(report,v,"robas_dgb_SetCADTextValue")


def lock_height_deviation(t):
    """AngularContactBallBearing.DetermineLockHeightDeviation."""
    v=number(t,"lock height")
    return "-"+text(lookup(v,((.07,.01),(.1,.015),(.2,.02),(.29,.03),(.39,.04),(math.inf,.05))))

def acb_width_deviation(bore_mm):
    """AngularContactBallBearing.DetermineBearingWidthDeviation."""
    return text(lookup(number(bore_mm,"bore"),((10,.2),(80,.3),(math.inf,.5))))

def apply_angular_contact_dimensions(*,report,parameters,legacy_values=None):
    """Original ACB variable TEXT, including asymmetric groove and cage.

    The RoBAS model is not the current OCCT model; groove positions and
    shoulder values which are not in the CAD request are explicit inputs.
    """
    old=legacy_values or {}
    if not isinstance(old,dict): raise DrawingDataError("legacy_values must be a mapping")
    v=common_dimensions(parameters,old,"rolling.angular_contact_ball")
    pt=groove_position_tolerance(parameters["outside_d_mm"],angular=True)
    for label,key in (("ae","outer_groove_position_mm"),("ai","inner_race_groove_position_mm")):
        if key in old:v[label]=text(number(old[key],key))+"±"+text(pt)
    if "lock_height_mm" in old:
        height=number(old["lock_height_mm"],"lock height")
        v.update(t_SK=text(height),t_SK_Upper="0",t_SK_Lower=lock_height_deviation(height))
    v.update(T_=text(number(parameters["width_mm"],"width")),T_Upper="0",
             T_Lower="-"+acb_width_deviation(parameters["bore_d_mm"]))
    if "cage_pitch_d_mm" in old:
        v["Dcp"]=text(number(old["cage_pitch_d_mm"],"pitch"))+"±0.015"
    if "cage_pocket_spacing_mm" in old:
        v["C_"]=text(number(old["cage_pocket_spacing_mm"],"spacing"))+"±0.05"
    for label,key in (("Dc","cage_outer_d_mm"),("Dc1","cage_inner_d_mm"),
                      ("Deltac","cage_pocket_d_mm"),("Bc","cage_width_mm"),
                      ("e_","cage_chamfer_mm")):
        if key in old:v[label]=text(number(old[key],key))
    if "cage_width_mm" in old:
        v["Bca"]=text(number(old["cage_width_mm"],"width")/2)
    for label,key in (("Dc_Lower","cage_outer_d_tolerance_mm"),
                      ("Dc1_Lower","cage_inner_d_tolerance_mm"),
                      ("Bca_Lower","cage_width_tolerance_mm"),
                      ("Bc_Lower","cage_width_tolerance_mm")):
        if key in old:v[label]="-"+text(number(old[key],key))
    for label in ("Dc","Dc1","Bca","Bc"):
        if label in v:v[label+"_Upper"]="0"
    if "cage_pocket_d_upper_tolerance_mm" in old:
        v["Deltac_Upper"]=text(number(old["cage_pocket_d_upper_tolerance_mm"],"pocket tolerance"))
        v["Deltac_Lower"]="0"
    for label,key in (("e_Upper","cage_chamfer_upper_text"),("e_Lower","cage_chamfer_lower_text")):
        if key in old and old[key]!="——":
            v[label]=str(old[key])
    for label,key in (("Cr","dynamic_load_n"),("Cor","static_load_n")):
        if key in old:v[label]=f"{number(old[key],key)/1000:.2f}"
    return overlay(report,v,"robas_acb_SetCADTextValue")

"""RoBAS CRBOptimizer source-based, Cr-only candidate comparison.

The original CRBOptimizer.CalcuRadialStiffness returns constant ZERO, while
GetIndexEvaluationFunctionMax mixes normalized Kr and *raw* dynamic-load N.
Consequently a meaningful two-objective evaluation cannot be migrated
faithfully. This adapter preserves the source's grid and Cr/Cor equations,
explicitly ranks by Cr only, and reports Kr as unavailable (never zero).

Source tables: CylinderRollerDiameterDB.csv, CylinderRollerDB.csv,
圆柱滚子轴承相关系数.csv (the optimizer-specific one-out CSV, NOT the
drawing server's inherited ball-coefficient overload).
No CAD or user-confirmed design is modified by this module.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re

from .contracts import BearingType, ContractError, parse_request
from .drawing_consistency import audit_drawing_design
from .drawing_standards import original_dotnet_math_round
from .drawing_variables import DrawingDataError
from .robas_optimization import OptimizationError, _nearest_diameter
from .robas_sizing import _read


_MODEL = re.compile(r"^(NUP|NU|NJ|NF|N)\d{2,5}$")
_CONFIGS = {"N", "NU", "NJ", "NF", "NUP"}
_PROFILES = {"plain", "chamfered", "crowned"}
_GRADES = {"P0", "P6", "P5", "P4", "P2"}
_MAX_RESULTS = 5


def _finite(value, *, path: str, zero_allowed: bool = False) -> float:
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or not 0 <= value <= 1000 or (not zero_allowed and value == 0):
        raise OptimizationError("Expected finite positive CAD dimension",
                                path)
    return float(value)


def _initial(data) -> dict:
    expected = {
        "bearing_type", "bore_d_mm", "outside_d_mm", "width_mm",
        "configuration", "radial_clearance_mm", "axial_clearance_mm",
        "rib_width_mm", "roller_profile", "roller_end_chamfer_mm",
        "roller_crown_relief_mm", "cage",
    }
    if type(data) is not dict or set(data) != expected:
        raise OptimizationError(
            "CRB initial design must include d/D/B, N-family configuration, "
            "radial and axial clearance, rib width, roller profile and cage",
            "/initial")
    if data["bearing_type"] != BearingType.CYLINDRICAL.value:
        raise OptimizationError("Only cylindrical roller bearings are supported",
                                "/initial/bearing_type")
    if type(data["configuration"]) is not str or data["configuration"] not in _CONFIGS:
        raise OptimizationError("Invalid N/NU/NJ/NF/NUP source configuration",
                                "/initial/configuration")
    if data["cage"] is not None:
        raise OptimizationError(
            "Existing roller window cage is tied to the old roller array. "
            "Disable the cage and recalculate it after confirming the optimized design",
            "/initial/cage")
    if type(data["roller_profile"]) is not str or data["roller_profile"] not in _PROFILES:
        raise OptimizationError("Invalid explicit CAD roller profile",
                                "/initial/roller_profile")
    cleaned = {"bearing_type":data["bearing_type"],
               "configuration":data["configuration"],
               "roller_profile":data["roller_profile"],"cage":None}
    for key in ("bore_d_mm","outside_d_mm","width_mm","rib_width_mm"):
        cleaned[key] = _finite(data[key],path="/initial/"+key)
    for key in ("radial_clearance_mm","axial_clearance_mm",
                "roller_end_chamfer_mm","roller_crown_relief_mm"):
        cleaned[key] = _finite(data[key],path="/initial/"+key,zero_allowed=True)
    if cleaned["bore_d_mm"] >= cleaned["outside_d_mm"]:
        raise OptimizationError("Outer diameter must exceed bore",
                                "/initial/outside_d_mm")
    if 2*cleaned["rib_width_mm"]+2*cleaned["axial_clearance_mm"] >= cleaned["width_mm"]:
        raise OptimizationError("Insufficient axial space for two ribs and end clearance",
                                "/initial/rib_width_mm")
    # Original CRBOptimizer sidewall coefficients are only defined through
    # d<=200 and D<=200; do not silently use the C# default zero above this.
    if cleaned["bore_d_mm"] > 200 or cleaned["outside_d_mm"] > 200:
        raise OptimizationError("Original roller flange coefficient is undefined above 200 mm",
                                "/initial/outside_d_mm")
    return cleaned


def _options(data: dict, configuration: str) -> dict:
    if type(data) is not dict or set(data) != {
        "model", "accuracy_class", "objective",
    }:
        raise OptimizationError(
            "Expected CRB model, accuracy_class and objective",
            "/optimization")
    label, grade, objective = (
        data["model"], data["accuracy_class"], data["objective"])
    if type(label) is not str or not _MODEL.fullmatch(label):
        raise OptimizationError(
            "Use a CRB N/NU/NJ/NF/NUP model label such as NU208",
            "/optimization/model")
    prefix = _MODEL.fullmatch(label).group(1)
    if prefix != configuration:
        raise OptimizationError("Model prefix contradicts selected rib configuration",
                                "/optimization/model")
    if type(grade) is not str or grade not in _GRADES:
        raise OptimizationError("Unknown accuracy class", "/optimization/accuracy_class")
    if objective != "dynamic_load_only":
        raise OptimizationError(
            "Source CRB radial stiffness is unimplemented (returns 0); "
            "a weighted two-objective score cannot be claimed",
            "/optimization/objective")
    return {"model":label,"accuracy_class":grade,"objective":objective}


def _roller_count(dw: float, pitch: float) -> int:
    """CRBOptimizer.CalcuRollerNum, C# truncation toward zero."""
    kz = 1.35 if dw<=6 else 1.225 if dw<50 else 1.3
    return int(math.pi*pitch/(kz*dw))


def _source_roller_length_limit(dw: float, outside: float, width: float,
                                rows: list[dict]) -> float | None:
    """Source intended closest standard Lw for this Dw; never invent length."""
    ratio = .60 if outside<=60 else .73 if outside<200 else .75
    sizes=[x["Lw"] for x in rows if x["Dw"]==dw]
    if not sizes:
        return None
    # RoBAS DetermineRollerLength has a first-row reference/fallback issue.
    # Use the nearest *listed* length for the selected diameter, as with
    # the already audited CAD preliminary-sizing adapter.
    return _nearest_diameter(sizes,ratio*width)


def _flange_factors(bore: float, outside: float) -> tuple[float,float]:
    if bore<=50:
        kd2=.425
    elif bore<=75:
        kd2=.405
    else:
        kd2=.365
    if outside<=25:
        KD2=.425
    elif outside<=50:
        KD2=.405
    else:
        KD2=.365
    return kd2,KD2


def _geometry(initial: dict,dw: float,lw: float,z: int,pitch: float) -> dict | None:
    d,D,B=(initial[x] for x in ("bore_d_mm","outside_d_mm","width_mm"))
    c=initial["radial_clearance_mm"]
    gap=initial["axial_clearance_mm"]
    rib=initial["rib_width_mm"]
    kd2,KD2=_flange_factors(d,D)
    inner_race=pitch-dw-2*c
    outer_race=pitch+dw+2*c
    # These rib tips are the original CRBOptimizer sidewall expressions.
    # The B-Rep's radial clearance moves raceway faces by +/- c.
    inner_tip=pitch-dw+kd2*dw
    outer_tip=pitch+dw-KD2*dw
    if not (d<inner_race<inner_tip<outer_tip<outer_race<D):
        return None
    if not (lw/2+gap<B/2-rib):
        return None
    if pitch*math.sin(math.pi/z)<=dw:
        return None
    params={
        "bore_d_mm":d,"outside_d_mm":D,"width_mm":B,
        "roller_d_mm":dw,"roller_length_mm":lw,
        "pitch_d_mm":pitch,"roller_count":z,
        "configuration":initial["configuration"],
        "radial_clearance_mm":c,"axial_clearance_mm":gap,
        "rib_width_mm":rib,
        "inner_rib_tip_d_mm":inner_tip,
        "outer_rib_tip_d_mm":outer_tip,
        "roller_profile":initial["roller_profile"],
        "roller_end_chamfer_mm":initial["roller_end_chamfer_mm"],
        "roller_crown_relief_mm":initial["roller_crown_relief_mm"],
    }
    request={
        "schema_version":"bearing-cad.request.v1",
        "bearing_type":BearingType.CYLINDRICAL.value,
        "unit":"mm","detail_level":"functional",
        "geometry_strategy":"explicit","parameters":params,
    }
    try:
        parse_request(request)
    except ContractError:
        return None
    return request


def optimize_crb_candidates(*,resources: Path,initial: dict,
                            optimization: dict) -> dict:
    """Source grid and Cr comparison; Kr deliberately unavailable."""
    initial=_initial(initial)
    options=_options(optimization,initial["configuration"])
    root=Path(resources)
    paths={
        name:root/"Resource"/name for name in (
            "CylinderRollerDiameterDB.csv","CylinderRollerDB.csv",
            "圆柱滚子轴承相关系数.csv")
    }
    digests={}
    for name,p in paths.items():
        if p.is_symlink() or not p.is_file():
            raise OptimizationError("Original RoBAS roller CSV is missing: "+name)
        if p.stat().st_size>1_000_000:
            raise OptimizationError("Unusually large RoBAS roller CSV: "+name)
        digests[name]=sha256(p.read_bytes()).hexdigest()
    try:
        diameter_rows=_read(paths["CylinderRollerDiameterDB.csv"],("Dw",))
        length_rows=_read(paths["CylinderRollerDB.csv"],("Dw","Lw"))
        coeff_rows=_read(paths["圆柱滚子轴承相关系数.csv"],("Dw/Dpw","fc"))
    except (OSError,ValueError,UnicodeError) as exc:
        raise OptimizationError("Original RoBAS roller CSV is invalid: "+str(exc)) from exc
    diameter_choices=[x["Dw"] for x in diameter_rows]
    if len(diameter_choices)<5 or any(a>=b for a,b in zip(diameter_choices,diameter_choices[1:])):
        raise OptimizationError("Original roller-diameter CSV must have ordered distinct rows")
    lookup={}
    for x in coeff_rows:
        gamma,fc=x["Dw/Dpw"],x["fc"]
        if gamma in lookup and not math.isclose(fc,lookup[gamma],rel_tol=0,abs_tol=0):
            raise OptimizationError("Conflicting roller source coefficient rows")
        lookup[gamma]=fc
    catalog=audit_drawing_design(
        resources=root,bearing_type=initial["bearing_type"],
        parameters=initial,model_label=options["model"],
        configuration=initial["configuration"],
        accuracy_class=options["accuracy_class"],diameter_series=None)
    d,D,B=(initial[x] for x in ("bore_d_mm","outside_d_mm","width_mm"))
    kwmin,kwmax=(.22,.30) if d<=35 else (.24,.32)
    middle=.5*(d+D)
    max_pitch=.515*(d+D)
    default_dw=_nearest_diameter(diameter_choices,.30*(D-d))
    default_z=_roller_count(default_dw,middle)
    start=max(0,min(diameter_choices.index(default_dw)-2,len(diameter_choices)-5))
    diameter_grid=diameter_choices[start:start+5]
    step_count=min(4096,int(math.floor((max_pitch-middle)/.05+1e-9))+1)
    search_hash=sha256(json.dumps(
        {"initial":initial,"optimization":options},
        sort_keys=True,separators=(",",":"),allow_nan=False
    ).encode("utf-8")).hexdigest()
    all_candidates=[]
    for dw in diameter_grid:
        if not kwmin*(D-d)<=dw<=kwmax*(D-d):
            continue
        max_length=_source_roller_length_limit(dw,D,B,length_rows)
        if max_length is None:
            continue
        valid_lengths=sorted({x["Lw"] for x in length_rows
                              if x["Dw"]==dw and x["Lw"]<=max_length})
        for lw in valid_lengths:
            for z in range(default_z-2,default_z+3):
                if not 2<=z<=64 or z>_roller_count(dw,max_pitch):
                    continue
                for i in range(step_count):
                    pitch=middle+.05*i
                    if pitch>max_pitch+1e-9:
                        continue
                    geometry=_geometry(initial,dw,lw,z,pitch)
                    if geometry is None:
                        continue
                    gamma=original_dotnet_math_round(dw/pitch,2)
                    fc=lookup.get(gamma)
                    if fc is None or fc<=0:
                        continue
                    cr=1.89*fc*lw**(7/9)*z**(3/4)*dw**(29/27)
                    cor=21.6*z*lw*dw
                    if not all(math.isfinite(x) and x>0 for x in (cr,cor)):
                        continue
                    cid=sha256((search_hash+json.dumps(
                        geometry["parameters"],sort_keys=True)
                    ).encode("utf-8")).hexdigest()[:16]
                    all_candidates.append({
                        "candidate_id":cid,"design":geometry,
                        "metrics":{
                            "dynamic_load_n":cr,"static_load_n":cor,
                            "radial_stiffness_source_units":None,
                        },
                        "coefficient_lookup":{
                            "gamma":gamma,"fc":fc,"csv_file":"圆柱滚子轴承相关系数.csv",
                        },
                    })
    if not all_candidates:
        raise OptimizationError(
            "No source-backed CRB candidates satisfy roller dimension, length, "
            "original coefficients and current CAD geometry constraints")
    # Keep genuinely different roller diameter / length / count combinations.
    # Near-identical pitch variants of the same combination should not occupy
    # all five visible recommendation slots.
    all_candidates.sort(key=lambda c:(
        -c["metrics"]["dynamic_load_n"],
        abs(c["design"]["parameters"]["pitch_d_mm"]-middle),
        c["candidate_id"]))
    diverse={}
    for item in all_candidates:
        p=item["design"]["parameters"]
        diverse.setdefault((p["roller_d_mm"],p["roller_length_mm"],p["roller_count"]),item)
    top=list(diverse.values())[:_MAX_RESULTS]
    maximum=all_candidates[0]["metrics"]["dynamic_load_n"]
    for rank,item in enumerate(top,1):
        item["rank"]=rank
        item["score"]=item["metrics"]["dynamic_load_n"]/maximum
    return {
        "schema_version":"bearing-cad.robas-crb-optimization.v1",
        "candidate_only":True,"applied":False,
        "bearing_type":initial["bearing_type"],
        "source_model":options["model"],
        "source_initial_hash":search_hash,
        "optimization":options,
        "objective_status":"CR_ONLY_SOURCE_KR_NOT_IMPLEMENTED",
        "total_valid_candidates":len(all_candidates),
        "total_distinct_structures":len(diverse),
        "candidates":top,
        "source_model_evidence":catalog,
        "source_csv_sha256":digests,
        "source_basis":[
            "RoBAS CRBOptimizer.Optimizer grid and SetCoeffccient",
            "RoBAS CRBOptimizer.CalcuRollerNum and DetermineRollerLength",
            "RoBAS CRBOptimizer.CalcuRadialDynamicLoad and CalcuRadialStaticLoad",
            "RoBAS Resource/CylinderRollerDiameterDB.csv, CylinderRollerDB.csv",
            "RoBAS Resource/圆柱滚子轴承相关系数.csv",
        ],
        "warnings":[
            "SOURCE_CRB_RADIAL_STIFFNESS_RETURNS_ZERO_NOT_VALID_KR",
            "SOURCE_CRB_SCORE_MIXES_NORMALIZED_KR_WITH_RAW_CR_NOT_REPRODUCED",
            "SINGLE_OBJECTIVE_CR_ONLY_PENDING_ENGINEERING_KR_FORMULA",
            "CRB_OPTIMIZER_ROLLER_CSV_DIFFERS_FROM_DRAWING_BALL_CSV",
            "CRB_CAD_CLEARANCE_PROFILE_NOT_IDENTICAL_TO_SOURCE_SIDEWALL_MODEL",
            "SOURCE_ROLLER_LENGTH_NEAREST_LISTED_ENTRY_CORRECTS_LEGACY_FALLBACK",
            "CANDIDATE_ONLY_NOT_BREP_VERIFIED_NOT_MANUFACTURING_APPROVED",
            *catalog.get("warnings",[]),
        ],
    }

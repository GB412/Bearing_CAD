# RoBAS cylindrical roller DATA for N-type bearings

The supported reference is a caller-verified, quasi-static N-type profile.
`CylinderBearingAnalysis.generateStaticAnalysisInputs()` defines the 44
records. The first 10 records and last 32 records match the ball protocol.
`rec 5B.1` and `rec 5B.2` replace `rec 5A`. Use the [ball mapping](robas-solver02-ball-data-mapping.md)
for common column names and the table below for CRB field ownership and units.

## Field sources and N222 check

| Record | C# source and Python mapping | N222 DATA check |
|---|---|---|
| `rec 1`, `rec 2.*`, `rec 3.1`, `rec 3.5` | `BaseSolver` and the original configuration. `Mode=-1` is required. A caller can override `nStps` with a positive integer. Other flags and output names come from the reference. | `Mode=-1` |
| `rec 3.2` | `BaseSolver` plus `CylinderRollerBearing.SetAnalysisValue()`. Require `kUnit=1`, `kBrg=2`; set `nRe` from the design. The four `kFlngInd*` fields are zero in the audited profile. | `nRe=14` |
| `rec 3.3` | `SetAnalysisValue()` assigns the five `kStaticConstraint` values. Retain the remaining switches, including material and life options. Require `kChrn=0` for this plain N analysis. | `1,1,0,1,1` |
| `rec 3.4` | `BaseSolver.GetPltElemInd(nRe)` gives `[1,nRe+1,0,0,0,0]`. Retain the other settings. | `[1,15,0,0,0,0]` |
| `rec 4` | Read confirmed bore, OD and common ring width through the 0.01 mm getter precision. `ShftID` uses rounded bore divided by 5, `HsngOD` uses rounded OD times 1.14. Setters write metres. | `0.11,0.2,0.022,0.228,0.038,0.038` |
| `rec 5B.1` | `bReDia`, `bReLen`, `bReCenLen`, `pitchDia` use `CRBGeometry` getters at 0.01 mm, then `CylinderRoller` and the analysis setters. Both lengths are the original roller length. `bReCrn=1e10` is assigned directly. Keep `bCorRad1/2` and `freeIntCls` from the profile. `analysis_free_clearance_mm`, if supplied, is divided by 1000. | `0.028,1e10,0.028,0.028,0.00025,0.00025,0.155,2e-5` |
| `rec 5B.2` | `raceLandLmt1` and `raceCenLen2` take the rounded `RollerLength` getter directly. Their DATA magnitude is mm. `raceCenLen1`, `raceCrn1`, `raceLandLmt2`, `raceCrn2`, and `rmsAspHt1/2` are retained from `CylinderRollerBearingGeometry` in the reference. | `28,0,0,0.01,28,0,1e-7,1e-7` |
| `rec 7.0` | `SetAnalysisValue()` assigns `kPoctype=0` and `iCageGuide=[1,1,0,0]`. Preserve the other cage switches. | Guide indices `1,1,0,0` |
| `rec 7.1` | Explicit CAD window cage dimensions and radial pocket allowance, or the original analysis cage if CAD omits the cage. `CRBGeometry` derives OD `pitch+0.5*Dw`, ID `pitch-0.45*Dw`, width `0.97*B` from unrounded geometry, then getter rounding. `CylinderPocketCage` derives pocket diameter `1.02*rounded Dw`. `cageCls1` uses the source outer sidewall diameter minus cage OD. `cageCls2` uses cage ID minus the inner race model OD. `bPocCls1` is assigned directly in mm. Preserve `bPocCls2`, `cageAngCut`, and `cageConeAng`. | Cage OD/ID/width `169/142.4/36.86 mm`, two clearances `3.78/15.4 mm`, pocket clearance `0.28` in DATA |
| `rec 7.2.x` × 2 | Both guides use cage OD, full cage width, half that width for position, and outer **ring OD** minus cage OD for clearance. Setters write metres. | Both `0.169,0.03686,0.01843,0.031` |
| `rec 8.*` | `BaseAnalysis` material objects, including rolling element, rings, shaft, housing and cage, plus life factors. Keep the source profile or accept deliberate material-field overrides in DATA units. | Reference tokens unchanged without overrides |
| `rec 9.0`–`rec 9.6`, `rec 11` | `BaseBC` boundary values. Explicit overrides use DATA units such as N, N·m, m, K and rpm. Ring speed updates link `rpm1` to `rpmRange21` and `rpm2` to `rpmRange12` unless an explicit endpoint takes precedence. | Case loads and speeds preserved in replay |
| `rec 9.7`, `rec 10.*` | `BaseBC` coolant properties and `Lubricant` coefficients. Keep the source profile or accept explicit lubricant-field overrides. | Reference tokens unchanged without overrides |

The C# N model has two inner flanges and no outer flange. The solver's
audited N profile has all four flange flags at zero and no separate flange
record. The C# `SingleRowCylinderInnerRace(CRBGeometry)` uses the groove
diameter as `OutsideDiameter` even when drawing two flanges. N222 therefore
uses `155 - 28 = 127 mm` in `cageCls2`. Its separate inner flange tip is
`137.22 mm`. The outer sidewall model value `172.78 mm` is used in `cageCls1`
even though that ring has no physical flange. The CAD `outer_rib_tip_d_mm`
supplies this dimension. The guide clearance uses `200 - 169 = 31 mm`.

## Using the mapping

`update_roller_data()` requires `reference_configuration="N"`, confirmed
from the original model, because the DATA flags alone do not identify the
CAD flange arrangement. In `legacy_data` mode use `request=None`. In
`cad_geometry` mode supply a confirmed `BearingRequest` for an N type with
a plain CAD roller. Differences in assigned fields, including rolling element
count, require `allow_reference_geometry_mismatch=True`. Analysis free
clearance remains a separate setting. For nonzero CAD `radial_clearance_mm`,
the CAD groove diameter used by the cage calculation reflects its one-sided
gap, and the caller must supply an independently confirmed
`analysis_free_clearance_mm` for the solver. The ratio between these two inputs
has not been validated. The solver file does not encode CAD rib width, axial
construction gap, or independent raceway diameters.

Override keys are `(zero_based_record_index, field_name)`. Because CRB has
one additional row, `rec 9.1.1`, `rec 9.1.2`, and `rec 9.2` are indices
30, 31, and 33, respectively. The reference file is read only. The returned
document records its SHA-256 and renders CRLF DATA for a new output file.
Derived CRB numbers use the original .NET Framework writer's 15 significant
digits. Explicit raw DATA overrides retain the caller's representation.

The supported input mapping covers the audited N profile. NU, NJ, NF, NUP,
CAD chamfer/crown profiles, and activated solver flange/crown settings are
rejected. Reference end radii, roughness, land limits and the material and
lubricant models retain their original profile values. Use a profile and
operating data appropriate to the actual design.

## Evidence

The independent local N222 UI case is under
`build/robas-solver01-acceptance-20261108/CRB-ui-run-20261108`.
Its DATA SHA-256 is
`e6c604dd32ceeac659e21edd32215d3f3218e3c53f954a1ef70736a94373d0f5`.
The golden test checks byte-for-byte legacy replay and CAD overlay,
separate hand-traced expected geometry, and preservation of the
source bytes. CI uses portable tests and skips the private golden file when
absent. The Windows probe records executable and output hashes and exit status.
Both generated N222 inputs were run through the original Windows EXE. Each
exited with code 0 and matched the saved UI `OUT.txt` and `a0_Final` hashes.
Solver convergence and engineering validity of individual result tables
require separate result interpretation.

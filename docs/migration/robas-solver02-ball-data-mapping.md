# PR-SOLVER-02: Ball DATA.txt Mapping

This mapping covers the 43 quasi-static records written by
`RoBAS/Core/BallBearing/BallBearingAnalysis.cs`.

Source categories:

- **CAD**: confirmed DGB/ACB values from the current `BearingRequest`.
- **RoBAS-derived**: original source formula, evaluated from CAD geometry.
- **Legacy default**: value initialized in the original C# constructor. The
  implementation preserves these values from an explicitly selected,
  original RoBAS-generated DATA profile rather than silently recreating them.
- **User input**: real operating or installation data; never inferred from CAD.
- **Gap**: no reliable source in the current CAD request or audited source.

| # | Record and field order | Source and notes |
|---:|---|---|
| 1 | `Mode,kDCR,kDOF,klcOpt,kFnOpt,kPrtOpt,kPrtFreq,kPltFreq,kAGraf,kLifeFreq,kTherm,maxStps,nStps,intMet` | Legacy default; `Mode=-1` is fixed for quasi-static. `nStps` is the only directly editable BaseSolver field in this record. |
| 2 | `stpInit,stpMin,stpMax,fTime,Tol,qFac` | Legacy `BaseSolver` defaults retained from the selected original DATA profile. |
| 3 | `kFD11,kFD21,kFD31,kFD12,kFD22,kFD32,kMD11,kMD21,kMD31,kMD12,kMD22,kMD32` | Legacy defaults; custom load/moment control flags require explicit override. |
| 4 | `finName,pltNames1..pltNames9` | Legacy output filename defaults. |
| 5 | `runId` | Caller-provided run identifier. |
| 6 | `kUnit,kBrg,nRe,nCseg,kRaceFlex,kReGeoImp,kRaceGeoImp1,kRaceGeoImp2,kFlngInd11,kFlngInd12,kFlngInd21,kFlngInd22` | This mapping accepts the audited `kUnit=1`, `kBrg=1` profiles. Both ball `SetAnalysisValue` methods assign `kBrg` and `nRe`. A change in ball count requires geometry mismatch acknowledgement. |
| 7 | `kStaticConstraint[5],kAngVel,kStif,kChrn,kReMat,kRaceMat1,kRaceMat2,kHsngMat,kShftMat,kLifeCons` | Legacy solver defaults; material switches must agree with selected material profile. |
| 8 | `kRotLoad,kRotFrame,kReIP,kRaceIP1,kRaceIP2,kNumPltElem,kPltElemInd[6]` | Six indices are assigned from `GetPltElemInd(nRe)`: `[1,nRe+1,0,0,0,0]`. |
| 9 | `kCoolant,kBaseTemp,kHTC,kGeoMod,kMatPropMod` | Legacy defaults; changed thermal boundary settings require explicit values. |
| 10 | `brgBore,brgOD,shftID,hsngOD,raceWidth1,raceWidth2` | Bore and OD first pass through `BaseInnerRace.InsideDiameter` / `BaseOuterRace.OutsideDiameter` getters (0.01 mm), then convert to m. `shftID` is the rounded bore divided by 5; `hsngOD` is the rounded outer diameter multiplied by 1.14. Both race widths use the 0.01 mm `Width` getter. |
| 11 | `bReDia,pitchDia,freeConAngDeg,freeIntCls,raceCurFac1,raceCurFac2,shoulderDia1,shoulderDia2,shimThickness1,shimThickness2,rmsAspHt1,rmsAspHt2` | CAD geometry mode uses rounded ball (0.001 mm), pitch (0.01 mm), contact angle (ACB getter: 0.01 degree), and source-family race getter values. DGB sidewalls and ACB outer sidewall use 0.01 mm; ACB inner sidewall uses 0.1 mm. CAD curvature coefficients are radius/ball diameter and are distinct from legacy `BallBearingGeometry` defaults 0.52/0.54; legacy mode preserves the selected DATA values. The two modes must not be represented as numerically equivalent. DGB/ACB `SetAnalysisValue` does not assign internal clearance, either shim field, or roughness, so CAD mode preserves those values from the selected DATA profile. Explicit `analysis_parameters_mm` values override these fields and are converted from mm to the DATA metre units. C# `ShimThickness1` reads/writes `freeIntCls`; DATA serializes the backing fields separately. |
| 12 | `kPoctype,kCagePocImp,kCageGsImp,kRaceGsImp,kPocHydro,kGsHydro,kCageMat,kCageIP,nGL,iCageGuide[4]` | `kPoctype=0` is explicitly assigned by both ball `SetAnalysisValue` methods; remaining fields retain `BaseGeometry` values. |
| 13 | `cageDia1,cageDia2,cageWidth,cageCls1,cageCls2,bPocCls1,bPocCls2,cageAngCut,cageConeAng` | Getter/setter order matters: BallDiameter getter to 0.001 mm; PocketDiameter getter to 0.1 mm; guide gap; OutsideDiameter/InsideDiameter getters to 0.01 mm; `CalculateWidth`; Width getter to 0.01 mm. DGB CageCls2 subtracts inner sidewall; ACB subtracts inner race outside diameter. DGB writes `BPocCls1` property (mm to m); ACB writes `bPocCls1` backing field directly (DATA keeps the mm magnitude). Both leave `bPocCls2`, `cageAngCut`, and `cageConeAng` in the reference profile. |
| 14 | `cageGsDia1,cageGsWidth1,cageGsPos1,cageGsCls1` | Both families use rounded cage inside diameter, `0.22*cage.Width`, `0.5*cage.Width`, and cage inside minus inner race outside diameter. |
| 15 | `cageGsDia2,cageGsWidth2,cageGsPos2,cageGsCls2` | Same assignments as record 14 for guide 2. |
| 16 | `density,elasticModules,poissonRatio,thermalExpansion,specificHeat,conductivity,strainLimit,hardness,wearCoeff,misis` (rolling element) | Original `Material` defaults or explicitly selected local material entry. |
| 17 | Same 10 material fields (outer race) | Original default/selected material. |
| 18 | Same 10 material fields (inner race) | Original default/selected material. |
| 19 | `density,elasticModules,poissonRatio,thermalExpansion,conductivity` (shaft) | Original default/selected material; current CAD has no shaft material. |
| 20 | Same 5 material fields (housing) | Original default/selected material; current CAD has no housing material. |
| 21 | Same 10 material fields (cage) | Original default/selected material; must match record 12 cage material code. |
| 22 | `sProb,brgWbDis` | Original `Material` global defaults. |
| 23 | `fcO1,fcLP1,shExLP1,depExLP1,fcGZ1,shExGZ1,fcIH1,shExIH1,depExIH1,wbDis1` (outer race) | Original material life properties. |
| 24 | Same 10 life fields (inner race) | Original material life properties. |
| 25 | Same 10 life fields (rolling element) | Original material life properties. |
| 26 | `rmsAspSlp1,shearLmt1,aspTrac1,facMat1,facCont1,facProc1,facMatLF1,facProcLF1,hardnessLF1` (outer race) | Original material contact/life defaults or selected material entry. |
| 27 | Same 9 fields (inner race) | Original material contact/life defaults or selected material entry. |
| 28 | `facMatRe,facContRe,facProcRe,facMatLFre,facProcLFre,hardnessLFre` | Original rolling-element material contact/life defaults. |
| 29 | `roomTemp,raceFit1,raceFit2,angVelOrt,resStress1,resStress2,facStrLimit` | User installation/operating inputs; explicit legacy profile defaults are available. Temperatures are K, fits are m, orientation is degrees. |
| 30 | `appLoadX,appLoadY,appLoadZ,appDispX,appDispY,appDispZ` | User-supplied force components and prescribed displacement; never inferred from CAD. |
| 31 | `appMomY,appMomZ,appMis11,appMis21,appMis12,appMis22,rpm1,rpm2` | User-supplied moments, misalignment and ring speeds. The source protocol has no `appMomX` field. |
| 32 | `hsngTemp,shftTemp,raceTemp1,raceTemp2,reTemp,cageTemp` | User-supplied temperatures or explicit legacy profile defaults; K in DATA. |
| 33 | `pctDisp,rpmRange11,rpmRange21,rpmRange12,rpmRange22` | `BaseBC.Rpm1` also sets `rpmRange21`, and `BaseBC.Rpm2` also sets `rpmRange12`. An explicitly supplied scan endpoint takes precedence. The remaining scan settings come from the reference profile or explicit overrides. |
| 34 | `pocLubFilm,wvRatio,avRatio,cageGcPosX,cageGcPosY,cageGcPosZ,cageAngPosX,cageAngPosY,cageAngPosZ` | Legacy defaults or explicit lubricant/initial-condition inputs; cage initial position is not in CAD. |
| 35 | `baseTemp,cFlowRate,cPres,reHTC,cageHTC,aveTime,skipTime` | Legacy thermal defaults or explicit boundary inputs. |
| 36 | `xRo,xMu,xCp,xK` | Original lubricant profile properties or explicit override. |
| 37 | `kTrac,kTracType,kCPTrac,kCPTracType,kCRTrac,kCRTracType,kRFTrac,kRFTracType,kRRTrac,kRRTracType,iTherm` | Original lubricant model defaults or selected lubricant profile. |
| 38 | `reRaceTC1,reRaceTC2,reRaceTC3,reRaceTC4` | Original lubricant profile. |
| 39 | `reRaceFilm,strParam` | Original lubricant profile. |
| 40 | `reCageTC1,reCageTC2,reCageTC3,reCageTC4,reCageFilm` | Original lubricant profile. |
| 41 | `cageRaceTC1,cageRaceTC2,cageRaceTC3,cageRaceTC4,cageRaceFilm` | Original lubricant profile. |
| 42 | `pocVis,gsVis` | Original lubricant profile. |
| 43 | `gravityVecX,gravityVecY,gravityVecZ` | Legacy gravity default or explicit user vector. |

## Verified gaps and comparison limits

- The golden 2026-11-08 DATA files are independent real RoBAS runs. The DGB
  sample's groove/shoulder geometry does not equal the current 6008 CAD fixture;
  ACB also has distinct geometry. They are protocol/configuration baselines,
  not interchangeable designs.
- `BallBearingGeometry` defaults to curve coefficients `0.52/0.54`; neither
  ball-bearing `SetAnalysisValue` overwrites these fields. CAD geometry mode
  derives coefficients from confirmed CAD groove radii divided by ball size.
  It does not claim to reproduce original DATA coefficients.
- Race geometry is serialized from the public C# getter values, not raw
  constructor backing fields. In particular ACB inner-race `SidewallDiameter`
  is rounded to 0.1 mm before downstream analysis reads it; its `OutsideDiameter`
  getter independently rounds to 0.01 mm. Shaft/housing dimensions derive from
  the already-rounded race bore/OD values.
- The ACB CAD request has two shoulder diameters on each race, but DATA has one
  analysis sidewall diameter per race. The caller must explicitly identify the
  two sidewall values used by the original analysis model; averaging the CAD
  shoulders is not justified by the source.
- The current CAD contract does not contain shaft/housing material or measured
  operating conditions. This API therefore requires an explicit original DATA
  profile; caller-supplied field overrides update that profile in memory.
- The DATA output proves protocol serialization only. Solver convergence and
  engineering correctness are outside this PR.

## Python API

`update_ball_data` requires `geometry_mode`. `legacy_data` accepts no CAD
request and retains source geometry. `cad_geometry` requires a `BearingRequest`,
the analysis inner-race outside diameter, ACB analysis sidewall diameters, and
`allow_reference_geometry_mismatch=True` when the selected DATA geometry differs
from CAD. This makes reuse of the reference's material, lubricant and operating
profile explicit. The returned document records the geometry mode and source
DATA SHA-256.

`operating_updates`, `solver_updates`, `material_updates`, and
`lubricant_updates` use `(zero_based_record_index, field_name)` keys.
Values use the serialized DATA units, such as N, N·m, m, K, and rpm for
force, moment, displacement, temperature, and ring speeds. When setting a
ring speed through `update_ball_data`, the matching scan endpoint follows
the speed unless explicitly supplied. `BallDataDocument.with_updates` edits
serialized fields directly and applies no setter side effects.
`solver_updates` is limited to `(0, "nStps")`. The original reference is never
changed; write `document.render()` to a new path after reviewing the profile.

## Local Golden Case Traces

The 2026-11-08 DGB DATA source has SHA-256
`b6610d150b0b8b05f0d024fe0c6fb90c1d4b270d5ef20f95398d48a6aa165a0f` and uses
ball 8.334 mm, pitch 54 mm, width 15 mm, and outer/inner sidewalls 59.02/49 mm.
Tracing the original C# getter sequence yields pocket 8.5 mm, guide gap
0.0996 mm, cage OD/ID/width 58.92/53.92/11 mm, DGB CageCls2 4.92 mm, pocket
clearance 0.083 mm, and guide width/position/clearance 2.42/5.5/4.92 mm.

The 2026-11-08 ACB DATA source has SHA-256
`9cb4e0e9b74e4e13a056a1e1afe2fbfa425645c8e65865b63c2fd3d3095617ef` and uses
ball 11 mm, pitch 82.5 mm, angle 25 degrees, width 18 mm, and sidewalls
89.15/75.9 mm. Its C# cage values are pocket 11.2 mm, guide gap 0.12 mm, cage
OD/ID/width 89.03/82.43/13.7 mm, ACB CageCls2 6.53 mm, direct-field
`bPocCls1=0.1`, and guide width/position/clearance 3.014/6.85/6.53 mm. These
original geometries differ from current CAD fixtures; they validate source
formulas and are not expected to match a different CAD geometry's full DATA.

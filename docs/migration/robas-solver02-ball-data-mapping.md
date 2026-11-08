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
| 6 | `kUnit,kBrg,nRe,nCseg,kRaceFlex,kReGeoImp,kRaceGeoImp1,kRaceGeoImp2,kFlngInd11,kFlngInd12,kFlngInd21,kFlngInd22` | Legacy defaults; `nRe` from confirmed CAD ball count. |
| 7 | `kStaticConstraint[5],kAngVel,kStif,kChrn,kReMat,kRaceMat1,kRaceMat2,kHsngMat,kShftMat,kLifeCons` | Legacy solver defaults; material switches must agree with selected material profile. |
| 8 | `kRotLoad,kRotFrame,kReIP,kRaceIP1,kRaceIP2,kNumPltElem,kPltElemInd[6]` | Legacy defaults; plot indices derived from `nRe` using `BaseSolver.GetPltElemInd`. |
| 9 | `kCoolant,kBaseTemp,kHTC,kGeoMod,kMatPropMod` | Legacy defaults; changed thermal boundary settings require explicit values. |
| 10 | `brgBore,brgOD,shftID,hsngOD,raceWidth1,raceWidth2` | Bore, OD and widths from CAD (mm converted to m). Shaft ID and housing OD follow legacy `bore/5` and `OD*1.14`; these are source formulas, not CAD dimensions. |
| 11 | `bReDia,pitchDia,freeConAngDeg,freeIntCls,raceCurFac1,raceCurFac2,shoulderDia1,shoulderDia2,shimThickness1,shimThickness2,rmsAspHt1,rmsAspHt2` | CAD ball diameter, pitch diameter, contact angle, groove radii and shoulders are converted to protocol units. Curvature coefficients are derived as radius/ball diameter. Clearance and shim use legacy defaults unless explicitly supplied. Roughness uses the `BallBearingGeometry` defaults. C# shim accessors need care: `ShimThickness1` reads/writes `freeIntCls`. |
| 12 | `kPoctype,kCagePocImp,kCageGsImp,kRaceGsImp,kPocHydro,kGsHydro,kCageMat,kCageIP,nGL,iCageGuide[4]` | Legacy `BaseGeometry` defaults; cage material must match record 21. |
| 13 | `cageDia1,cageDia2,cageWidth,cageCls1,cageCls2,bPocCls1,bPocCls2,cageAngCut,cageConeAng` | Legacy `StraightPocketCage` formula, not the CAD stamped cage. Public properties pass mm: `pocket=1.004*ball+0.12`, guide gap `0.6*(pocket-ball)`, outside `outerSidewall-guideGap`, inside `outside-0.6*ball`; width follows `CalculateWidth`. Convert outputs to m. |
| 14 | `cageGsDia1,cageGsWidth1,cageGsPos1,cageGsCls1` | `SetAnalysisValue`: guide diameter is cage inside diameter, guide width `0.22*cageWidth`, position `0.5*cageWidth`, clearance is cage inside minus inner-race sidewall. |
| 15 | `cageGsDia2,cageGsWidth2,cageGsPos2,cageGsCls2` | Same as record 14 for the second guide. |
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
| 33 | `pctDisp,rpmRange11,rpmRange21,rpmRange12,rpmRange22` | Legacy scan defaults or explicitly supplied speed ranges; not inferred from a single speed. |
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
- `ACBGeometry` constructs groove radii with coefficients `0.525/0.515`, while
  the audited ACB DATA has coefficient fields `0.52/0.54`. This discrepancy
  must remain visible in provenance and must not be normalized away.
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

`update_ball_data` reads an original, caller-selected DGB/ACB DATA file and
returns a new in-memory document. `operating_updates`, `solver_updates`,
`material_updates`, and `lubricant_updates` use `(zero_based_record_index,
field_name)` keys. `solver_updates` is limited to `(0, "nStps")`, the only
solver field marked editable in the original DATA-writing path. The explicit reference file supplies any values not
overridden; it is never changed. For ACB, pass
`analysis_shoulder_diameters_mm=(inner_sidewall, outer_sidewall)` from the
original bearing analysis model. The caller writes `document.render()` to a
new path after reviewing the selected source profile.

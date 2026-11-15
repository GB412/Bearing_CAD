# RoBAS quasi-static result mapping

## Source audit and supported scope

`Core/BallBearing/BallBearingAnalysis.cs` and
`Core/RollerBearing/CylinderRollerBreaing/CylinderBearingAnalysis.cs`
are byte-identical in the two local RoBAS source copies. The Windows DGB,
ACB and N222 golden runs all print `Version (RoBAS 8.11)` in `OUT.txt`.
The `ball` output family covers DGB and ACB. The `roller` family has local
golden coverage for N222. Neither output family code establishes an exact
bearing model or flange arrangement.

| Output evidence | Meaning and mapping | Python unit | DGB / ACB / N222 |
|---|---|---|---|
| `OUT.txt`, echoed `rec 1` and `rec 3.2` | Check `Mode=-1`, unit code, bearing family code and `nRe` against the paired `DATA.txt`. This limited echo leaves the source binding unverified. The same-run probe report provides file hashes for verification. | codes / count | Yes |
| `OUT.txt`, `RE ... Contact Angle ... Contact Deflection ... Contact Load ... Contact Stress ... Race Flexing` | Both C# `processAnalysisResultDataTxt` implementations read the first matching table. Columns 1–8 after the RE index are angle, deflection, load and stress, each outer then inner. Require both unit and race headers and exactly `nRe` indexed rows. | deg; mm (`m × 1000`, round to 5 decimals as C#); N; MPa (`Pa × 1e-6`) | Yes |
| Same contact table, final two columns | `Race Flexing` is printed in metres. C# does not map these columns in the contact reader. Now exposed as `race_flexing` using the printed units. | m as printed | Yes |
| `OUT.txt`, `Race Angular Velocities / Relative Race Displacements / Stiffness` | Units and axes come directly from the three printed table headings. Rows are sweep points with both ring speeds, x/y/z relative displacements and XX/YY/ZZ stiffness. The audited C# result reader does not extract this table. Do not collapse sweep rows into a single operating point or infer axial/radial axes. | rpm, m, N/m | Yes |
| `OUT.txt`, `Total Power Loss (W)` and `Internal Clearance (m)` | Both C# readers select the last token of the matching line. Report the printed values. Keep the sign on clearance. | W, m | Yes |
| `OUT.txt`, `Time Average Parameters` footer | Use the observed terminal data row to detect truncated reports. The footer provides structural evidence. | — | Yes |
| `OUT.txt`, life tables | Fixed-width model tables now retain finite, nonfinite and blank cells independently. Neither audited C# parser reads these life tables. Model applicability remains unverified; these are printed model outputs, not accepted life predictions. | h for basic / modified life; dimensionless for modification factors | Printed values only |
| `a0_Final` | `BaseSolver.finName` assigns this name and `rec 2.3` serializes it. Both C# `DeleteFile` implementations remove old copies. The audited result readers take their engineering fields from OUT. Observed `a0_Final` is whitespace-delimited numeric text, with a two-token first line and packed numeric rows. Its vector ordering, units and purpose beyond the configured final output are unverified. Preserve file evidence when present. | Unknown | Evidence only |

### Extended engineering fields (2026-11-15)

Both C# `processAnalysisResultDataTxt` implementations read the following
fields. Their columns and units have now been checked against all three local
goldens. These results are added to the existing v1 response without changing
input generation or solver execution. All contact fields have selectable
curves and tables in the workbench. New paired metrics retain their OUT line.

| Added field | OUT section and C# assignment |
|---|---|
| Contact dimensions | `Major Half Width` and `Minor Half Width` in m, assigned to `cMajorHalf` and `cMinorHalf` for both races. |
| Rolling velocity and spin/roll ratio | `Rolling Velocity` in m/s and `Spin/Roll` as a ratio, assigned to `cVelocity` and `cOuterRaceSpinRollRatio` / `cInnerRaceSpinRollRatio`. |
| Film thickness, maximum slip and traction | `Max Slip Velocity / Trac Coeff / Lubricant Film`, assigned to `cMaxSlipVelocity`, `cTracCoeff` and the two `FilmThickness` properties. C# multiplies the film thickness in m by `1e6` and rounds to four decimals in µm. The adjacent isothermal film table is a separate quantity. |
| Contact loss, temperature rise and film temperature | `Contact Loss` (W), `Contact Temp Rise` (K) and `Lub Film Temp` (K). C# reads the rise directly and converts absolute film temperature to °C with `K - 273.15` and two decimal places. |
| Computed stress and load capacities | `Computed Dynamic Capacities at Heaviest Loaded Rolling Element`. All eight fixed-width slots are retained per model, four Pa columns then four N columns. Blank cells are `NOT_REPORTED`, not zero. Applicability stays unverified; these are not CAD optimizer Cr or maximum contact stress. |

The two orbital tables also populate `rolling_elements`: angular position in
degrees, axial position in metres, relative orbital position in radians,
Mis/Skew angles, spin amplitude in rpm, Theta/Phi in degrees, orbit rpm,
centrifugal and moving-frame forces, wear rate, bulk temperature and HTC.
The C# property name `cRadicalPosition` is misleading for the printed relative
orbital position column: we retain the OUT unit `rad`, not an invented radius.

Other paired columns are retained using their printed meanings: contact edge
depth / chordal distance, isothermal film (separate from net lubricant film),
film reduction factor, stress-slip product / normalized position, contact
temperature and load-slip integral. Absolute contact / film temperatures are
converted from K to °C, with two decimals. Temperature rises remain K.
N222 prints 0 K for lubricant film temperature. It is `INVALID`, `value=null`,
with raw zero and reason `NONPOSITIVE_ABSOLUTE_TEMPERATURE`; its cause is unknown.
It must not be presented as a real -273.15°C oil temperature.

`additional_sections` reports each of six extended sections as `PARSED` or
`NOT_PRESENT`. Absent optional sections preserve compatibility with older /
limited outputs; present malformed tables raise a line-specific error. This
does not change `PARSED_SUPPORTED_SECTIONS` into a convergence claim.
`model_tables` retains the four capacity / life tables with explicit
`UNVERIFIED_MODEL_APPLICABILITY`. `VALID` means the printed numeric value is
finite, not that a model is applicable or an engineering check passed.

`raw_report` contains the original text from Rolling Element Parameters to
the end, with its starting physical line. This makes supplemental slip and
traction curves, race/cage and applied-parameter tables inspectable, without
guessing typed meanings for every column. DATA echo is excluded. Text is
rendered as text, never HTML; original files and their hashes remain untouched.
`a0_Final` vector ordering and auxiliary-file column meanings remain unverified.

**Original summary-column defect:** `FindId(..., 5, 1)` selects the `Original LP`
capacity row. `StringLineToStrings` removes blank fields and splits the model
name into `Original`, `LP`. C# assigns tokens 2/3 to `StressCapacities` and
`LoadCapacities`; in the checked output these are the two printed **load**
capacities, e.g. DGB 12420 / 5629 N. We do not reproduce this unit / label
mismatch or claim a maximum contact stress from it. All models and columns
are shown with their actual printed units instead.

## N222 nonfinite evidence

Line numbers count physical CRLF lines, including form-feed lines. All five
`NaN` tokens occur in `OUT.txt`, in rows labelled `Original LP`.

| OUT line | Table | Column containing `NaN` |
|---:|---|---|
| 689 | Modified Life | Tallian Outer Race |
| 698 | Life Modification Factors | Tallian Outer Race |
| 698 | Life Modification Factors | Tallian Bearing |
| 698 | Life Modification Factors | STLE Outer Race |
| 698 | Life Modification Factors | STLE Bearing |

The `Roll Elem` cells in those rows are blank. Fixed-column positioning
keeps those blanks from shifting the mapped columns. No NaN or Infinity
tokens were found in the N222 `a0_Final` or the archived auxiliary files
`a1_Outer`, `a2_Inner`, `a7_LifePow`, `a8_Animati`, and `a9_User`.
The C# result readers contain no handling of
these life-table tokens. The local evidence does not distinguish an
inapplicable model from a numerical failure. A nonfinite value is `INVALID`
with `value=null`, original token and line retained, and cause `UNKNOWN`.
The blank life cells and finite `9.999E+99` values have unverified semantics.

`Solve()` waits for the process and marks `BlnStaticAnalysisSuccess` after
the OUT reader returns. The audited code does not check the process exit
code or read an independent numerical convergence flag. The three saved
OUT files contain no verified convergence status. Printed error limits
are input settings. Execution status, supported-table integrity, and
metric validity are separate from convergence (`UNKNOWN`).

## Python boundary for SOLVER-05

`parse_static_results(run_directory, *, family, probe_report=None)` reads
paired `DATA.txt` and `OUT.txt` and records SHA-256 from the bytes parsed.
`a0_Final` is optional evidence. Without a report, `execution.status` is
`UNKNOWN` and `source_binding.status` is `UNVERIFIED` with evidence
`LIMITED_OUT_ECHO`. Matching mode, unit, bearing family and element count can
also occur in reports from different designs or operating conditions.

SOLVER-05 must pass the report returned by `run_probe()` for the **same run**
and require `source_binding.status=HASH_VERIFIED`. The parser checks the
family, the complete SHA-256 of `DATA.txt` and `OUT.txt`, and the presence and
hash of `a0_Final` when tracked. A report supplied by a caller is not an
authenticated proof of execution. The API should use its own run report.

| `solver_executed` | `process_exit_code` | Allowed probe `output_status` |
|---|---|---|
| `true` | integer `0` | `OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF` or `OUTPUT_ABSENT_OR_INVALID` |
| `true` | nonzero integer | `PROCESS_NONZERO_EXIT` |
| `true` | `null` | `PROCESS_TIMEOUT` |
| `false` | `null` | `PROCESS_START_FAILED` or `NOT_EXECUTED` |

Missing fields and contradictory combinations raise `ResultParseError`.
`output_status=PARSED_SUPPORTED_SECTIONS` covers only the supported
sections' structure and extraction. Individual metrics can still be
`INVALID`, and `convergence.status` remains independent. The parser provides
no whole-report validity or engineering approval. Each metric contains
`value`, `unit`, `status` and
the original `raw` token. `contacts` and `stiffness_sweep` include physical
source line numbers. `nonfinite_evidence` preserves the raw source line
and column, and includes life model labels when the audited table header
identifies them. Missing files, mismatched headers and truncated required
tables raise `ResultParseError` with
`filename` and a physical `line` when known. A caller can serialize the
result with `json.dumps(result, allow_nan=False)`.

The parser accepts the audited report layout. Other RoBAS versions, report
options that omit required sections, and untested combinations of inputs
have no compatibility claim.

## Independent Windows comparison

These are printed OUT values transcribed from the preserved Windows runs,
with the documented C# conversions applied independently. Local golden
tests compare these references with the parser output. Absolute and relative
tolerances of `1e-12` accommodate binary representation and arithmetic of
the printed decimal values. They are not solver error tolerances or evidence
of precision beyond the digits printed by RoBAS.

| Case | Contact rows | RE #1 outer / inner angle (deg) | Deflection (mm) | Load (N) | Stress (MPa) | Sweep point 5 z displacement (m) / ZZ stiffness (N/m) | Power (W) / clearance (m) |
|---|---:|---|---|---|---|---|---|
| DGB | 11 | 12.54 / 12.83 | 0.02008 / 0.02376 | 2251 / 2202 | 2593 / 3402 | 5.347e-6 / 2.920e8 | 3092 / -5.023e-5 |
| ACB | 20 | 19.01 / 23.63 | 0.01035 / 0.01077 | 954.5 / 775.6 | 1635 / 1968 | 5.018e-6 / 3.372e8 | 400.7 / 6.850e-5 |
| N222 | 14 | 0 / 0 | 0.01735 / 0.01322 | 16750 / 9001 | 1103 / 1138 | 6.457e-7 / 3.097e9 | 226.8 / -5.985e-5 |

All three bound Windows probe reports record a zero exit. Convergence is
`UNKNOWN` in all three. Private golden files stay local. CI runs synthetic
format and failure tests and skips local golden cases when files are absent.

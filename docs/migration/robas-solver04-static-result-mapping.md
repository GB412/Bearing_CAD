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
| `OUT.txt`, echoed `rec 1` and `rec 3.2` | Check `Mode=-1`, unit code, bearing family code and `nRe` against the paired `DATA.txt`. The full input echo uses limited print precision. A supplied probe report binds the files by SHA-256. | codes / count | Yes |
| `OUT.txt`, `RE ... Contact Angle ... Contact Deflection ... Contact Load ... Contact Stress ... Race Flexing` | Both C# `processAnalysisResultDataTxt` implementations read the first matching table. Columns 1–8 after the RE index are angle, deflection, load and stress, each outer then inner. Require both unit and race headers and exactly `nRe` indexed rows. | deg; mm (`m × 1000`, round to 5 decimals as C#); N; MPa (`Pa × 1e-6`) | Yes |
| Same contact table, final two columns | `Race Flexing` is printed in metres. C# does not map these columns in the contact reader. Retain the source file and row location. | m as printed | Evidence only |
| `OUT.txt`, `Race Angular Velocities / Relative Race Displacements / Stiffness` | Units and axes come directly from the three printed table headings. Rows are sweep points with both ring speeds, x/y/z relative displacements and XX/YY/ZZ stiffness. The audited C# result reader does not extract this table. Do not collapse sweep rows into a single operating point or infer axial/radial axes. | rpm, m, N/m | Yes |
| `OUT.txt`, `Total Power Loss (W)` and `Internal Clearance (m)` | Both C# readers select the last token of the matching line. Report the printed values. Keep the sign on clearance. | W, m | Yes |
| `OUT.txt`, `Time Average Parameters` footer | Use the observed terminal data row to detect truncated reports. The footer provides structural evidence. | — | Yes |
| `OUT.txt`, life tables | Use the printed section, model and fixed-column headings to locate nonfinite tokens. Neither audited C# parser reads these life tables. The explanation and physical usability of the values remain unresolved. | h for modified life; dimensionless for modification factors | Evidence only |
| `a0_Final` | `BaseSolver.finName` assigns this name and `rec 2.3` serializes it. Both C# `DeleteFile` implementations remove old copies. The audited result readers take their engineering fields from OUT. Observed `a0_Final` is whitespace-delimited numeric text, with a two-token first line and packed numeric rows. Its vector ordering, units and purpose beyond the configured final output are unverified. Preserve file evidence when present. | Unknown | Evidence only |

Other OUT tables, including loads in inertial and body-fixed frames, detailed
film and thermal quantities, and dynamic capacities, remain available as
original-file evidence. They are outside the first typed mapping.

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
`a0_Final` is optional evidence. An explicit SOLVER-01 report can supply
execution state after verifying its input and tracked output hashes.
Without a report, execution state is `UNKNOWN`. Missing files, mismatched
protocol headers and truncated required tables raise a diagnostic error.
The result contains only JSON-safe data. Finite metrics represent parsed
solver output with verified field mapping, with convergence assessed separately.

Pass the report object returned by `run_probe()` when available. The parser
checks that the report's family and input/output hashes match the files.
`execution.status` distinguishes unknown, startup failure, timeout, zero
exit and nonzero exit. `output_status=PARSED_SUPPORTED_SECTIONS` records
format checks for the supported sections. It does not certify the whole
report or the physics. Each metric contains `value`, `unit`, `status` and
the original `raw` token. `contacts` and `stiffness_sweep` include physical
source line numbers. `nonfinite_evidence` preserves the raw source line
and column, and includes life model labels when the audited table header
identifies them. File or schema failures raise `ResultParseError` with
`filename` and a physical `line` when known. A caller can serialize the
result with `json.dumps(result, allow_nan=False)`.

The parser accepts the audited report layout. Other RoBAS versions, report
options that omit required sections, and untested combinations of inputs
have no compatibility claim. With no probe report, the echo checks the
mode, family and rolling-element count. It does not bind all operating
inputs to the OUT file at full precision.

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

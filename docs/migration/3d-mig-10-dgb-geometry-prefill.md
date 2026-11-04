# PR-02 · RoBAS DGBGeometry 初始几何预填

## Scope

This change adds an opt-in, source-backed initial-geometry preset for the existing deep-groove CAD workbench. It does not change the B-Rep builder, the request schema, the explicit CAD API contract, or any optimizer/solver.

The UI calls POST /api/v2/cad/sizing/dgb-geometry. The endpoint is loopback-only and same-origin, and is enabled only when --robas-resources points to a resource tree containing Resource/BallDB.csv.

## Exact legacy path selected

The preset follows the parameterized DGBGeometry(outsideDia, insideDia, width) constructor:

- RoBAS/Core/BaseOptimizer.cs:27-49: choose the nearest ball diameter from BallDB.csv using relative ratio error.
- RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBGeometry.cs:53-92: pitch circle, 186-degree ball-count expression, 0.51/0.53 groove coefficients, groove diameters, sidewall diameters, and DGBGeometry cage envelope.
- RoBAS/Core/BallBearing/DeepGroveBallBearing/DGBOptimizer.cs:566-604: C# integer-division radial-clearance table, returned in millimetres.

Source archive SHA-256: 69b39ec937bcc942d223601995c7279573c629d81c652e56a3146b4f2c95d23d.

The supplied RoBAS_Resources/Resource/BallDB.csv SHA-256 is 3c0c4d6f589de2cc985a14d074389598192e1fa9e5f06477453c706f6f142b0a.

## Reproducible example

For d=40, D=68, B=15 mm, the supplied BallDB table selects Dw=8.33438 mm. The selected DGBGeometry path yields:

| Field | Value |
|---|---:|
| Ball diameter | 8.33438 mm |
| Pitch diameter | 54 mm |
| Ball count | 11 |
| Inner groove radius | 4.2505338 mm |
| Outer groove radius | 4.4172214 mm |
| Radial clearance used in outer groove diameter | 0.013 mm |
| Inner shoulder diameter | 48.999372 mm |
| Outer shoulder diameter | 59.013628 mm |
| DGBGeometry cage inner diameter | 49.97935944 mm |
| DGBGeometry cage outside diameter | 57.83335544 mm |
| DGBGeometry cage width | 14.25 mm |

The UI applies the cage envelope only when simplified_annular is selected. It never writes these values into the stamping_double_half board, rivet, or pocket fields. The simplified-cage pocket clearance remains an explicit CAD-only input.

## Deliberate boundaries and corrections

- This is not DGBOptimizer.Optimizer. The optimizer searches candidate ball diameters, ball counts, pitch circles and load/stiffness objectives using model-series coefficients and clearance settings. None of those optimization decisions is claimed here.
- This is not the conflicting DeepGrooveBallBearing(string,...) scalar constructor, which contains a different pitch expression and 0.52/0.54 curvature defaults. The preset explicitly selects the DGBGeometry constructor path.
- The 186-degree expression is copied as a legacy selection heuristic. Its derivation is not explained in the supplied source and it is not proof of an optimal ball count or load capacity.
- The old BaseOptimizer.DetermineRollerDiameter can return its raw target when the first CSV row is already the closest item, because the initial Dw is not replaced on an equal ratio. The Python implementation deliberately returns an actual BallDB entry instead of preserving that defect.
- The C# radial-clearance table returns zero outside 10 <= d < 200 mm. The preset refuses to apply that fallback as a design clearance and returns a field error.
- The cage inner/outer/width values are DGBGeometry properties, not a validated stamped-cage design. StampingCage series-specific board thickness, rivet, pocket and forming parameters remain explicit and separate.
- Source provenance is shown in the current workbench session. The generated request remains an explicit numeric request; this PR does not add a new provenance field to the request schema or claim a durable optimizer trace.

## Tests

- Unit tests cover the original formulas, C# integer clearance behavior, nearest-table entry selection, fail-closed behavior outside the source clearance range, and a real OCCT B-Rep build using the returned DGB profile.
- HTTP tests cover same-origin enforcement, missing resource handling, request shape validation, and source-backed response values.
- Playwright tests cover DGB form prefill, unchanged CAD-only pocket clearance, no accidental stamped-cage overwrite, and hiding the preset for other bearing types.
- Existing CAD/OCCT, drawing, and browser regression workflows remain required.

No real Eyeshot STEP comparison, Windows AutoCAD review, bearing load calculation, or manufacturing approval is claimed by this PR.
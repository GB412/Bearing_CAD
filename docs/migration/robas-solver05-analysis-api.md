# RoBAS quasi-static analysis API

The loopback CAD service connects the existing `BearingRequest`, ball/roller
DATA builders, Windows probe and result parser. The API is synchronous. It
accepts supplied DGB, ACB and CRB N design snapshots, with plain rollers for CRB.
It uses the same Host, Origin, JSON and 16 KiB body checks as CAD jobs.

## Server setup

For the normal local launch, add the optional `analysis_profiles_path` key to
`config/robas.local.json` and run `scripts/run_bearing_cad_with_robas.ps1`.
An absolute path is accepted, and a relative path is resolved against the
configuration file's directory. An omitted, null or empty key leaves analysis
disabled and keeps the existing CAD launch. The lower-level
`scripts/start_bearing_cad_with_robas.ps1` accepts `-AnalysisProfilesPath`
and forwards `--robas-analysis-profiles` to the backend.
An explicitly configured manifest must exist and contain valid profile JSON.
The launcher or backend reports the error at startup if this check fails.

The backend can also be started directly with operator-controlled paths.

```powershell
python -m bearing_cad.api --port 8090 --robas-resources 'C:\RollBearing' `
  --robas-analysis-profiles 'D:\local-robas-profiles\profiles.json'
```

`--robas-resources` points to the local resource directory containing
`exe/RoBAS_v2.exe`. The probe validates the original x86 executable and
its pinned SHA-256 before each execution. The manifest has profile IDs as
keys. Each entry has these five fields.

```json
{
  "n222-reviewed-v1": {
    "bearing_type": "rolling.cylindrical_roller",
    "configuration": "N",
    "data_file": "n222/DATA.txt",
    "sha256": "e6c604dd32ceeac659e21edd32215d3f3218e3c53f954a1ef70736a94373d0f5",
    "source": "Original RoBAS UI N222 case, 2026-11-08"
  }
}
```

Use `configuration: null` for DGB and ACB and `"N"` for a CRB source
confirmed from the original model. Copy the reviewed reference under the
manifest directory. Paths must resolve beneath that directory. Pin the file's
actual lowercase SHA-256 and record its source. The operator is responsible
for selecting a suitable original material, lubrication and solver profile.
The API checks the protocol and hash before generation and verifies the same
hash after the builder reads it. Only the original output filenames are
accepted. Keep the manifest, original DATA and EXE on the local machine.

`GET /api/v2/cad/analyses/status` reports the timeout and each configured ID's
`available` flag and optional `unavailable_reason`. It checks Windows and the
EXE and retained-run limit, then verifies each reference's protocol, pinned
hash, supported profile settings and output filenames. A missing or changed
reference disables its profile. Top-level `available` requires at least one
usable profile. POST rechecks the selected profile and storage. A ready status
does not reserve solver capacity. POST reports if the solver is busy.

## Request and response

`POST /api/v2/cad/analyses` accepts an object with these fields.

| Field | Meaning |
|---|---|
| `design` | Supplied `bearing-cad.request.v1` design snapshot. |
| `request_hash` | SHA-256 from `BearingRequest.request_hash` for that snapshot, also returned by the existing CAD job. A mismatch returns HTTP 409. A match proves snapshot consistency only. User confirmation and successful CAD generation require separate evidence. |
| `profile_id` | Selects a configured profile of the same bearing type. Paths and EXE arguments are absent from the request contract. |
| `analysis_geometry` | DGB requires `inner_race_od_mm`. ACB also requires `inner_sidewall_mm` and `outer_sidewall_mm`, each matching one of the CAD sidewalls at original getter precision. CRB uses `{}` because its existing DATA builder maps the CAD inputs directly. |
| `operating_conditions` | Optional keys within this required object are `load_x_n`, `load_y_n`, `load_z_n`, `outer_speed_rpm`, `inner_speed_rpm`, and `free_clearance_mm`. An empty object deliberately inherits the selected profile's conditions. Speeds supplied by the caller use the original scan-endpoint linkage. Nonzero CRB CAD radial gap requires an explicit, independently sourced solver clearance. |
| `allow_reference_geometry_mismatch` | Optional Boolean, default `false`. If the builder reports a geometry difference, the caller must review it before acknowledging an overlay. |

The force components follow RoBAS DATA axes. No CAD-axis conversion is
assumed. The signed load and speed limits are ±1,000,000 N and ±100,000 rpm,
with free clearance from 0 to 10 mm. These are service limits. The response
reports `operating_conditions.requested`, `inherited` and `effective` for the
six exposed fields. `inherited` lists the exposed values left to the profile.
The existing `BaseBC` mapping derives `rpmRange21` from a supplied outer speed
and `rpmRange12` from a supplied inner speed. Other scan fields, fit,
temperatures, moments, material, lubrication and solver settings remain in
the pinned profile. The six fields are a limited override interface.

### Ball CAD and analysis cages

The DGB CAD builder supports a simplified annular or stamped double-half
cage. The ACB CAD builder supports an explicit straight-pocket cage, and
the CAD design can carry an ACB cage-material selection. SOLVER-02 generates
the original analysis cage geometry and uses the pinned analysis material
profile. The current mapping does not reconcile the CAD cage dimensions or
material with those analysis settings. POST rejects explicit DGB/ACB CAD
cages at `/design/cage` and ACB CAD cage material at
`/design/parameters/cage_material`, with HTTP 422 `NOT_SUPPORTED`.

HTTP 201 means a structured result was created and saved. The response binds
the design snapshot and request hash, requested and effective conditions,
analysis-only dimensions, profile ID and hash, generated DATA hash, original
EXE hash, and parsed file hashes to one `run_id`. The parser receives the
report from that exact probe call and must return `HASH_VERIFIED`. The result
continues to expose process exit, parsed section status, metric validity and
convergence separately. A zero exit still leaves convergence `UNKNOWN`.

| Failure | HTTP | Diagnostic |
|---|---:|---|
| Missing or unsupported request field or analysis geometry | 422 | Existing `error.field_path` identifies the field. |
| Design snapshot hash mismatch | 409 | `DESIGN_HASH_MISMATCH` |
| Configuration, profile, executable or capacity unavailable | 503 | Profile/preflight, busy or storage limit code. |
| Process launch/nonzero exit, missing output or invalid result binding | 502 | Separate execution, output and parse codes, with `run_id` when created. |
| Solver timeout | 504 | `ANALYSIS_TIMEOUT`, with execution evidence. |
| Local evidence storage failure | 500 | `ANALYSIS_STORAGE_FAILED` |

Each attempt gets a new folder under the server's artifact root in
`robas-analysis/analysis-<run_id>`. The request snapshot and generated DATA
are recorded there, the probe writes to its isolated child directory, and
the API stores the verified response as `analysis_result.json`. These are
local operator artifacts. The service runs one solver at a time per server
process, with no queue, a 45-second timeout, at most 32 retained attempts,
and a 2 MiB limit per parsed output file. These parsing limits do not impose
an OS-level disk quota on the legacy executable while it runs. The operator
can archive old runs before the cap is reached. The API has no artifact
download, deletion or background task endpoint.

SOLVER-06 can discover usable profiles via GET and take `design_snapshot.json`
and `request_hash` from a successful CAD job when its workflow requires CAD
generation. The UI owns user confirmation and must surface unsupported ball
cages or cage materials before submission. It must preserve the snapshot and
show the mismatch, with any design change requiring an explicit user action.
The UI should present requested and inherited conditions distinctly, then POST
the snapshot, hash, analysis dimensions and chosen overrides. It can display
the returned field errors or result. Associate the result with its returned
`request_hash` and compare it against the current design snapshot hash, even
if the request completes after an edit. While the current design is edited or
its hash differs, show the old result only as a historical run. Request a new
analysis for the current design snapshot.
It can use `result.execution`, `result.output_status`, metric `status` and
`result.convergence` independently. Tests exercise this HTTP contract with
portable simulated process outcomes and with the original Windows EXE and
private DGB, ACB and N222 cases when available. Coverage is limited to the
verified RoBAS 8.11 quasi-static format and the tested engineering cases.

### Windows golden comparison

The HTTP tests start the real loopback server, select a pinned profile,
generate DATA from the corresponding design snapshot and invoke the
original Windows EXE. They compare every supported metric and nonfinite
entry with the archived output, alongside independent expected values.

| Case | RE #1 outer contact load (N) | RE #1 inner contact stress (MPa) | Nonfinite evidence entries |
|---|---:|---:|---:|
| DGB | 2251 | 3402 | 15 |
| ACB | 954.5 | 1968 | 15 |
| N222 | 16750 | 1138 | 5 |

All three bind generated DATA and result hashes with `HASH_VERIFIED`.
The N222 generated DATA, OUT and `a0_Final` also match the archived hashes.
Each process exits with code 0 and its convergence remains `UNKNOWN`.

An additional Windows HTTP test uses the same DGB snapshot and profile with
RoBAS `load_z_n` changed from 2000 to 2400 N. It checks that only the load field
changes in DATA, a separate original EXE run produces a new OUT hash, and
the result returns `HASH_VERIFIED` and `PARSED_SUPPORTED_SECTIONS`.
The original DATA, OUT and `a0_Final` remain unchanged. The X load and inner
speed stay at 4500 N and 20,000 rpm in both runs.

| Printed result | 2000 N Z load | 2400 N Z load |
|---|---:|---:|
| RE #1 outer contact load (N) | 2251 | 2330 |
| RE #1 inner contact stress (MPa) | 3402 | 3443 |
| Total power loss (W) | 3092 | 3112 |
| Internal clearance (m) | -5.023e-5 | -5.023e-5 |

Each run retains 14 `NaN` values and one `Infinity` as raw tokens with null
values and `INVALID` status. Convergence remains `UNKNOWN`.

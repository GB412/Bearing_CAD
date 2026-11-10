# RoBAS quasi-static analysis API

The loopback CAD service connects the existing `BearingRequest`, ball/roller
DATA builders, Windows probe and result parser. The API is synchronous. It
accepts confirmed DGB, ACB and CRB N designs, with plain rollers for CRB.
It uses the same Host, Origin, JSON and 16 KiB body checks as CAD jobs.

## Server setup

Start the Windows backend with operator-controlled paths.

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

`GET /api/v2/cad/analyses/status` reports availability, the allowed profile IDs,
bearing types, source descriptions, reference hashes and timeout. It verifies
Windows and the EXE when configured. Each POST verifies its selected profile.

## Request and response

`POST /api/v2/cad/analyses` accepts an object with these fields.

| Field | Meaning |
|---|---|
| `design` | Confirmed `bearing-cad.request.v1` snapshot used for CAD. |
| `request_hash` | SHA-256 from `BearingRequest.request_hash` for that snapshot, also returned by the existing CAD job. A mismatch returns HTTP 409. This is a version check. |
| `profile_id` | Selects a configured profile of the same bearing type. Paths and EXE arguments are absent from the request contract. |
| `analysis_geometry` | DGB requires `inner_race_od_mm`. ACB also requires `inner_sidewall_mm` and `outer_sidewall_mm`, each matching one of the CAD sidewalls at original getter precision. CRB uses `{}` because its existing DATA builder maps the CAD inputs directly. |
| `operating_conditions` | Optional keys within this required object are `load_x_n`, `load_y_n`, `load_z_n`, `outer_speed_rpm`, `inner_speed_rpm`, and `free_clearance_mm`. An empty object deliberately inherits the selected profile's conditions. Speeds supplied by the caller use the original scan-endpoint linkage. Nonzero CRB CAD radial gap requires an explicit, independently sourced solver clearance. |
| `allow_reference_geometry_mismatch` | Optional Boolean, default `false`. If the builder reports a geometry difference, the caller must review it before acknowledging an overlay. |

The force components follow RoBAS DATA axes. No CAD-axis conversion is
assumed. The signed load and speed limits are ±1,000,000 N and ±100,000 rpm,
with free clearance from 0 to 10 mm. These are service limits. The full
material, fit, lubricant and solver settings remain in the pinned profile.
The ball builders use the original analysis cage. Requests with a separate
ball CAD cage or ACB CAD cage-material selection are rejected because the
existing ball DATA mapping does not reconcile them with that profile.

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
| Confirmed design hash mismatch | 409 | `DESIGN_HASH_MISMATCH` |
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

SOLVER-06 can discover the server profiles via GET, take `design_snapshot.json`
from the confirmed CAD job and its returned `request_hash`, then POST both
with the chosen conditions. It can display the returned field errors or result.
It can use `result.execution`, `result.output_status`, metric `status` and
`result.convergence` independently. Tests exercise this HTTP contract with
portable simulated process outcomes and with the original Windows EXE and
private DGB, ACB and N222 cases when available. Coverage is limited to the
verified RoBAS 8.11 quasi-static format and the tested engineering cases.

### Windows golden comparison

The HTTP tests start the real loopback server, select a pinned profile,
generate DATA from the corresponding confirmed snapshot and invoke the
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

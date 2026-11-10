"""Portable parser checks and independent local Windows result goldens."""
import hashlib
import json
from pathlib import Path

import pytest

from bearing_cad.robas_ball_input import _RECORD_FIELDS as BALL_FIELDS
from bearing_cad.robas_results import ResultParseError, parse_static_results


EVIDENCE = Path(__file__).resolve().parents[1] / "build" / "robas-solver01-acceptance-20261108"
CONTACT_KEYS = ("angle", "deflection", "load", "stress")
CONTACT_UNITS = ("deg", "mm", "N", "MPa")


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def run(tmp_path):
    data = []
    for i, (label, fields) in enumerate(BALL_FIELDS):
        values = ["1"] * len(fields)
        if i == 0:
            values[0] = "-1"
        if i in (3, 4):
            values = ["'test'"] * len(fields)
        if i == 5:
            values[2] = "2"
        data.append(",".join([f"'{label}'", *values]))
    (tmp_path / "DATA.txt").write_bytes(("\r\n".join(data) + "\r\n").encode())
    out = """\f
    Listing of input data records
    rec 1    -1  1  0  0  1  1  1  1  1  0  1  100  5  5
    rec 3.2   1  1  2  1  0  0  0  0  0  0  0  0
    Version (RoBAS 8.11)
    AT INF SLIP
    Race Angular Velocities Relative Race Displacements Stiffness Stiffness Stiffness
    Outer Inner x y z XX YY ZZ
    (rpm) (rpm) (m) (m) (m) (n/m) (n/m) (n/m)

    1. 0 1200 2.1E-4 0 6.1E-7 3E+7 4E+7 5E+7

    RE ....Contact Angle.... ...Contact Deflection  ....Contact Load..... ...Contact Stress........Race Flexing.....
    no (deg) (m) (n) (Pa) (m)
    Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race

    1 12 18 1.23456E-5 3.125E-5 126 74 2.3E+8 1.6E+8 0 0
    2 10 20 0 0 0 0 0 0 0 0

    Internal Clearance (m) -2.4E-5
    Int ORace 0 0 0 0 0 0 Total Power Loss (W) 9.5E+1
    .....................Time Average Parameters.....................
    Step Time Outer Race Inner Race Power RE Orbital Cage Omega Cage Whirl Cage Average RE
    no Rotation Rotation Loss Vel Ratio Ratio Ratio Wear Rate Excursion
    (s) (rev) (rev) (W) (m**3/s) (m)

    0 0 0 0 95 0 0 0 0 0
"""
    (tmp_path / "OUT.txt").write_bytes(out.replace("\n", "\r\n").encode())
    return tmp_path


def _replace_out(run, old, new):
    path = run / "OUT.txt"
    raw = path.read_bytes()
    assert old.encode() in raw
    path.write_bytes(raw.replace(old.encode(), new.encode(), 1))


def _probe(run, *, executed=True, code=0, status="OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF"):
    return {
        "schema_version": "bearing-cad.robas-solver-probe.v1", "stage": "isolated_execution",
        "input": {"family": "ball", "input_sha256": _hash(run / "DATA.txt")},
        "output_files": [{"filename": name, "sha256": _hash(run / name)}
                         for name in ("OUT.txt", "a0_Final") if (run / name).exists()],
        "solver_executed": executed, "process_exit_code": code, "output_status": status,
        "solver_converged": True,  # An unaudited report flag cannot establish convergence.
    }


def test_parses_units_rounding_and_keeps_execution_independent(run):
    result = parse_static_results(run, family="ball")
    assert result["execution"] == {"status": "UNKNOWN", "exit_code": None}
    assert result["convergence"] == {"status": "UNKNOWN"}
    assert result["files"]["a0_Final"] == {"status": "MISSING"}
    assert result["files"]["OUT.txt"]["sha256"] == _hash(run / "OUT.txt")
    assert result["nonfinite_evidence"] == []  # The `AT INF SLIP` heading is text.
    row = result["contacts"][0]
    assert row["outer"]["deflection"] == {
        "unit": "mm", "raw": "1.23456E-5", "value": 0.01235, "status": "VALID",
    }
    # This converted value is already at the C# five-decimal precision.
    assert row["inner"]["deflection"]["value"] == 0.03125
    assert row["outer"]["load"]["value"] == 126
    assert row["inner"]["stress"]["value"] == pytest.approx(160)
    assert result["contacts"][1]["outer"]["load"]["value"] == 0
    assert result["stiffness_sweep"][0]["inner_speed"]["value"] == 1200
    assert result["stiffness_sweep"][0]["stiffness_zz"]["unit"] == "N/m"
    assert result["summary"]["internal_clearance"]["value"] == -2.4e-5


@pytest.mark.parametrize(("executed", "code", "probe_status", "expected"), [
    (True, 0, "OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF", "EXITED_ZERO"),
    (True, 6, "PROCESS_NONZERO_EXIT", "EXITED_NONZERO"),
    (True, None, "PROCESS_TIMEOUT", "TIMEOUT"),
    (False, None, "PROCESS_START_FAILED", "START_FAILED"),
])
def test_uses_hash_bound_execution_evidence(run, executed, code, probe_status, expected):
    (run / "a0_Final").write_bytes(b"0 0.05\r\n0 1\r\n")
    result = parse_static_results(run, family="ball", probe_report=_probe(
        run, executed=executed, code=code, status=probe_status,
    ))
    assert result["execution"] == {"status": expected, "exit_code": code}
    assert result["convergence"]["status"] == "UNKNOWN"
    assert result["files"]["a0_Final"]["status"] == "PRESENT_UNINTERPRETED"
    assert result["files"]["a0_Final"]["sha256"] == _hash(run / "a0_Final")


def test_probe_hash_mismatch_is_rejected(run):
    report = _probe(run)
    _replace_out(run, "2.3E+8", "2.4E+8")
    with pytest.raises(ResultParseError, match="OUT.txt SHA-256 mismatch"):
        parse_static_results(run, family="ball", probe_report=report)


@pytest.mark.parametrize("name", ["DATA.txt", "OUT.txt"])
def test_requires_input_and_output_files(run, name):
    (run / name).unlink()
    with pytest.raises(ResultParseError, match="required file is missing") as error:
        parse_static_results(run, family="ball")
    assert error.value.filename == name


@pytest.mark.parametrize(("old", "new", "detail"), [
    ("(deg) (m) (n) (Pa) (m)", "(deg) (m) (n) (MPa) (m)", "contact units"),
    ("2 10 20 0 0 0 0 0 0 0 0", "2 10 20 0", "contact row width"),
    ("2 10 20 0 0 0 0 0 0 0 0", "", "expected 2 contact rows"),
    ("2.3E+8", "bad", "invalid numeric field"),
    ("rec 3.2   1  1  2", "rec 3.2   1  2  2", "does not match DATA.txt"),
    ("0 0 0 0 95 0 0 0 0 0", "0 0 0 0 95", "incomplete Time Average Parameters"),
    ("Time Average Parameters", "truncated", "missing header"),
])
def test_rejects_malformed_and_truncated_reports(run, old, new, detail):
    _replace_out(run, old, new)
    with pytest.raises(ResultParseError, match=detail) as error:
        parse_static_results(run, family="ball")
    assert error.value.filename == "OUT.txt"


def test_invalid_numbers_keep_tokens_and_never_serialize_nonstandard_json(run):
    _replace_out(run, "2.3E+8 1.6E+8", "NaN -Infinity")
    _replace_out(run, "1.23456E-5", "1E+999")
    result = parse_static_results(run, family="ball")
    row = result["contacts"][0]
    for metric, raw in ((row["outer"]["stress"], "NaN"), (row["inner"]["stress"], "-Infinity"),
                        (row["outer"]["deflection"], "1E+999")):
        assert (metric["value"], metric["status"], metric["raw"]) == (None, "INVALID", raw)
    assert [entry["raw"] for entry in result["nonfinite_evidence"]] == ["NaN", "-Infinity"]
    assert json.loads(json.dumps(result, allow_nan=False)) == result


# Hand-transcribed printed rows and C# conversions. These values are independent
# of the parser, including signed clearance and the final point of the sweep.
@pytest.mark.parametrize(("folder", "family", "digest", "count", "line", "outer", "inner", "sweep", "summary"), [
    ("real-DGB", "ball", "9e1a86c60ff39ebbd5aa56609e245242f107bb9abfc7e9a53966d2ce0ba415c9",
     11, 390, (12.54, .02008, 2251, 2593), (12.83, .02376, 2202, 3402),
     (1.199e-4, 5.347e-6, 2.920e8), (3092, -5.023e-5)),
    ("user-run-2304", "ball", "ed15064dda6f719929ae5e2858044d1a4be4c87377250edb5c7ff1fd0e17148d",
     20, 408, (19.01, .01035, 954.5, 1635), (23.63, .01077, 775.6, 1968),
     (2.557e-4, 5.018e-6, 3.372e8), (400.7, 6.85e-5)),
    ("real-CRB", "roller", "f4ca12de97c8c326c685044ee0e3d1a1ff517464e171d76fee9f8a81903d4326",
     14, 396, (0, .01735, 16750, 1103), (0, .01322, 9001, 1138),
     (0, 6.457e-7, 3.097e9), (226.8, -5.985e-5)),
])
def test_real_windows_goldens(folder, family, digest, count, line, outer, inner, sweep, summary):
    matches = sorted((EVIDENCE / folder).glob("*/OUT.txt"))
    if not matches:
        pytest.skip("local RoBAS golden output is not part of the public repository")
    path = matches[0]
    assert _hash(path) == digest
    report = json.loads((path.parent / "solver_probe_report.json").read_bytes())
    result = parse_static_results(path.parent, family=family, probe_report=report)
    assert result["rolling_element_count"] == len(result["contacts"]) == count
    assert result["contacts"][0]["line"] == line
    for side, expected in (("outer", outer), ("inner", inner)):
        row = result["contacts"][0][side]
        for field, unit, value in zip(CONTACT_KEYS, CONTACT_UNITS, expected):
            assert row[field]["status"] == "VALID"
            assert row[field]["unit"] == unit
            assert row[field]["value"] == pytest.approx(value, rel=1e-12, abs=1e-12)
    assert len(result["stiffness_sweep"]) == 5
    last = result["stiffness_sweep"][-1]
    assert last["inner_speed"]["value"] == 20000
    for field, unit, value in zip(("displacement_x", "displacement_z", "stiffness_zz"), ("m", "m", "N/m"), sweep):
        assert last[field]["unit"] == unit
        assert last[field]["value"] == pytest.approx(value, rel=1e-12, abs=1e-12)
    assert result["summary"]["total_power_loss"]["value"] == summary[0]
    assert result["summary"]["internal_clearance"]["value"] == summary[1]
    assert result["execution"] == {"status": "EXITED_ZERO", "exit_code": 0}
    assert result["convergence"]["status"] == "UNKNOWN"
    assert result["files"]["OUT.txt"]["sha256"] == _hash(path) == digest
    if family == "roller":
        evidence = result["nonfinite_evidence"]
        assert [(e["line"], e["method"], e["component"], e["unit"]) for e in evidence] == [
            (689, "Tallian", "Outer Race", "h"), (698, "Tallian", "Outer Race", "1"),
            (698, "Tallian", "Bearing", "1"), (698, "STLE", "Outer Race", "1"),
            (698, "STLE", "Bearing", "1"),
        ]
        assert all((e["file"], e["model"], e["raw"], e["status"], e["cause"], e["value"]) ==
                   ("OUT.txt", "Original LP", "NaN", "INVALID", "UNKNOWN", None) for e in evidence)
    assert json.loads(json.dumps(result, allow_nan=False)) == result

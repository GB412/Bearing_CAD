"""Portable parser checks and independent local Windows result goldens."""
import hashlib
import json
from pathlib import Path

import pytest

from bearing_cad.robas_ball_input import BallDataDocument, _RECORD_FIELDS as BALL_FIELDS
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


def test_builtin_dgb_life_result_parser_accepts_39_rows(run):
    data = run / "DATA.txt"
    rows = data.read_bytes().splitlines()
    rows = [row for row in rows if not any(
        row.startswith(("'" + rec + "'").encode())
        for rec in ("rec 8.6.0", "rec 8.6.1", "rec 8.6.2", "rec 8.6.3")
    )]
    rows[6] = rows[6].rsplit(b",", 1)[0] + b",0"
    data.write_bytes(b"\r\n".join(rows) + b"\r\n")
    result = parse_static_results(run, family="ball")
    assert result["rolling_element_count"] == 2
    assert result["summary"]["total_power_loss"]["value"] == 95

    rows[6] = rows[6].rsplit(b",", 1)[0] + b",1"
    data.write_bytes(b"\r\n".join(rows) + b"\r\n")
    with pytest.raises(ResultParseError, match="kLifeCons must be 0"):
        parse_static_results(run, family="ball")


def test_parses_units_rounding_and_keeps_execution_independent(run):
    result = parse_static_results(run, family="ball")
    assert result["execution"] == {"status": "UNKNOWN", "exit_code": None}
    assert result["convergence"] == {"status": "UNKNOWN"}
    assert result["source_binding"] == {"status": "UNVERIFIED", "evidence": "LIMITED_OUT_ECHO"}
    assert result["output_status"] == "PARSED_SUPPORTED_SECTIONS"
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
    (True, 0, "OUTPUT_ABSENT_OR_INVALID", "EXITED_ZERO"),
    (True, 6, "PROCESS_NONZERO_EXIT", "EXITED_NONZERO"),
    (True, None, "PROCESS_TIMEOUT", "TIMEOUT"),
    (False, None, "PROCESS_START_FAILED", "START_FAILED"),
    (False, None, "NOT_EXECUTED", "NOT_EXECUTED"),
])
def test_uses_hash_bound_execution_evidence(run, executed, code, probe_status, expected):
    (run / "a0_Final").write_bytes(b"0 0.05\r\n0 1\r\n")
    result = parse_static_results(run, family="ball", probe_report=_probe(
        run, executed=executed, code=code, status=probe_status,
    ))
    assert result["execution"] == {"status": expected, "exit_code": code}
    assert result["source_binding"] == {"status": "HASH_VERIFIED", "evidence": "PROBE_REPORT_SHA256"}
    assert result["convergence"]["status"] == "UNKNOWN"
    assert result["files"]["a0_Final"]["status"] == "PRESENT_UNINTERPRETED"
    assert result["files"]["a0_Final"]["sha256"] == _hash(run / "a0_Final")


def test_probe_hash_mismatch_is_rejected(run):
    report = _probe(run)
    _replace_out(run, "2.3E+8", "2.4E+8")
    with pytest.raises(ResultParseError, match="OUT.txt SHA-256 mismatch"):
        parse_static_results(run, family="ball", probe_report=report)


def test_equal_echo_does_not_bind_modified_operating_conditions(run):
    report = _probe(run)
    data = run / "DATA.txt"
    modified = BallDataDocument.read(data).with_updates({(29, "appLoadX"): 1500})
    data.write_bytes(modified.render().encode())
    result = parse_static_results(run, family="ball")
    assert result["output_status"] == "PARSED_SUPPORTED_SECTIONS"
    assert result["source_binding"]["status"] == "UNVERIFIED"
    with pytest.raises(ResultParseError, match="DATA.txt family or SHA-256 mismatch"):
        parse_static_results(run, family="ball", probe_report=report)


@pytest.mark.parametrize(("executed", "code", "status"), [
    (True, 0, "PROCESS_NONZERO_EXIT"),
    (True, 0, "PROCESS_TIMEOUT"),
    (True, 3, "OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF"),
    (True, 3, "OUTPUT_ABSENT_OR_INVALID"),
    (True, None, "PROCESS_START_FAILED"),
    (False, None, "PROCESS_TIMEOUT"),
    (False, None, "OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF"),
    (False, None, "UNRECOGNIZED_STATUS"),
    (False, 1, "PROCESS_NONZERO_EXIT"),
    (True, False, "OUTPUT_ABSENT_OR_INVALID"),
    (1, 0, "OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF"),
])
def test_rejects_contradictory_execution_fields(run, executed, code, status):
    report = _probe(run, executed=executed, code=code, status=status)
    with pytest.raises(ResultParseError, match="inconsistent execution fields") as error:
        parse_static_results(run, family="ball", probe_report=report)
    assert error.value.filename == "solver_probe_report.json"


def test_missing_exit_code_is_distinct_from_explicit_null(run):
    report = _probe(run, executed=True, code=None, status="PROCESS_TIMEOUT")
    del report["process_exit_code"]
    with pytest.raises(ResultParseError, match="missing execution fields"):
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
    assert result["output_status"] == "PARSED_SUPPORTED_SECTIONS"
    assert result["execution"]["status"] == result["convergence"]["status"] == "UNKNOWN"
    row = result["contacts"][0]
    for metric, raw in ((row["outer"]["stress"], "NaN"), (row["inner"]["stress"], "-Infinity"),
                        (row["outer"]["deflection"], "1E+999")):
        assert (metric["value"], metric["status"], metric["raw"]) == (None, "INVALID", raw)
    assert [entry["raw"] for entry in result["nonfinite_evidence"]] == ["NaN", "-Infinity"]
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.fixture
def extended_run(run):
    # Independently transcribed output headers / RE #1 values, plus a zero
    # row. Expected conversions below are literal C# reference results.
    extra = """
RE ...Orbital .....Axial ...Rel Orb ...RE Ang Position...........Angular Velocity........
no Position Position Position Mis Skew Amplitude Theta Phi
(deg) (m) (rad) (deg) (deg) (rpm) (deg) (deg)

1 0 4.056E-05 -3.331E-16 0 0 6.339E+04 1.691E+02 0
2 0 0 0 0 0 0 0 0

RE ...Orbital Centrifugal ......Moving Frame Forces...... ..Time Ave ......Bulk Convec HTC
no Velocity Force (n) Wear Rate Temp
(rpm) (n) Radial Orbital Axial (m**3/s) (K) (W/m**2/K)

1 8.495E+03 5.099E+01 0 0 0 4.512E-13 3.230E+02 0
2 0 0 0 0 0 0 0 0

RE ..Major Half Width... ..Minor Half Width... .Outer Contact Edge.. ..Chordal Distance...
no (m) (m) Depth from Shoulder of Inner Contact Edge
(m) (m)
Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race

1 1.760E-03 1.363E-03 2.356E-04 2.267E-04 8.348E-04 1.035E-03 -8.062E-04 3.544E-04
2 0 0 0 0 0 0 0 0

RE ...Rolling Velocity.. ......Spin/Roll...... Isothermal Lub Film.. ..Reduction Factor...
no (m/s) (m)
Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race

1 2.765E+01 2.764E+01 0 6.329E-02 4.582E-07 3.967E-07 6.509E-01 6.048E-01
2 0 0 0 0 0 0 0 0

RE ..Max Slip Velocity.. .....Trac Coeff...... ...Lubricant Film.... ...Max Stress*Slip... ..Normalized Position
no (m/s) (m) (Pa.m/s) of Max Stress*Slip
Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race

1 1.893E+00 2.110E+00 3.104E-02 5.959E-02 2.983E-07 2.399E-07 1.852E+09 3.061E+09 -6.700E-01 6.700E-01
2 0 0 0 0 0 0 0 0 0 0

RE ....Contact Loss..... ..Contact Temp Rise.. .....Contact Temp.... ....Lub Film Temp.... ....Load*Slip Int....
no (W) (K) (K) (K) (W)
Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race Outer Race Inner Race

1 1.406E+02 2.481E+02 1.048E+01 2.384E+01 3.230E+02 3.230E+02 3.782E+02 4.238E+02 9.645E+02 8.056E+02
2 0 0 0 0 0 0 0 0 0 0

"""
    path = run / "OUT.txt"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"    Internal Clearance", extra.replace("\n", "\r\n").encode() + b"    Internal Clearance"))
    return run


def test_extended_sections_use_csharp_units_and_rounding(extended_run):
    result = parse_static_results(extended_run, family="ball")
    assert set(result["additional_sections"].values()) == {"PARSED"}
    outer, inner = result["contacts"][0]["outer"], result["contacts"][0]["inner"]
    for field, unit, value in (("major_half_width", "m", .00176), ("minor_half_width", "m", .0002356),
                               ("rolling_velocity", "m/s", 27.65), ("spin_roll_ratio", "1", 0),
                               ("film_thickness", "um", .2983), ("isothermal_film_thickness", "um", .4582),
                               ("film_temperature", "degC", 105.05), ("contact_temperature", "degC", 49.85),
                               ("contact_temperature_rise", "K", 10.48), ("contact_loss", "W", 140.6)):
        assert outer[field]["value"] == pytest.approx(value, rel=1e-12)
        assert outer[field]["unit"] == unit
    assert inner["film_temperature"]["value"] == 150.65
    assert inner["film_thickness"]["value"] == .2399
    assert inner["spin_roll_ratio"]["value"] == .06329
    # Literal values cover the remaining paired columns, so equal row counts
    # alone cannot hide a shifted source column.
    for field, expected in {
        "major_half_width": (.00176, .001363), "minor_half_width": (.0002356, .0002267),
        "outer_contact_edge_depth": (.0008348, .001035), "inner_contact_edge_chord": (-.0008062, .0003544),
        "rolling_velocity": (27.65, 27.64), "film_reduction_factor": (.6509, .6048),
        "max_slip_velocity": (1.893, 2.11), "traction_coefficient": (.03104, .05959),
        "max_stress_slip": (1.852e9, 3.061e9), "max_stress_slip_position": (-.67, .67),
        "contact_loss": (140.6, 248.1), "contact_temperature_rise": (10.48, 23.84),
        "contact_temperature": (49.85, 49.85), "load_slip_integral": (964.5, 805.6),
    }.items():
        assert (outer[field]["value"], inner[field]["value"]) == pytest.approx(expected, rel=1e-12)
    motion = result["rolling_elements"][0]
    assert motion["spin_speed"]["value"] == 63390
    assert motion["orbit_speed"]["value"] == 8495
    assert motion["centrifugal_force"]["value"] == 50.99
    assert motion["relative_orbital_position"]["unit"] == "rad"
    # N222 prints zero kelvin for film temperature: retain zero as raw
    # evidence, not a usable -273.15°C lubricant temperature.
    zero = result["contacts"][1]["outer"]["film_temperature"]
    assert zero == {"line": zero["line"], "value": None, "unit": "degC", "status": "INVALID", "raw": "0",
                    "reason": "NONPOSITIVE_ABSOLUTE_TEMPERATURE"}


@pytest.mark.parametrize(("old", "new", "message"), [
    ("no (m/s) (m)", "no (rpm) (m)", "unexpected units"),
    ("1 2.765E+01 2.764E+01 0", "1 2.765E+01 bad 0", "invalid numeric"),
    ("2 0 0 0 0 0 0 0 0", "2 0 0 0", "row width"),
])
def test_extended_tables_reject_wrong_units_numbers_and_truncation(extended_run, old, new, message):
    _replace_out(extended_run, old, new)
    with pytest.raises(ResultParseError, match=message):
        parse_static_results(extended_run, family="ball")


def test_extended_nonfinite_values_are_json_safe(extended_run):
    _replace_out(extended_run, "3.782E+02 4.238E+02", "NaN Infinity")
    result = parse_static_results(extended_run, family="ball")
    assert result["contacts"][0]["outer"]["film_temperature"]["value"] is None
    assert result["contacts"][0]["inner"]["film_temperature"]["raw"] == "Infinity"
    json.dumps(result, allow_nan=False)


def test_old_reports_mark_extended_sections_absent(run):
    result = parse_static_results(run, family="ball")
    assert set(result["additional_sections"].values()) == {"NOT_PRESENT"}
    assert result["model_tables"] == []
    assert result["raw_report"]["status"] == "PRINTED_EVIDENCE_ONLY"


@pytest.fixture
def model_run(run):
    printed = """
     Computed Dynamic Capacities at Heaviest Loaded Rolling Element on Primary Race Segments ***
             Model .............Stress Capacities............. ..............Load Capacities..............
                                       (Pa)                                         (n)
                   Outer Race Inner Race ...Rolling Element... Outer Race Inner Race ...Rolling Element...
                                         Outer Race Inner Race                       Outer Race Inner Race

       Original LP                                              1.242E+04  5.629E+03
        Current LP  1.043E+12  1.585E+12  1.007E+10  1.531E+10  1.463E+11  2.225E+11  1.319E+05  2.005E+05
                GZ  3.659E+11  5.561E+11  3.534E+09  5.372E+09  6.323E+09  9.614E+09  5.701E+03  8.665E+03
                IH  0.000E+00  0.000E+00  0.000E+00  0.000E+00  0.000E+00  0.000E+00  0.000E+00  0.000E+00

     Basic Life (Hours) with Various Life Models
             Model Outer Race Inner Race  Roll Elem    Bearing

       Original LP  0.000E+00  2.099E+00             0.000E+00
        Current LP  1.388E+04  1.868E+04  5.495E-01  9.608E-02
                GZ  1.709E+03  2.300E+03  4.487E-01  9.608E-02
                IH  0.000E+00  0.000E+00  0.000E+00  0.000E+00

"""
    path = run / "OUT.txt"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"    Internal Clearance", printed.replace("\n", "\r\n").encode() + b"    Internal Clearance"))
    return run


def test_model_tables_preserve_sparse_columns_without_claiming_applicability(model_run):
    tables = parse_static_results(model_run, family="ball")["model_tables"]
    capacity, life = tables
    metrics = capacity["rows"][0]["metrics"]
    assert metrics["stress_outer"]["status"] == "NOT_REPORTED"
    assert metrics["load_outer"]["value"] == 12420
    assert metrics["load_inner"]["value"] == 5629
    assert metrics["load_outer"]["unit"] == "N"
    assert metrics["stress_outer"]["unit"] == "Pa"
    assert life["rows"][0]["metrics"]["element"]["value"] is None
    assert life["rows"][0]["metrics"]["bearing"]["value"] == 0
    assert all(table["interpretation"] == "UNVERIFIED_MODEL_APPLICABILITY" for table in tables)


@pytest.mark.parametrize(("old", "new", "message"), [
    ("(Pa)                                         (n)", "(MPa)                                        (n)", "capacities units"),
    ("Model Outer Race Inner Race  Roll Elem    Bearing", "Model Inner Race Outer Race  Roll Elem    Bearing", "basic_life columns"),
    ("  1.242E+04", "        NaN", None),
    ("  5.629E+03", "bad!", "invalid numeric"),
    ("                GZ  3.659E+11", "                ZZ  3.659E+11", "unsupported capacities"),
])
def test_model_tables_diagnose_invalid_values_and_headers(model_run, old, new, message):
    _replace_out(model_run, old, new)
    if message:
        with pytest.raises(ResultParseError, match=message):
            parse_static_results(model_run, family="ball")
    else:
        result = parse_static_results(model_run, family="ball")
        metric = result["model_tables"][0]["rows"][0]["metrics"]["load_outer"]
        assert metric["value"] is None and metric["status"] == "INVALID"
        json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(("folder", "family", "film", "temperature", "ratio", "spin", "orbit"), [
    ("real-DGB", "ball", (.2983, .2399), (105.05, 150.65), .06329, 63390, 8495),
    ("user-run-2304", "ball", (.425, .3657), (54.75, 81.55), .1586, 74340, 8793),
    ("real-CRB", "roller", (.7051, .6221), (None, None), 0, 53560, 8194),
])
def test_extended_real_windows_goldens(folder, family, film, temperature, ratio, spin, orbit):
    matches = sorted((EVIDENCE / folder).glob("*/OUT.txt"))
    if not matches:
        pytest.skip("local RoBAS golden output is not part of the public repository")
    path = matches[0]
    before = _hash(path)
    result = parse_static_results(path.parent, family=family,
                                  probe_report=json.loads((path.parent / "solver_probe_report.json").read_bytes()))
    assert set(result["additional_sections"].values()) == {"PARSED"}
    for side, thickness, temp in zip(("outer", "inner"), film, temperature):
        row = result["contacts"][0][side]
        assert row["film_thickness"]["value"] == thickness
        assert row["film_temperature"]["value"] == temp
    assert result["contacts"][0]["inner"]["spin_roll_ratio"]["value"] == ratio
    assert result["rolling_elements"][0]["spin_speed"]["value"] == spin
    assert result["rolling_elements"][0]["orbit_speed"]["value"] == orbit
    assert len(result["model_tables"]) == 4
    assert result["raw_report"]["text"].startswith("     1. Rolling Element Parameters")
    assert result["files"]["OUT.txt"]["sha256"] == before == _hash(path)


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
    assert result["source_binding"]["status"] == "HASH_VERIFIED"
    assert result["output_status"] == "PARSED_SUPPORTED_SECTIONS"
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

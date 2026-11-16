"""Read the audited RoBAS 8.11 quasi-static output without running the solver."""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import math
from pathlib import Path
import re

from .robas_ball_input import BallDataDocument
from .robas_data import dotnet_round
from .robas_roller_input import RollerDataDocument
from .robas_solver_probe import _MAX_INPUT, _MAX_OUTPUT


_FAMILIES = {"ball": (BallDataDocument, "1"), "roller": (RollerDataDocument, "2")}
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?")
_NONFINITE = re.compile(r"(?<!\S)[+-]?(?:NaN|Infinity)(?!\S)", re.IGNORECASE)
_CONTACT_HEADER = (
    "RE ....Contact Angle.... ...Contact Deflection ....Contact Load..... "
    "...Contact Stress........Race Flexing....."
)
_CONTACT_FIELDS = (
    ("angle", "deg", 1.0, None),
    ("deflection", "mm", 1e3, 5),
    ("load", "N", 1.0, None),
    ("stress", "MPa", 1e-6, None),
    ("race_flexing", "m", 1.0, None),
)
_SWEEP_FIELDS = (
    ("outer_speed", "rpm"), ("inner_speed", "rpm"),
    ("displacement_x", "m"), ("displacement_y", "m"), ("displacement_z", "m"),
    ("stiffness_xx", "N/m"), ("stiffness_yy", "N/m"), ("stiffness_zz", "N/m"),
)
_LIFE_UNITS = {
    "Modified Life with Various Life Models": "h",
    "Life Modification Factors with Various Life Models": "1",
}


class ResultParseError(ValueError):
    """A required artifact is missing, mismatched, or outside the audited format."""

    def __init__(self, filename: str, detail: str, *, line: int | None = None):
        self.filename = filename
        self.line = line
        location = filename if line is None else f"{filename}:{line}"
        super().__init__(f"{location}: {detail}")


def _read(path: Path, limit: int, *, optional: bool = False) -> bytes | None:
    if path.is_symlink():
        raise ResultParseError(path.name, "symlink artifacts are unsupported")
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    except FileNotFoundError as exc:
        if optional:
            return None
        raise ResultParseError(path.name, "required file is missing") from exc
    except OSError as exc:
        raise ResultParseError(path.name, f"cannot read file ({type(exc).__name__})") from exc
    if len(raw) > limit or (not raw and not optional):
        raise ResultParseError(path.name, "unexpected file size")
    return raw


def _decode(raw: bytes, filename: str) -> str:
    try:
        if b"\0" in raw:
            raise ResultParseError(filename, "contains binary NUL bytes")
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ResultParseError(filename, "expected ASCII or UTF-8 text") from exc


def _lines(text: str) -> list[str]:
    # Form feeds are report page markers; preserve CRLF physical line numbers.
    return [line.removesuffix("\r") for line in text.split("\n")]


def _metric(raw: str, unit: str, line: int, scale: float = 1.0, digits: int | None = None) -> dict:
    if _NONFINITE.fullmatch(raw):
        return {"value": None, "unit": unit, "status": "INVALID", "raw": raw}
    if not _NUMBER.fullmatch(raw):
        raise ResultParseError("OUT.txt", f"invalid numeric field {raw!r}", line=line)
    value = float(raw) * scale
    if not math.isfinite(value):
        return {"value": None, "unit": unit, "status": "INVALID", "raw": raw}
    if digits is not None:
        value = dotnet_round(value, digits)
    return {"value": value, "unit": unit, "status": "VALID", "raw": raw}


def _temperature(raw: str, line: int) -> dict:
    metric = _metric(raw, "degC", line)
    if metric["status"] == "VALID":
        if metric["value"] <= 0:
            metric.update(value=None, status="INVALID", reason="NONPOSITIVE_ABSOLUTE_TEMPERATURE")
        else:
            metric["value"] = dotnet_round(metric["value"] - 273.15, 2)
    return metric


def _header(lines: list[str], heading: str) -> int:
    for index, line in enumerate(lines):
        if " ".join(line.split()) == heading:
            return index
    raise ResultParseError("OUT.txt", f"missing header {heading!r}")


def _block(lines: list[str], start: int):
    while start < len(lines) and not lines[start].strip():
        start += 1
    for index in range(start, len(lines)):
        if not lines[index].strip():
            break
        yield index + 1, lines[index]


def _table(lines: list[str], start: int, columns: int, label: str, suffix: str = "") -> list:
    result = []
    for number, line in _block(lines, start):
        fields = line.split()
        if len(fields) != columns + 1 or fields[0] != f"{len(result) + 1}{suffix}":
            raise ResultParseError("OUT.txt", f"invalid {label} row width or index", line=number)
        result.append((number, fields[1:]))
    return result


def _contacts(lines: list[str], expected_count: int) -> list[dict]:
    header = _header(lines, _CONTACT_HEADER)
    if [line.split() for line in lines[header + 1:header + 3]] != [
        ["no", "(deg)", "(m)", "(n)", "(Pa)", "(m)"],
        ["Outer", "Race", "Inner", "Race"] * 5,
    ]:
        raise ResultParseError("OUT.txt", "unexpected contact units or race order", line=header + 1)
    rows = _table(lines, header + 3, 10, "contact")
    if len(rows) != expected_count:
        raise ResultParseError("OUT.txt", f"expected {expected_count} contact rows, found {len(rows)}", line=header + 1)
    for line, tokens in rows:
        if not all(_NUMBER.fullmatch(token) or _NONFINITE.fullmatch(token) for token in tokens[8:]):
            raise ResultParseError("OUT.txt", "invalid race flexing field", line=line)
    return [
        {"rolling_element": index, "line": line, **{
            race: {field: _metric(tokens[2 * column + side], unit, line, scale, digits)
                   for column, (field, unit, scale, digits) in enumerate(_CONTACT_FIELDS)}
            for side, race in enumerate(("outer", "inner"))
        }}
        for index, (line, tokens) in enumerate(rows, 1)
    ]


# OUT headings and units, independently checked against the three Windows
# archives and both C# processAnalysisResultDataTxt implementations. All
# columns remain outer then inner. Missing optional sections are explicit;
# a present but malformed section must never masquerade as missing data.
_PAIRED_SECTIONS = (
    ("contact_dimensions", "RE ..Major Half Width... ..Minor Half Width... .Outer Contact Edge.. ..Chordal Distance...",
     ["no (m) (m) Depth from Shoulder of Inner Contact Edge", "(m) (m)", "Outer Race Inner Race " * 4],
     (("major_half_width", "m", 1, None), ("minor_half_width", "m", 1, None),
      ("outer_contact_edge_depth", "m", 1, None), ("inner_contact_edge_chord", "m", 1, None))),
    ("rolling_and_film", "RE ...Rolling Velocity.. ......Spin/Roll...... Isothermal Lub Film.. ..Reduction Factor...",
     ["no (m/s) (m)", "Outer Race Inner Race " * 4],
     (("rolling_velocity", "m/s", 1, None), ("spin_roll_ratio", "1", 1, None),
      ("isothermal_film_thickness", "um", 1e6, None), ("film_reduction_factor", "1", 1, None))),
    ("slip_and_film", "RE ..Max Slip Velocity.. .....Trac Coeff...... ...Lubricant Film.... ...Max Stress*Slip... ..Normalized Position",
     ["no (m/s) (m) (Pa.m/s) of Max Stress*Slip", "Outer Race Inner Race " * 5],
     (("max_slip_velocity", "m/s", 1, None), ("traction_coefficient", "1", 1, None),
      ("film_thickness", "um", 1e6, 4), ("max_stress_slip", "Pa.m/s", 1, None),
      ("max_stress_slip_position", "1", 1, None))),
    ("contact_thermal", "RE ....Contact Loss..... ..Contact Temp Rise.. .....Contact Temp.... ....Lub Film Temp.... ....Load*Slip Int....",
     ["no (W) (K) (K) (K) (W)", "Outer Race Inner Race " * 5],
     (("contact_loss", "W", 1, None), ("contact_temperature_rise", "K", 1, None),
      ("contact_temperature", "degC", 1, None), ("film_temperature", "degC", 1, None),
      ("load_slip_integral", "W", 1, None))),
)
_KINEMATIC_SECTIONS = (
    ("positions_and_spin", "RE ...Orbital .....Axial ...Rel Orb ...RE Ang Position...........Angular Velocity........",
     ["no Position Position Position Mis Skew Amplitude Theta Phi", "(deg) (m) (rad) (deg) (deg) (rpm) (deg) (deg)"],
     (("orbital_position", "deg"), ("axial_position", "m"), ("relative_orbital_position", "rad"),
      ("misalignment", "deg"), ("skew", "deg"), ("spin_speed", "rpm"),
      ("spin_theta", "deg"), ("spin_phi", "deg"))),
    ("orbit_and_forces", "RE ...Orbital Centrifugal ......Moving Frame Forces...... ..Time Ave ......Bulk Convec HTC",
     ["no Velocity Force (n) Wear Rate Temp", "(rpm) (n) Radial Orbital Axial (m**3/s) (K) (W/m**2/K)"],
     (("orbit_speed", "rpm"), ("centrifugal_force", "N"), ("moving_radial_force", "N"),
      ("moving_orbital_force", "N"), ("moving_axial_force", "N"), ("wear_rate", "m3/s"),
      ("bulk_temperature", "K"), ("bulk_convection_htc", "W/m2/K"))),
)


def _optional_rows(lines, heading, headings, columns, count):
    if not any(" ".join(line.split()) == heading for line in lines):
        return None
    header = _header(lines, heading)
    if [line.split() for line in lines[header + 1:header + 1 + len(headings)]] != [line.split() for line in headings]:
        raise ResultParseError("OUT.txt", f"unexpected units or columns for {heading}", line=header + 1)
    rows = _table(lines, header + 1 + len(headings), columns, heading)
    if len(rows) != count:
        raise ResultParseError("OUT.txt", f"expected {count} rows for {heading}, found {len(rows)}", line=header + 1)
    return rows


def _additional_results(lines, contacts, count):
    sections = {}
    for name, heading, headings, fields in _PAIRED_SECTIONS:
        rows = _optional_rows(lines, heading, headings, 2 * len(fields), count)
        sections[name] = "NOT_PRESENT" if rows is None else "PARSED"
        for row, (line, tokens) in zip(contacts, rows or []):
            for column, (field, unit, scale, digits) in enumerate(fields):
                for side, race in enumerate(("outer", "inner")):
                    raw = tokens[2 * column + side]
                    row[race][field] = {"line": line, **(_temperature(raw, line) if unit == "degC"
                                                        else _metric(raw, unit, line, scale, digits))}
    elements = [{"rolling_element": i} for i in range(1, count + 1)]
    for name, heading, headings, fields in _KINEMATIC_SECTIONS:
        rows = _optional_rows(lines, heading, headings, len(fields), count)
        sections[name] = "NOT_PRESENT" if rows is None else "PARSED"
        for row, (line, tokens) in zip(elements, rows or []):
            row[name + "_line"] = line
            row.update({field: _metric(raw, unit, line) for (field, unit), raw in zip(fields, tokens)})
    return sections, elements


def _model_tables(lines):
    """Printed model outputs, with blank cells preserved by fixed columns.

    Numerical finiteness does not establish model applicability. In particular,
    capacity values are not re-labelled as maximum contact stress or CAD Cr.
    """
    specs = (
        ("capacities", "Computed Dynamic Capacities at Heaviest Loaded Rolling Element on Primary Race Segments ***", 5,
         ["stress_outer", "stress_inner", "stress_element_outer", "stress_element_inner",
          "load_outer", "load_inner", "load_element_outer", "load_element_inner"], ["Pa"] * 4 + ["N"] * 4),
        ("basic_life", "Basic Life (Hours) with Various Life Models", 2,
         ["outer", "inner", "element", "bearing"], ["h"] * 4),
        ("modified_life", "Modified Life with Various Life Models", 3,
         [method + "_" + part for method in ("tallian", "stle") for part in ("outer", "inner", "element", "bearing")], ["h"] * 8),
        ("life_factors", "Life Modification Factors with Various Life Models", 3,
         [method + "_" + part for method in ("tallian", "stle") for part in ("outer", "inner", "element", "bearing")], ["1"] * 8),
    )
    result = []
    for name, heading, offset, fields, units in specs:
        if not any(line.strip() == heading for line in lines):
            continue
        header = _header(lines, heading)
        column_header = lines[header + (3 if name == "capacities" else offset - 1)]
        columns = list(re.finditer(r"Outer Race|Inner Race|Roll Elem|Bearing|\.\.\.Rolling Element\.\.\.", column_header))
        # A capacity group contains two RE columns; printed numeric slots are
        # uniformly 11 characters wide, starting at the first race column.
        expected_columns = (["Outer Race", "Inner Race", "...Rolling Element..."] * 2 if name == "capacities"
                            else ["Outer Race", "Inner Race", "Roll Elem", "Bearing"] * (len(fields) // 4))
        if [column[0] for column in columns] != expected_columns or column_header[:columns[0].start()].strip() not in ("", "Model"):
            raise ResultParseError("OUT.txt", f"invalid {name} columns", line=header + 1)
        start = columns[0].end() - 10
        expected_positions = ([0, 1, 3, 4, 5, 7] if name == "capacities" else range(len(fields)))
        if any(col.end() != start + 10 + 11 * pos for col, pos in zip(columns, expected_positions)):
            raise ResultParseError("OUT.txt", f"invalid {name} fixed columns", line=header + 1)
        if name == "capacities":
            if (lines[header + 2].split() != ["(Pa)", "(n)"] or
                    lines[header + 4].split() != ["Outer", "Race", "Inner", "Race"] * 2):
                raise ResultParseError("OUT.txt", "unexpected capacities units or element columns", line=header + 1)
        if name in ("modified_life", "life_factors"):
            method_header = lines[header + 1]
            if not ("Tallian" in method_header and "STLE" in method_header and
                    method_header.index("Tallian") < method_header.index("STLE")):
                raise ResultParseError("OUT.txt", f"unexpected {name} method order", line=header + 1)
        rows = []
        for line, text in _block(lines, header + offset):
            if len(text) > start + 11 * len(fields) and text[start + 11 * len(fields):].strip():
                raise ResultParseError("OUT.txt", f"unexpected {name} trailing columns", line=line)
            model = text[:start].strip()
            if model not in ("Original LP", "Current LP", "GZ", "IH"):
                raise ResultParseError("OUT.txt", f"unsupported {name} model row", line=line)
            metrics = {}
            for i, (field, unit) in enumerate(zip(fields, units)):
                raw = text[start + 11 * i:start + 11 * (i + 1)].strip()
                metrics[field] = (_metric(raw, unit, line) if raw else
                                  {"value": None, "unit": unit, "raw": "", "status": "NOT_REPORTED"})
            rows.append({"model": model, "line": line, "metrics": metrics})
        if [row["model"] for row in rows] != ["Original LP", "Current LP", "GZ", "IH"]:
            raise ResultParseError("OUT.txt", f"incomplete {name} model rows", line=header + 1)
        result.append({"id": name, "heading": heading, "interpretation": "UNVERIFIED_MODEL_APPLICABILITY",
                       "columns": fields, "rows": rows})
    return result


def _sweep(lines: list[str]) -> list[dict]:
    header = _header(lines, "Race Angular Velocities Relative Race Displacements Stiffness Stiffness Stiffness")
    if [line.split() for line in lines[header + 1:header + 3]] != [
        ["Outer", "Inner", "x", "y", "z", "XX", "YY", "ZZ"],
        ["(rpm)"] * 2 + ["(m)"] * 3 + ["(n/m)"] * 3,
    ]:
        raise ResultParseError("OUT.txt", "unexpected stiffness sweep units or axes", line=header + 1)
    rows = _table(lines, header + 3, 8, "stiffness sweep", suffix=".")
    if not rows:
        raise ResultParseError("OUT.txt", "missing stiffness sweep rows", line=header + 1)
    return [
        {"point": index, "line": line, **{
            field: _metric(token, unit, line)
            for (field, unit), token in zip(_SWEEP_FIELDS, tokens)
        }}
        for index, (line, tokens) in enumerate(rows, 1)
    ]


def _scalar(lines: list[str], label: str, printed_unit: str, unit: str) -> dict:
    pattern = re.compile(rf"\b{label}\s+\({printed_unit}\)\s+(\S+)\s*$")
    for number, line in enumerate(lines, 1):
        match = pattern.search(line)
        if match:
            return {"line": number, **_metric(match[1], unit, number)}
    raise ResultParseError("OUT.txt", f"missing {label} ({printed_unit})")


def _check_footer(lines: list[str]) -> None:
    heading = _header(lines, ".....................Time Average Parameters.....................")
    rows = [line.split() for line in lines[heading + 4:] if line.strip()]
    if not rows or any(
        len(row) != 10 or not re.fullmatch(r"[0-9]+", row[0]) or
        not all(_NUMBER.fullmatch(token) or _NONFINITE.fullmatch(token) for token in row[1:])
        for row in rows
    ):
        raise ResultParseError("OUT.txt", "missing or incomplete Time Average Parameters footer", line=heading + 1)


def _nonfinite(lines: list[str], filename: str) -> list[dict]:
    life_rows = {}
    if filename == "OUT.txt":
        for index, line in enumerate(lines[:-2]):
            section = line.strip()
            if section not in _LIFE_UNITS or not all(name in lines[index + 1] for name in ("Tallian", "STLE")):
                continue
            header = lines[index + 2]
            columns = list(re.finditer(r"Outer Race|Inner Race|Roll Elem|Bearing", header))
            if [column[0] for column in columns] != ["Outer Race", "Inner Race", "Roll Elem", "Bearing"] * 2:
                continue
            positions = {column.end(): ("Tallian" if i < 4 else "STLE", column[0])
                         for i, column in enumerate(columns)}
            for number, row in _block(lines, index + 3):
                model = row[:columns[0].start()].strip()
                life_rows[number] = section, _LIFE_UNITS[section], model, positions
    evidence = []
    for number, line in enumerate(lines, 1):
        for match in _NONFINITE.finditer(line):
            entry = {"file": filename, "line": number, "column": match.start() + 1,
                     "raw": match[0], "source_line": line, "value": None,
                     "status": "INVALID", "cause": "UNKNOWN"}
            if number in life_rows:
                section, unit, model, positions = life_rows[number]
                method, component = positions.get(match.end(), (None, None))
                entry.update(section=section, unit=unit, model=model, method=method, component=component)
            evidence.append(entry)
    return evidence


def _execution(report: Mapping | None, family: str, files: dict) -> dict:
    if report is None:
        return {"status": "UNKNOWN", "exit_code": None}
    if not isinstance(report, Mapping):
        raise ResultParseError("solver_probe_report.json", "expected a JSON object")
    source = report.get("input")
    outputs = report.get("output_files")
    if (report.get("schema_version") != "bearing-cad.robas-solver-probe.v1"
            or report.get("stage") != "isolated_execution" or not isinstance(source, Mapping)
            or not isinstance(outputs, list) or not all(isinstance(item, Mapping) for item in outputs)):
        raise ResultParseError("solver_probe_report.json", "expected an isolated SOLVER-01 execution report")
    if source.get("family") != family or source.get("input_sha256") != files["DATA.txt"]["sha256"]:
        raise ResultParseError("solver_probe_report.json", "DATA.txt family or SHA-256 mismatch")
    for name in ("OUT.txt", "a0_Final"):
        expected = [item.get("sha256") for item in outputs if item.get("filename") == name]
        observed = [files[name]["sha256"]] if "sha256" in files[name] else []
        if expected != observed:
            raise ResultParseError("solver_probe_report.json", f"{name} SHA-256 mismatch")
    if not {"solver_executed", "process_exit_code", "output_status"}.issubset(report):
        raise ResultParseError("solver_probe_report.json", "missing execution fields")
    executed = report["solver_executed"]
    code = report["process_exit_code"]
    output = report["output_status"]
    if executed is True and type(code) is int:
        if code == 0 and output in ("OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF", "OUTPUT_ABSENT_OR_INVALID"):
            return {"status": "EXITED_ZERO", "exit_code": code}
        if code != 0 and output == "PROCESS_NONZERO_EXIT":
            return {"status": "EXITED_NONZERO", "exit_code": code}
    if code is None:
        if executed is True and output == "PROCESS_TIMEOUT":
            return {"status": "TIMEOUT", "exit_code": None}
        if executed is False and output in ("PROCESS_START_FAILED", "NOT_EXECUTED"):
            status = "START_FAILED" if output == "PROCESS_START_FAILED" else "NOT_EXECUTED"
            return {"status": status, "exit_code": None}
    raise ResultParseError(
        "solver_probe_report.json",
        "inconsistent execution fields (solver_executed, process_exit_code, output_status)",
    )


def parse_static_results(
    run_directory: str | Path, *, family: str, probe_report: Mapping | None = None,
) -> dict:
    """Read paired DATA/OUT and optional evidence, returning a JSON-safe result.

    Pass the same-run probe report to verify input/output hashes and read
    execution state. Without it, source binding is unverified. Metrics
    describe printed values, with convergence assessed separately.
    """
    if family not in _FAMILIES:
        raise ResultParseError("DATA.txt", "family must be ball or roller")
    document_type, bearing_code = _FAMILIES[family]
    folder = Path(run_directory)
    data = _read(folder / "DATA.txt", _MAX_INPUT)
    out = _read(folder / "OUT.txt", _MAX_OUTPUT)
    final = _read(folder / "a0_Final", _MAX_OUTPUT, optional=True)
    files = {
        "DATA.txt": {"sha256": sha256(data).hexdigest(), "size_bytes": len(data)},
        "OUT.txt": {"sha256": sha256(out).hexdigest(), "size_bytes": len(out)},
        "a0_Final": {"status": "MISSING"} if final is None else {
            "status": "PRESENT_UNINTERPRETED" if final else "EMPTY",
            "sha256": sha256(final).hexdigest(), "size_bytes": len(final),
        },
    }
    data_text = _decode(data, "DATA.txt")
    try:
        document = document_type.parse(data_text)
        count = int(document.value(5, "nRe"))
        if count < 1:
            raise ValueError("rec 3.2 nRe must be positive")
    except ValueError as exc:
        raise ResultParseError("DATA.txt", str(exc)) from exc
    execution = _execution(probe_report, family, files)
    lines = _lines(_decode(out, "OUT.txt"))
    version = _header(lines, "Version (RoBAS 8.11)")
    echo_header = _header(lines, "Listing of input data records")
    echo = {}
    for number, line in enumerate(lines[echo_header + 1:version], echo_header + 2):
        fields = line.split()
        if fields[:2] in (["rec", "1"], ["rec", "3.2"]):
            if fields[1] in echo:
                raise ResultParseError("OUT.txt", f"duplicate echoed rec {fields[1]}", line=number)
            echo[fields[1]] = fields[2:]
    if echo.get("1", [])[:1] != ["-1"] or echo.get("3.2", [])[:3] != ["1", bearing_code, str(count)]:
        raise ResultParseError("OUT.txt", "echoed mode, unit, family or nRe does not match DATA.txt")
    _check_footer(lines)
    evidence = _nonfinite(lines, "OUT.txt")
    if final:
        evidence.extend(_nonfinite(_lines(_decode(final, "a0_Final")), "a0_Final"))
    contacts = _contacts(lines, count)
    sections, elements = _additional_results(lines, contacts, count)
    summary = {
        "total_power_loss": _scalar(lines, "Total Power Loss", "W", "W"),
        "internal_clearance": _scalar(lines, "Internal Clearance", "m", "m"),
    }
    for key, label in (("outer_race_fit", "Outer Race Fit"), ("inner_race_fit", "Inner Race Fit")):
        if any(label in line for line in lines):
            summary[key] = _scalar(lines, label + r"\*?", "m", "m")
    # Exclude the DATA echo. Supplemental solver tables remain inspectable as
    # printed evidence even when their engineering interpretation is unaudited.
    report_start = next((i for i, line in enumerate(lines) if line.strip() == "1. Rolling Element Parameters"), version)
    return {
        "schema_version": "bearing-cad.robas-static-results.v1", "family": family,
        "files": files, "execution": execution, "convergence": {"status": "UNKNOWN"},
        "source_binding": (
            {"status": "UNVERIFIED", "evidence": "LIMITED_OUT_ECHO"} if probe_report is None
            else {"status": "HASH_VERIFIED", "evidence": "PROBE_REPORT_SHA256"}
        ),
        "output_status": "PARSED_SUPPORTED_SECTIONS", "rolling_element_count": count,
        "contacts": contacts, "stiffness_sweep": _sweep(lines), "summary": summary,
        "additional_sections": sections, "rolling_elements": elements,
        "model_tables": _model_tables(lines),
        "raw_report": {"file": "OUT.txt", "line": report_start + 1,
                       "status": "PRINTED_EVIDENCE_ONLY", "text": "\n".join(lines[report_start:])},
        "nonfinite_evidence": evidence,
    }

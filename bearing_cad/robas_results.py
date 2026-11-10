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
    executed = report.get("solver_executed")
    code = report.get("process_exit_code")
    output = report.get("output_status")
    if executed is True and type(code) is int:
        status = "EXITED_ZERO" if code == 0 else "EXITED_NONZERO"
    elif executed is True and code is None and output == "PROCESS_TIMEOUT":
        status = "TIMEOUT"
    elif executed is False and code is None:
        status = "START_FAILED" if output == "PROCESS_START_FAILED" else "NOT_EXECUTED"
    else:
        raise ResultParseError("solver_probe_report.json", "inconsistent execution fields")
    return {"status": status, "exit_code": code}


def parse_static_results(
    run_directory: str | Path, *, family: str, probe_report: Mapping | None = None,
) -> dict:
    """Read paired DATA/OUT and optional evidence, returning a JSON-safe result.

    Pass the existing probe's report to establish execution state and bind
    hashes. Metrics describe printed values. Convergence remains unknown.
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
    return {
        "schema_version": "bearing-cad.robas-static-results.v1", "family": family,
        "files": files, "execution": execution, "convergence": {"status": "UNKNOWN"},
        "output_status": "PARSED_SUPPORTED_SECTIONS", "rolling_element_count": count,
        "contacts": _contacts(lines, count), "stiffness_sweep": _sweep(lines),
        "summary": {
            "total_power_loss": _scalar(lines, "Total Power Loss", "W", "W"),
            "internal_clearance": _scalar(lines, "Internal Clearance", "m", "m"),
        },
        "nonfinite_evidence": evidence,
    }

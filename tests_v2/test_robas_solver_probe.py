"""Safe protocol probe tests; do not execute the proprietary RoBAS executable."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess

import pytest

from bearing_cad.robas_solver_probe import (
    ORIGINAL_ROBAS_EXE_SHA256, SolverProbeError, _RECORDS,
    inspect_executable, inspect_probe, inspect_static_input, main, run_probe,
)


def _test_pe() -> bytes:
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 128)
    data[128:132] = b"PE\x00\x00"
    data[132:134] = (0x014c).to_bytes(2, "little")
    return bytes(data)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "RoBAS_Resources"
    (root / "exe").mkdir(parents=True)
    original = root / "exe" / "RoBAS_v2.exe"
    original.write_bytes(_test_pe())
    digest = sha256(_test_pe()).hexdigest()
    data = tmp_path / "original_DATA.txt"
    return root, data, digest


def _input_data(path, family="ball", *, mode="-1"):
    lines = [
        "'" + rec + "'," + (mode if n == 0 else "0") + ",1"
        for n, rec in enumerate(_RECORDS[family])
    ]
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return path


def test_legacy_quasistatic_source_record_order_has_ball43_roller44():
    assert len(_RECORDS["ball"]) == 43
    assert len(_RECORDS["roller"]) == 44
    assert _RECORDS["ball"][10] == "rec 5A"
    assert _RECORDS["roller"][10:12] == ("rec 5B.1", "rec 5B.2")
    assert _RECORDS["ball"][13:15] == ("rec 7.2.x", "rec 7.2.x")
    assert _RECORDS["ball"][-1] == "rec 11"


@pytest.mark.parametrize("family,records", [("ball", 43), ("roller", 44)])
def test_input_contract_matches_legacy_static_source(source, family, records):
    root, data, digest = source
    _input_data(data, family)
    result = inspect_probe(
        resources=root, input_path=data, family=family, expected_sha=digest)
    assert result["input"]["record_count"] == records
    assert result["input"]["protocol_status"] == "SOURCE_STATIC_RECORD_LABELS_MATCH"
    assert result["input"]["numerical_fields_verified"] is False
    assert result["exe"]["pe_machine"] == "x86"
    assert result["exe"]["verified_source_archive_binary"] is False
    assert result["solver_executed"] is False
    assert result["solver_converged"] is None
    assert result["engineering_approved"] is False


def test_binary_source_digest_requires_exact_match(source):
    root, data, digest = source
    with pytest.raises(SolverProbeError, match="SHA-256 differs"):
        inspect_executable(root)
    assert ORIGINAL_ROBAS_EXE_SHA256 != digest
    assert inspect_executable(root, expected_sha=digest)["sha256"] == digest


def test_reject_modified_pe_mz_or_wrong_architecture(source):
    root, _, digest = source
    path = root / "exe" / "RoBAS_v2.exe"
    path.write_bytes(b"MZ" + bytes(1022))
    with pytest.raises(SolverProbeError, match="PE signature"):
        inspect_executable(root, expected_sha=sha256(path.read_bytes()).hexdigest())
    invalid = bytearray(_test_pe())
    invalid[132:134] = (0x8664).to_bytes(2, "little")
    path.write_bytes(invalid)
    with pytest.raises(SolverProbeError, match="x86"):
        inspect_executable(root, expected_sha=sha256(invalid).hexdigest())


def test_reject_wrong_family_record_order_and_dynamic_mode(source):
    _, data, _ = source
    _input_data(data, "ball")
    with pytest.raises(SolverProbeError, match="44 record lines"):
        inspect_static_input(data, family="roller")
    _input_data(data, "ball", mode="1")
    with pytest.raises(SolverProbeError, match="Mode=-1"):
        inspect_static_input(data, family="ball")
    _input_data(data, "ball")
    text = data.read_text(encoding="utf-8").replace(
        "'rec 5A'", "'rec 5B.1'")
    data.write_text(text, encoding="utf-8")
    with pytest.raises(SolverProbeError, match="record 11"):
        inspect_static_input(data, family="ball")


def test_isolated_fake_launcher_cannot_mutate_source_or_claim_solver_convergence(
        source, tmp_path):
    root, data, digest = source
    _input_data(data, "roller")
    before_exe = (root / "exe" / "RoBAS_v2.exe").read_bytes()
    before_input = data.read_bytes()
    observed = []

    def fake_launch(exe, cwd, timeout_s):
        observed.append((exe, cwd, timeout_s))
        assert exe.name == "RoBAS_v2.exe"
        assert exe.parent == cwd
        assert (cwd / "DATA.txt").read_bytes() == before_input
        (cwd / "OUT.txt").write_text("SOURCE_SIMULATED_NO_ACTUAL_ANALYSIS\n",
                                      encoding="utf-8")
        return subprocess.CompletedProcess([str(exe)], 0)

    result = run_probe(
        resources=root, input_path=data, family="roller",
        output_dir=tmp_path / "artifacts",
        timeout_s=17, _platform="Windows",
        expected_sha=digest, _launcher=fake_launch)
    assert observed and observed[0][2] == 17
    assert result["output_status"] == "OUTPUT_PRESENT_UNPARSED_NOT_CONVERGENCE_PROOF"
    assert result["solver_executed"] is True
    assert result["solver_converged"] is None
    assert result["engineering_approved"] is False
    assert len(result["output_files"]) == 1
    assert result["output_files"][0]["filename"] == "OUT.txt"
    assert (root / "exe" / "RoBAS_v2.exe").read_bytes() == before_exe
    assert data.read_bytes() == before_input
    assert json.loads((Path(result["run_directory"]) /
                       "solver_probe_report.json").read_text(encoding="utf-8")
                      )["output_status"] == result["output_status"]


def test_zero_exit_without_out_is_not_a_success(source, tmp_path):
    root, data, digest = source
    _input_data(data)
    result = run_probe(
        resources=root, input_path=data, family="ball",
        output_dir=tmp_path / "out", expected_sha=digest,
        _platform="Windows",
        _launcher=lambda exe, cwd, timeout: subprocess.CompletedProcess(
            [str(exe)], 0))
    assert result["output_status"] == "OUTPUT_ABSENT_OR_INVALID"
    assert result["solver_converged"] is None


@pytest.mark.parametrize("exit_code,status", [
    (17, "PROCESS_NONZERO_EXIT"),
    (0, "PROCESS_TIMEOUT"),
])
def test_failed_or_timed_out_process_is_reported_without_claiming_convergence(
        source, tmp_path, exit_code, status):
    root, data, digest = source
    _input_data(data)
    def fake_launch(exe, cwd, timeout):
        if status == "PROCESS_TIMEOUT":
            raise subprocess.TimeoutExpired([str(exe)], timeout)
        return subprocess.CompletedProcess([str(exe)], exit_code)
    result = run_probe(
        resources=root, input_path=data, family="ball",
        output_dir=tmp_path / status, expected_sha=digest,
        _platform="Windows", _launcher=fake_launch)
    assert result["output_status"] == status
    assert result["solver_converged"] is None
    assert (Path(result["run_directory"]) / "solver_probe_report.json").is_file()


def test_execution_is_windows_only_and_requires_valid_timeout(source, tmp_path):
    root, data, digest = source
    _input_data(data)
    with pytest.raises(SolverProbeError, match="Windows-only"):
        run_probe(resources=root, input_path=data, family="ball",
                  output_dir=tmp_path / "out", expected_sha=digest,
                  _platform="Linux")
    with pytest.raises(SolverProbeError, match="timeout_s"):
        run_probe(resources=root, input_path=data, family="ball",
                  output_dir=tmp_path / "out", expected_sha=digest,
                  _platform="Windows", timeout_s=0)
    assert not (tmp_path / "out").exists()


def test_cli_inspect_reports_mismatched_source_instead_of_executing(source, capsys):
    root, data, _ = source
    _input_data(data)
    code = main(["inspect", "--resources", str(root),
                 "--input", str(data), "--family", "ball"])
    assert code == 2
    assert "SHA-256 differs" in capsys.readouterr().err

def test_failed_process_start_is_never_marked_executed(source, tmp_path):
    root, data, digest = source
    _input_data(data)
    def broken_launcher(exe, cwd, timeout):
        raise OSError("load failure")
    result = run_probe(
        resources=root, input_path=data, family="ball",
        output_dir=tmp_path / "out", expected_sha=digest,
        _platform="Windows", _launcher=broken_launcher)
    assert result["output_status"] == "PROCESS_START_FAILED"
    assert result["solver_executed"] is False
    assert result["solver_converged"] is None

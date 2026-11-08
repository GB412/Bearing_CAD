"""Ball DATA serialization tests; private legacy reference files stay local."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bearing_cad.contracts import parse_request
from bearing_cad.robas_ball_input import (
    BALL_RECORD_LABELS, BallDataDocument, BallDataError, geometry_updates,
    update_ball_data,
)
from bearing_cad.robas_solver_probe import _RECORDS


ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "build" / "robas-solver01-acceptance-20261108"
CASES = json.loads((ROOT / "tests_v2" / "fixtures" / "robas_3d_cases.json").read_text())


def _case(case_id):
    return next(item["request"] for item in CASES["cases"] if item["case_id"] == case_id)


def _local_case_data(folder):
    matches = sorted(folder.rglob("DATA.txt")) if folder.is_dir() else []
    if not matches:
        pytest.skip("local RoBAS DATA reference is not part of the public repository")
    return matches[0]


def _synthetic_data():
    from bearing_cad.robas_ball_input import _RECORD_FIELDS
    lines = []
    for index, (label, fields) in enumerate(_RECORD_FIELDS):
        values = ["-1" if index == 0 and field == "Mode" else "1"
                  for field in fields]
        if label == "rec 2.3":
            values = [f"'file-{number}'" for number in range(10)]
        if label == "rec 3.1":
            values = ["'test-run'"]
        lines.append(",".join([f"'{label}'", *values]))
    return "\r\n".join(lines) + "\r\n"


def test_public_protocol_schema_round_trips_43_crlf_records():
    assert BALL_RECORD_LABELS == _RECORDS["ball"]
    source = _synthetic_data()
    parsed = BallDataDocument.parse(source)
    rendered = parsed.render()
    assert rendered.encode("utf-8").count(b"\r\n") == 43
    assert b"\r\r\n" not in rendered.encode("utf-8")
    assert BallDataDocument.parse(rendered).rows == parsed.rows


def test_geometry_mapping_uses_contract_units_and_robas_cage_formula():
    request = parse_request(_case("dgb_no_cage"))
    updates = geometry_updates(request)
    assert updates[(9, "brgBore")] == pytest.approx(0.04)
    assert updates[(9, "hsngOD")] == pytest.approx(0.07752)
    assert updates[(10, "raceCurFac1")] == pytest.approx(4.5 / 8)
    ball_mm = 8
    pocket_mm = 1.004 * ball_mm + 0.12
    expected_outer_mm = 60.8 - 0.6 * (pocket_mm - ball_mm)
    assert updates[(12, "cageDia1")] == pytest.approx(expected_outer_mm / 1000)


@pytest.mark.parametrize(("case_id", "source"), [
    ("dgb_no_cage", REAL / "real-DGB"),
    ("acb_25deg_window", REAL / "user-run-2304"),
])
def test_real_ball_data_is_read_only_and_updated_fields_match_mapping(case_id, source):
    source = _local_case_data(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    kwargs = {}
    if case_id.startswith("acb"):
        kwargs["analysis_shoulder_diameters_mm"] = (47.0, 61.0)
    request = parse_request(_case(case_id))
    result = update_ball_data(
        source, request, operating_updates={}, **kwargs)
    original = BallDataDocument.read(source)
    expected_updates = geometry_updates(request, **kwargs)
    assert len(result.rows) == 43
    assert result.rows[0][1] == "-1"
    assert result.value(5, "nRe") == "11"
    assert float(result.value(9, "brgBore")) == pytest.approx(0.04)
    assert float(result.value(9, "shftID")) == pytest.approx(0.008)
    assert float(result.value(9, "hsngOD")) == pytest.approx(0.07752)
    assert float(result.value(10, "bReDia")) == pytest.approx(0.008)
    assert float(result.value(10, "raceCurFac1")) == pytest.approx(4.5 / 8)
    assert float(result.value(12, "cageDia1")) > float(result.value(12, "cageDia2"))
    for row_index, (old_row, new_row) in enumerate(zip(original.rows, result.rows)):
        label, fields = (original.rows[row_index][0], new_row[1:])
        for column, field in enumerate(fields, 1):
            key = (row_index, fields_name := _record_fields(row_index)[column - 1])
            if key in expected_updates:
                assert float(new_row[column]) == pytest.approx(float(expected_updates[key]))
            else:
                assert new_row[column] == old_row[column], f"unexpected change at {label}.{fields_name}"
    assert b"\r\n" in result.render().encode()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_acb_requires_single_robas_sidewall_mapping():
    source = _local_case_data(REAL / "user-run-2304")
    with pytest.raises(BallDataError, match="sidewall diameters explicitly"):
        update_ball_data(source, parse_request(_case("acb_25deg_window")),
                         operating_updates={})


def test_ball_document_rejects_wrong_field_count():
    with pytest.raises(BallDataError, match="expects 14 values"):
        BallDataDocument.parse("'rec 1',-1\n" + "\n".join("'rec x',0" for _ in range(42)))


def test_custom_operating_value_overrides_only_requested_field():
    source = _local_case_data(REAL / "real-DGB")
    result = update_ball_data(
        source, parse_request(_case("dgb_no_cage")), operating_updates={(29, "appLoadX"): 1234.5})
    assert result.value(29, "appLoadX") == "1234.5"
    assert result.value(29, "appLoadZ") == "2000"


def _record_fields(index):
    from bearing_cad.robas_ball_input import _RECORD_FIELDS
    return _RECORD_FIELDS[index][1]


def test_rejects_nonfinite_and_misclassified_overrides():
    source = _local_case_data(REAL / "real-DGB")
    request = parse_request(_case("dgb_no_cage"))
    with pytest.raises(BallDataError, match="Non-finite"):
        update_ball_data(source, request, operating_updates={(29, "appLoadX"): float("nan")})
    with pytest.raises(BallDataError, match="Non-finite"):
        update_ball_data(source, request, operating_updates={(29, "appLoadX"): "Infinity"})
    with pytest.raises(BallDataError, match="outside their mapped scope"):
        update_ball_data(source, request, operating_updates={(15, "density"): 1})
    with pytest.raises(BallDataError, match="solver updates"):
        update_ball_data(source, request, operating_updates={},
                         solver_updates={(0, "Mode"): 1})

"""RoBAS ball DATA mapping against independent C# source traces."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bearing_cad.contracts import parse_request
from bearing_cad.robas_ball_input import (
    BALL_RECORD_LABELS, BallDataDocument, BallDataError,
    geometry_updates, update_ball_data,
)
from bearing_cad.robas_solver_probe import _RECORDS


ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "build" / "robas-solver01-acceptance-20261108"
CASES = json.loads((ROOT / "tests_v2" / "fixtures" / "robas_3d_cases.json").read_text())
DGB = REAL / "real-DGB"
ACB = REAL / "user-run-2304"
DGB_SHA256 = "b6610d150b0b8b05f0d024fe0c6fb90c1d4b270d5ef20f95398d48a6aa165a0f"
ACB_SHA256 = "9cb4e0e9b74e4e13a056a1e1afe2fbfa425645c8e65865b63c2fd3d3095617ef"


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


def _round_trip(data):
    return BallDataDocument.parse(data).render()


def test_public_protocol_schema_round_trips_43_crlf_records():
    assert BALL_RECORD_LABELS == _RECORDS["ball"]
    rendered = _round_trip(_synthetic_data())
    assert rendered.encode().count(b"\r\n") == 43
    assert b"\r\r\n" not in rendered.encode()
    assert BallDataDocument.parse(rendered).rows == BallDataDocument.parse(_synthetic_data()).rows


def test_dotnet_rounding_ties_to_even_and_cage_assignment_chain_boundaries():
    from bearing_cad.robas_ball_input import _dotnet_round, _straight_pocket_reference

    assert _dotnet_round(8.25, 1) == 8.2
    assert _dotnet_round(8.35, 1) == 8.4
    assert _dotnet_round(2.135, 2) == 2.13
    assert _dotnet_round(2.675, 2) == 2.68
    # Fixed reference values independently traced from constructor assignments
    # and the rounded public getters in BallRoller/StraightPocketCage/BaseCage.
    values = _straight_pocket_reference(ball_d_mm=8.0, width_mm=15.0,
                                        outer_sidewall_mm=60.8)
    assert values == {
        "ball_d_mm": 8.0,
        "pocket_d_mm": 8.2,
        "guide_gap_mm": pytest.approx(0.12),
        "cage_outer_mm": 60.68,
        "cage_inner_mm": 55.88,
        "cage_width_mm": 10.7,
        "pocket_clearance_mm": pytest.approx(0.1),
        "guide_width_mm": pytest.approx(2.354),
        "guide_position_mm": pytest.approx(5.35),
    }


def test_race_getter_precision_precedes_derived_shaft_and_housing_dimensions():
    request = parse_request(_case("dgb_no_cage"))
    request = replace(request, parameters={
        **request.parameters, "bore_d_mm": 40.006, "outside_d_mm": 80.006,
    })
    updates = geometry_updates(request, analysis_inner_race_outside_diameter_mm=50.0)
    # BaseInnerRace/BaseOuterRace getters round to 0.01 mm before the
    # original analysis derives shaft ID and housing OD.
    assert updates[(9, "brgBore")] == pytest.approx(0.04001)
    assert updates[(9, "brgOD")] == pytest.approx(0.08001)
    assert updates[(9, "shftID")] == pytest.approx(0.008002)
    assert updates[(9, "hsngOD")] == pytest.approx(0.0912114)


def test_acb_inner_sidewall_uses_one_decimal_getter_before_clearance():
    request = parse_request(_case("acb_25deg_window"))
    updates = geometry_updates(
        request, analysis_shoulder_diameters_mm=(75.94, 89.154),
        analysis_inner_race_outside_diameter_mm=75.904)
    # SingleRowAngularContactInnerRace.SidewallDiameter rounds to 0.1 mm;
    # outer race sidewall and the inner-race OD getter round to 0.01 mm.
    assert updates[(10, "shoulderDia2")] == pytest.approx(75.9 / 1000)
    assert updates[(10, "shoulderDia1")] == pytest.approx(89.15 / 1000)
    assert updates[(12, "cageCls2")] == pytest.approx(
        updates[(12, "cageDia2")] - 75.9 / 1000)


@pytest.mark.parametrize(("folder", "digest", "source_values"), [
    (DGB, DGB_SHA256, {
        "ball": 8.334, "pitch": 54.0, "width": 15.0, "outer_sidewall": 59.02,
        "inner_sidewall": 49.0, "inner_race_od": 49.0,
        "pocket": 8.5, "guide_gap": 0.0996, "cage_od": 58.92,
        "cage_id": 53.92, "cage_width": 11.0, "cage_cls1": 0.1,
        "cage_cls2": 4.92, "pocket_clearance": 0.083,
        "guide_width": 2.42, "guide_pos": 5.5, "guide_clearance": 4.92,
    }),
    (ACB, ACB_SHA256, {
        "ball": 11.0, "pitch": 82.5, "angle": 25.0, "width": 18.0,
        "outer_sidewall": 89.15, "inner_sidewall": 75.9, "inner_race_od": 75.9,
        "pocket": 11.2, "guide_gap": 0.12, "cage_od": 89.03,
        "cage_id": 82.43, "cage_width": 13.7, "cage_cls1": 0.12,
        "cage_cls2": 6.53, "pocket_clearance": 0.1,
        "guide_width": 3.014, "guide_pos": 6.85, "guide_clearance": 6.53,
    }),
])
def test_real_original_cases_match_independently_traced_csharp_values(folder, digest,
                                                                      source_values):
    path = _local_case_data(folder)
    raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert raw_hash == digest
    doc = BallDataDocument.read(path)
    # Actual source geometry/operating values are read from the real DATA, not
    # inferred from the different current CAD fixtures.
    assert float(doc.value(10, "bReDia")) == pytest.approx(source_values["ball"] / 1000)
    assert float(doc.value(10, "pitchDia")) == pytest.approx(source_values["pitch"] / 1000)
    assert float(doc.value(10, "shoulderDia1")) == pytest.approx(source_values["outer_sidewall"] / 1000)
    assert float(doc.value(10, "shoulderDia2")) == pytest.approx(source_values["inner_sidewall"] / 1000)
    if "angle" in source_values:
        assert float(doc.value(10, "freeConAngDeg")) == source_values["angle"]

    request = parse_request(_case(
        "dgb_no_cage" if folder == DGB else "acb_25deg_window"))
    request = replace(request, parameters={
        **request.parameters,
        "ball_d_mm": source_values["ball"],
        "pitch_d_mm": source_values["pitch"],
        "width_mm": source_values["width"],
        "inner_shoulder_d_mm": source_values["inner_sidewall"],
        "outer_shoulder_d_mm": source_values["outer_sidewall"],
    })
    analysis_sidewalls = ((source_values["inner_sidewall"],
                           source_values["outer_sidewall"])
                          if folder == ACB else None)
    python_values = geometry_updates(
        request,
        analysis_shoulder_diameters_mm=analysis_sidewalls,
        analysis_inner_race_outside_diameter_mm=source_values["inner_race_od"],
    )

    # These expected values are hand-traced from C# property access order:
    # Dw getter -> PocketDiameter getter -> GuideGap -> OutsideDiameter getter
    # -> InsideDiameter getter -> CalculateWidth -> Width getter.
    expected = {
        (12, "cageDia1"): source_values["cage_od"] / 1000,
        (12, "cageDia2"): source_values["cage_id"] / 1000,
        (12, "cageWidth"): source_values["cage_width"] / 1000,
        (12, "cageCls1"): source_values["cage_cls1"] / 1000,
        (12, "cageCls2"): source_values["cage_cls2"] / 1000,
        (12, "bPocCls1"): (source_values["pocket_clearance"] / 1000
                            if folder == DGB else source_values["pocket_clearance"]),
        (13, "cageGsDia1"): source_values["cage_id"] / 1000,
        (13, "cageGsWidth1"): source_values["guide_width"] / 1000,
        (13, "cageGsPos1"): source_values["guide_pos"] / 1000,
        (13, "cageGsCls1"): source_values["guide_clearance"] / 1000,
        (14, "cageGsDia2"): source_values["cage_id"] / 1000,
        (14, "cageGsWidth2"): source_values["guide_width"] / 1000,
        (14, "cageGsPos2"): source_values["guide_pos"] / 1000,
        (14, "cageGsCls2"): source_values["guide_clearance"] / 1000,
    }
    for (record, field), value in expected.items():
        assert float(python_values[(record, field)]) == pytest.approx(value, abs=1e-12), (record, field)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == raw_hash


def test_legacy_data_mode_is_explicit_and_preserves_original_geometry():
    path = _local_case_data(DGB)
    original = BallDataDocument.read(path)
    result = update_ball_data(path, None, geometry_mode="legacy_data",
                              operating_updates={})
    assert result.geometry_mode == "legacy_data"
    assert result.reference_data_sha256 == DGB_SHA256
    for record in (9, 10, 11, 12, 13, 14):
        assert result.rows[record] == original.rows[record]
    with pytest.raises(BallDataError, match="must not receive a CAD request"):
        update_ball_data(path, parse_request(_case("dgb_no_cage")),
                         geometry_mode="legacy_data", operating_updates={})


def test_cad_geometry_requires_mismatch_ack_and_sets_all_source_overrides():
    path = _local_case_data(DGB)
    request = parse_request(_case("dgb_no_cage"))
    kwargs = {"analysis_inner_race_outside_diameter_mm": 49.0}
    with pytest.raises(BallDataError, match="reference DATA geometry differs"):
        update_ball_data(path, request, geometry_mode="cad_geometry",
                         operating_updates={}, **kwargs)
    result = update_ball_data(path, request, geometry_mode="cad_geometry",
                              operating_updates={}, allow_reference_geometry_mismatch=True,
                              **kwargs)
    assert result.geometry_mode == "cad_geometry"
    assert result.value(5, "kBrg") == "1"
    assert result.value(5, "nRe") == "11"
    assert [result.value(7, f"kPltElemInd{n}") for n in range(1, 7)] == ["1", "12", "0", "0", "0", "0"]
    assert result.value(11, "kPoctype") == "0"
    # Independently traced for Dw=8, B=15, outer sidewall=60.8.
    expected = {
        (12, "cageDia1"): 0.06068,
        (12, "cageDia2"): 0.05588,
        (12, "cageWidth"): 0.0107,
        (12, "cageCls1"): 0.00012,
        (12, "cageCls2"): 0.00868,
        (12, "bPocCls1"): 0.0001,
        (13, "cageGsWidth1"): 0.002354,
        (13, "cageGsPos1"): 0.00535,
        (13, "cageGsCls1"): 0.00688,
        (14, "cageGsCls2"): 0.00688,
    }
    for (record, field), value in expected.items():
        assert float(result.value(record, field)) == pytest.approx(value)
    assert float(result.value(10, "raceCurFac1")) == pytest.approx(4.5 / 8)
    assert float(result.value(10, "raceCurFac2")) == pytest.approx(4.3 / 8)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == DGB_SHA256


def test_acb_requires_explicit_analysis_sidewalls_and_inner_race_od():
    path = _local_case_data(ACB)
    request = parse_request(_case("acb_25deg_window"))
    with pytest.raises(BallDataError, match="sidewall diameters explicitly"):
        geometry_updates(request, analysis_inner_race_outside_diameter_mm=50.0)
    with pytest.raises(BallDataError, match="inner_race_outside_diameter"):
        update_ball_data(path, request, geometry_mode="cad_geometry",
                         analysis_shoulder_diameters_mm=(47.0, 61.0),
                         operating_updates={}, allow_reference_geometry_mismatch=True)


def test_cad_dgb_and_acb_apply_distinct_cage_clearance_sources():
    # Build a valid profile from the original DATA rows. The two requests use
    # the same generic CAD dimensions but intentionally different analysis data.
    dgb = geometry_updates(parse_request(_case("dgb_no_cage")),
                           analysis_inner_race_outside_diameter_mm=50.0)
    acb = geometry_updates(parse_request(_case("acb_25deg_window")),
                           analysis_shoulder_diameters_mm=(47.0, 61.0),
                           analysis_inner_race_outside_diameter_mm=50.0)
    # DGB CageCls2 references the inner sidewall; both guide clearances use
    # the inner race OD. ACB CageCls2 references the same inner race OD.
    assert dgb[(12, "cageCls2")] == pytest.approx((55.88 - 47.2) / 1000)
    assert acb[(12, "cageCls2")] == pytest.approx((56.08 - 50.0) / 1000)
    assert dgb[(13, "cageGsCls1")] == pytest.approx((55.88 - 50.0) / 1000)
    assert dgb[(14, "cageGsCls2")] == pytest.approx((55.88 - 50.0) / 1000)
    assert acb[(13, "cageGsCls1")] == pytest.approx((56.08 - 50.0) / 1000)


def test_custom_operating_value_overrides_only_requested_field():
    path = _local_case_data(DGB)
    result = update_ball_data(path, None, geometry_mode="legacy_data",
                              operating_updates={(29, "appLoadX"): 1234.5})
    assert result.value(29, "appLoadX") == "1234.5"
    assert result.value(29, "appLoadZ") == "2000"


def test_rejects_nonfinite_and_misclassified_overrides():
    path = _local_case_data(DGB)
    with pytest.raises(BallDataError, match="Non-finite"):
        update_ball_data(path, None, geometry_mode="legacy_data",
                         operating_updates={(29, "appLoadX"): float("nan")})
    with pytest.raises(BallDataError, match="Non-finite"):
        update_ball_data(path, None, geometry_mode="legacy_data",
                         operating_updates={(29, "appLoadX"): "Infinity"})
    with pytest.raises(BallDataError, match="outside their mapped scope"):
        update_ball_data(path, None, geometry_mode="legacy_data",
                         operating_updates={(15, "density"): 1})
    with pytest.raises(BallDataError, match="solver updates"):
        update_ball_data(path, None, geometry_mode="legacy_data", operating_updates={},
                         solver_updates={(0, "Mode"): 1})


def test_reference_mode_cannot_silently_blend_geometry_and_profiles():
    path = _local_case_data(DGB)
    with pytest.raises(BallDataError, match="geometry_mode"):
        update_ball_data(path, None, geometry_mode="", operating_updates={})
    with pytest.raises(BallDataError, match="requires a confirmed BearingRequest"):
        update_ball_data(path, None, geometry_mode="cad_geometry", operating_updates={},
                         analysis_inner_race_outside_diameter_mm=49.0)

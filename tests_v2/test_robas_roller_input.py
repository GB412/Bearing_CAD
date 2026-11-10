"""N-type CRB DATA tests with independent RoBAS/N222 values."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from bearing_cad.contracts import CageSpec, parse_request
from bearing_cad.robas_roller_input import (
    ROLLER_RECORD_LABELS, RollerDataDocument, RollerDataError, _RECORD_FIELDS,
    geometry_updates, update_roller_data,
)
from bearing_cad.robas_solver_probe import _RECORDS, inspect_static_input


GOLDEN = (Path(__file__).resolve().parents[1] / "build" / "robas-solver01-acceptance-20261108"
          / "CRB-ui-run-20261108" / "DATA.txt")
GOLDEN_SHA256 = "e6c604dd32ceeac659e21edd32215d3f3218e3c53f954a1ef70736a94373d0f5"


def n222_request(**changes):
    return parse_request({
        "schema_version": "bearing-cad.request.v1", "bearing_type": "rolling.cylindrical_roller",
        "unit": "mm", "detail_level": "functional", "geometry_strategy": "explicit",
        "parameters": {
            "bore_d_mm": 110, "outside_d_mm": 200, "width_mm": 38,
            "roller_d_mm": 28, "roller_length_mm": 28, "pitch_d_mm": 155, "roller_count": 14,
            "configuration": "N", "inner_rib_tip_d_mm": 137.22, "outer_rib_tip_d_mm": 172.78,
            # CAD construction dimensions without direct DATA fields.
            "radial_clearance_mm": 0, "axial_clearance_mm": 0.1, "rib_width_mm": 3,
            **changes,
        },
    })


# Values traced from CRBGeometry, the component getters, BaseSolver and
# CylinderRollerBearing.SetAnalysisValue, cross-checked with the original DATA.
N222_ROWS = {
    5: (1, 2, 14, 1, 0, 0, 0, 0, 0, 0, 0, 0),
    6: (1, 1, 0, 1, 1, 1, 5, 0, 1, 1, 1, 1, 1, 1),
    7: (0, 0, 0, 0, 0, 2, 1, 15, 0, 0, 0, 0),
    9: (0.110, 0.200, 0.022, 0.228, 0.038, 0.038),
    10: (0.028, 1e10, 0.028, 0.028, 0.00025, 0.00025, 0.155, 0.00002),
    11: (28, 0, 0, 0.01, 28, 0, 1e-7, 1e-7),
    12: (0, 0, 0, 0, 2, 2, 1, 0, 2, 1, 1, 0, 0),
    13: (0.169, 0.1424, 0.03686, 0.00378, 0.0154, 0.28, 0, 0, 0),
    14: (0.169, 0.03686, 0.01843, 0.031),
    15: (0.169, 0.03686, 0.01843, 0.031),
}


@pytest.fixture
def reference(tmp_path):
    lines = []
    for index, (label, fields) in enumerate(_RECORD_FIELDS):
        values = N222_ROWS.get(index, (1,) * len(fields))
        if index == 0:
            values = (-1, *values[1:])
        if index == 3:
            values = [f"'file-{i}'" for i in range(10)]
        if index == 4:
            values = ("'synthetic-profile'",)
        lines.append(",".join((f"'{label}'", *map(str, values))))
    path = tmp_path / "DATA.txt"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode())
    return path


def overlay(path, request=None, **kwargs):
    return update_roller_data(path, request or n222_request(), reference_configuration="N",
                              geometry_mode="cad_geometry", operating_updates={}, **kwargs)


def test_n222_original_data_matches_source_assignments_and_full_overlay():
    if not GOLDEN.is_file():
        pytest.skip("local RoBAS N222 DATA is not part of the public repository")
    original = GOLDEN.read_bytes()
    assert sha256(original).hexdigest() == GOLDEN_SHA256
    assert inspect_static_input(GOLDEN, family="roller")["record_count"] == 44
    doc = RollerDataDocument.read(GOLDEN)
    for record, values in N222_ROWS.items():
        assert tuple(map(float, doc.rows[record][1:])) == pytest.approx(values, rel=1e-12, abs=1e-14)
    replay = update_roller_data(GOLDEN, None, reference_configuration="N", geometry_mode="legacy_data",
                                operating_updates={})
    assert replay.render().encode() == original
    generated = overlay(GOLDEN)
    assert generated.render().encode() == original
    assert generated.reference_data_sha256 == GOLDEN_SHA256
    assert GOLDEN.read_bytes() == original


def test_public_schema_roundtrip_and_linked_overrides(reference):
    assert ROLLER_RECORD_LABELS == _RECORDS["roller"]
    source = reference.read_bytes()
    doc = RollerDataDocument.read(reference)
    assert doc.render().encode() == source
    result = update_roller_data(
        reference, n222_request(), reference_configuration="N", geometry_mode="cad_geometry",
        operating_updates={(30, "appLoadX"): 4000, (31, "rpm1"): -500, (31, "rpm2"): 15000,
                           (33, "rpmRange12"): 16000},
        analysis_free_clearance_mm=0.04,
    )
    assert result.value(30, "appLoadX") == "4000"
    assert result.value(31, "rpm1") == result.value(33, "rpmRange21") == "-500"
    assert result.value(31, "rpm2") == "15000"
    assert result.value(33, "rpmRange12") == "16000"
    assert float(result.value(10, "freeIntCls")) == pytest.approx(0.00004)
    for index in (0, 1, 2, 3, 4, 8, *range(16, 30), *range(34, 44)):
        assert result.rows[index] == doc.rows[index]
    assert result.reference_data_sha256 == sha256(source).hexdigest()
    assert reference.read_bytes() == source


def test_rounding_order_precedes_setter_conversions():
    values = geometry_updates(n222_request(
        bore_d_mm=110.006, outside_d_mm=200.006, width_mm=38.006, pitch_d_mm=155.004,
        roller_d_mm=28.006, roller_length_mm=28.126, outer_rib_tip_d_mm=172.786,
    ))
    # C# cage OD takes the raw pitch and Dw before their getters round them.
    assert values[(13, "cageDia1")] == pytest.approx(0.16901)
    assert values[(13, "cageWidth")] == pytest.approx(0.03687)
    assert values[(13, "cageCls1")] == pytest.approx(0.00378)
    assert values[(13, "bPocCls1")] == pytest.approx(0.2801)
    assert values[(9, "shftID")] == pytest.approx(0.022002)
    assert values[(9, "hsngOD")] == pytest.approx(0.2280114)
    assert values[(10, "bReDia")] == pytest.approx(0.02801)
    assert values[(10, "pitchDia")] == pytest.approx(0.155)
    assert values[(10, "bReLen")] == pytest.approx(0.02813)
    assert values[(11, "raceLandLmt1")] == pytest.approx(28.13)


def test_geometry_mismatch_and_roller_count_linkage(reference):
    request = n222_request(roller_count=13)
    with pytest.raises(RollerDataError, match=r"rec 3\.2\.nRe"):
        overlay(reference, request)
    result = overlay(reference, request, allow_reference_geometry_mismatch=True)
    assert result.value(5, "nRe") == "13"
    assert result.value(7, "kPltElemInd2") == "14"
    assert float(result.value(10, "freeIntCls")) == pytest.approx(0.00002)


def test_cad_gap_requires_independent_solver_clearance(reference):
    request = n222_request(radial_clearance_mm=0.05)
    with pytest.raises(RollerDataError, match="analysis_free_clearance_mm"):
        overlay(reference, request, allow_reference_geometry_mismatch=True)
    result = overlay(reference, request, analysis_free_clearance_mm=0.07,
                     allow_reference_geometry_mismatch=True)
    assert float(result.value(13, "cageCls2")) == pytest.approx(0.0155)
    assert float(result.value(10, "freeIntCls")) == pytest.approx(0.00007)


def test_explicit_cad_cage_updates_linked_clearances_and_preserves_reference_fields(reference):
    original = RollerDataDocument.read(reference).with_updates({
        (13, "bPocCls2"): 0.0002, (13, "cageAngCut"): 2, (13, "cageConeAng"): 3,
    })
    reference.write_bytes(original.render().encode())
    request = replace(n222_request(), cage=CageSpec("cylindrical_window", 142.1, 169.5, 36.6, 0.3))
    result = overlay(reference, request, allow_reference_geometry_mismatch=True)
    assert tuple(map(float, result.rows[13][1:])) == pytest.approx(
        (0.1695, 0.1421, 0.0366, 0.00328, 0.0151, 0.3, 0.0002, 2, 3))
    assert tuple(map(float, result.rows[14][1:])) == pytest.approx((0.1695, 0.0366, 0.0183, 0.0305))
    assert tuple(map(float, result.rows[15][1:])) == pytest.approx((0.1695, 0.0366, 0.0183, 0.0305))


@pytest.mark.parametrize("configuration", ["NU", "NJ", "NF", "NUP"])
def test_unsupported_flange_configurations(reference, configuration):
    with pytest.raises(RollerDataError, match="parameters.configuration"):
        overlay(reference, n222_request(configuration=configuration))
    with pytest.raises(RollerDataError, match="reference_configuration"):
        update_roller_data(reference, None, reference_configuration=configuration, geometry_mode="legacy_data",
                           operating_updates={})


def test_rejects_unverified_profile_and_nonfinite_values(reference):
    request = n222_request()
    with pytest.raises(RollerDataError, match="roller_profile"):
        overlay(reference, n222_request(roller_profile="crowned", roller_crown_relief_mm=0.01))
    with pytest.raises(RollerDataError, match="analysis_free_clearance_mm"):
        overlay(reference, request, analysis_free_clearance_mm=float("nan"))
    with pytest.raises(RollerDataError, match=r"rec 9\.1\.1\.appLoadX"):
        update_roller_data(reference, request, reference_configuration="N", geometry_mode="cad_geometry",
                           operating_updates={(30, "appLoadX"): "nan"})
    with pytest.raises(RollerDataError, match="outside their mapped scope"):
        update_roller_data(reference, request, reference_configuration="N", geometry_mode="cad_geometry",
                           operating_updates={(16, "density"): 1000})
    with pytest.raises(RollerDataError, match=r"rec 1\.nStps"):
        overlay(reference, solver_updates={(0, "nStps"): 1.5})
    changed = RollerDataDocument.read(reference).with_updates({(5, "kFlngInd22"): 1})
    reference.write_bytes(changed.render().encode())
    with pytest.raises(RollerDataError, match="kFlngInd22"):
        overlay(reference)

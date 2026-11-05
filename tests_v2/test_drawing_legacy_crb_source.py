"""Original RoBAS cylindrical groove + integral-flange source dimensions."""
import pytest

from bearing_cad.drawing_legacy_crb_source import (
 derive_crb_source_drawing_values, _inner_coefficient, _outer_coefficient,
)
from bearing_cad.drawing_legacy_dimensions import common_dimensions

P={
 "bore_d_mm":40., "outside_d_mm":68., "width_mm":18.,
 "pitch_d_mm":54., "roller_d_mm":8., "roller_length_mm":12.,
 "configuration":"NJ", "radial_clearance_mm":0.,
 "inner_rib_tip_d_mm":49.4, "outer_rib_tip_d_mm":59.08,
}


def test_source_crb_zero_gap_rollers_and_real_flange_values():
    values,ev=derive_crb_source_drawing_values(P)
    assert values=={
      "inner_groove_d_mm":46., "outer_groove_d_mm":62.,
      "inner_sidewall_d_mm":49.4, "outer_sidewall_d_mm":59.08,
    }
    rendered=common_dimensions(P,values,"rolling.cylindrical_roller")
    assert rendered["De"]=="62.000±0.015"
    assert rendered["di"]=="46.000±0.015"
    assert rendered["Dd2"]=="59.1"
    assert rendered["d2"]=="49.4"
    assert len(ev["autofilled_input_keys"])==4


def test_custom_gap_does_not_claim_legacy_crb_surface_identity():
    values,ev=derive_crb_source_drawing_values({**P,"radial_clearance_mm":.1})
    assert values=={}
    assert "CRB_CUSTOM_PITCH_OR_RADIAL_GAP_NOT_ORIGINAL_ROBAS" in ev["warnings"]


def test_custom_flange_does_not_receive_original_sidewall_label():
    values,ev=derive_crb_source_drawing_values({**P,"inner_rib_tip_d_mm":49.45})
    assert "inner_sidewall_d_mm" not in values
    assert "outer_sidewall_d_mm" in values
    assert "CRB_INNER_RIB_DIFFERENT_FROM_ORIGINAL_SOURCE" in ev["warnings"]


def test_no_phantom_flange_dimensions_on_n_or_nu():
    n,_=derive_crb_source_drawing_values({**P,"configuration":"N"})
    nu,_=derive_crb_source_drawing_values({**P,"configuration":"NU"})
    assert "inner_sidewall_d_mm" in n and "outer_sidewall_d_mm" not in n
    assert "inner_sidewall_d_mm" not in nu and "outer_sidewall_d_mm" in nu


@pytest.mark.parametrize("d, expected",[(50,.425),(50.1,.405),(75,.405),(75.1,.365),(200,.365),(201,None)])
def test_inner_kd2_source_intervals(d,expected):
    assert _inner_coefficient(d)==expected


@pytest.mark.parametrize("d, expected",[(25,.425),(25.1,.405),(50,.405),(50.1,.365),(200,.365),(201,None)])
def test_outer_kd2_source_intervals(d,expected):
    assert _outer_coefficient(d)==expected

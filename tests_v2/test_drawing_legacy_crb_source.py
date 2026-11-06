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


def test_source_crb_rib_tip_uses_raw_groove_before_public_getter_rounding():
    # Original CRBGeometry: inner raw = Dpw - Dw = 46.002,
    # inner tip = 46.002 + .425*8.004 = 49.4037, getter => 49.40.
    # Premature rounding of the groove to 46.00 would lose the match.
    p={**P,"bore_d_mm":40.004,"outside_d_mm":68.008,
       "pitch_d_mm":54.006,"roller_d_mm":8.004,
       "inner_rib_tip_d_mm":49.4037,"outer_rib_tip_d_mm":59.08854}
    values,ev=derive_crb_source_drawing_values(p)
    assert values["inner_groove_d_mm"]==46.0
    assert values["outer_groove_d_mm"]==62.01
    assert values["inner_sidewall_d_mm"]==49.4
    assert values["outer_sidewall_d_mm"]==59.09
    assert ev["original_source_rib_tip_mm"]=={"inner":49.4,"outer":59.09}
    assert ev["original_source_rib_matches_cad"]=={"inner":True,"outer":True}


def test_crb_same_displayed_rib_tip_but_different_actual_cad_is_not_source_match():
    p={**P,"bore_d_mm":40.004,"outside_d_mm":68.008,
       "pitch_d_mm":54.006,"roller_d_mm":8.004,
       "inner_rib_tip_d_mm":49.40,"outer_rib_tip_d_mm":59.08854}
    values,ev=derive_crb_source_drawing_values(p)
    assert "inner_sidewall_d_mm" not in values
    assert values["outer_sidewall_d_mm"]==59.09
    assert ev["original_source_rib_tip_mm"]["inner"]==49.4
    assert ev["original_source_rib_matches_cad"]["inner"] is False
    assert "CRB_INNER_RIB_DIFFERENT_FROM_ORIGINAL_SOURCE" in ev["warnings"]


def test_crb_only_labels_flange_present_for_n_and_nu_even_in_diagnostics():
    n,ne=derive_crb_source_drawing_values({**P,"configuration":"N"})
    nu,nue=derive_crb_source_drawing_values({**P,"configuration":"NU"})
    assert set(ne["original_source_rib_tip_mm"])=={"inner"}
    assert set(nue["original_source_rib_tip_mm"])=={"outer"}
    assert "outer_sidewall_d_mm" not in n
    assert "inner_sidewall_d_mm" not in nu

"""Tests for the isolated RoBAS sizing and angular-contact source audit."""
import csv
import math
import pytest
from bearing_cad.robas_sizing import preliminary_sizes
from bearing_cad.legacy_geometry_review import review_angular_contact

def test_sizing_reads_external_tables(tmp_path):
    (tmp_path / "BallDB.csv").write_text("diameter(mm)\n4\n8\n9\n12\n")
    (tmp_path / "CylinderRollerDiameterDB.csv").write_text("Dw\n4\n8\n12\n")
    (tmp_path / "CylinderRollerDB.csv").write_text("Dw,Lw\n8,10\n8,14\n8,18\n")
    ball = preliminary_sizes(bearing_type="rolling.deep_groove_ball",
                             bore_d_mm=40, outside_d_mm=68, width_mm=18, tables_dir=tmp_path)
    assert ball["ball_or_roller_d_mm"] == 8
    assert ball["pitch_d_mm"] == 54
    assert ball["candidate_only"]
    roller = preliminary_sizes(bearing_type="rolling.cylindrical_roller",
                               bore_d_mm=40, outside_d_mm=68, width_mm=18, tables_dir=tmp_path)
    assert roller["roller_length_mm"] == 14
    assert roller["preliminary_roller_count"] >= 1
    with pytest.raises(ValueError):
        preliminary_sizes(bearing_type="rolling.deep_groove_ball",
                          bore_d_mm=68, outside_d_mm=40, width_mm=18, tables_dir=tmp_path)

def test_angular_source_audit_has_expected_nonzero_offset():
    report = review_angular_contact(dict(width_mm=15, ball_d_mm=8,
        pitch_d_mm=54, contact_angle_deg=25, inner_groove_radius_mm=4.3,
        outer_groove_radius_mm=4.5))
    assert report["status"] == "STATIC_SOURCE_COMPARISON_ONLY"
    geometry = report["geometry"]
    assert geometry["legacy_draw_torus_center_z_mm"] == 0
    assert geometry["occt_inner_torus_center_z_mm"] == pytest.approx(.3 * math.sin(math.radians(25)))
    assert geometry["legacy_cone_half_width_radial_change_mm"] > 0

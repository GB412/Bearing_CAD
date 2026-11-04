"""Tests for the isolated RoBAS sizing and angular-contact source audit."""
import csv
import math
import pytest
from bearing_cad.robas_sizing import preliminary_sizes, dgb_geometry_profile
from bearing_cad.legacy_geometry_review import review_angular_contact
from bearing_cad.contracts import parse_request
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.geometry_checks import inspect_solid
from test_contracts import deep_request

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

def test_dgb_geometry_profile_matches_the_robas_dgbgeometry_constructor(tmp_path):
    (tmp_path / "BallDB.csv").write_text(
        "diameter(mm)\n8\n8.33438\n8.5\n", encoding="utf-8")
    profile = dgb_geometry_profile(
        bore_d_mm=40, outside_d_mm=68, width_mm=15, tables_dir=tmp_path)
    p = profile["parameters"]
    assert profile["candidate_only"] is True
    assert profile["method"] == "RoBAS DGBGeometry(outsideDia, insideDia, width)"
    assert p["ball_d_mm"] == pytest.approx(8.33438)
    assert p["pitch_d_mm"] == 54
    assert p["ball_count"] == 11
    assert p["inner_groove_radius_mm"] == pytest.approx(4.2505338)
    assert p["outer_groove_radius_mm"] == pytest.approx(4.4172214)
    assert p["inner_shoulder_d_mm"] == pytest.approx(48.999372)
    assert p["outer_shoulder_d_mm"] == pytest.approx(59.013628)
    assert profile["intermediate"]["radial_clearance_mm"] == pytest.approx(.013)
    assert profile["simplified_cage_dimensions"]["inner_d_mm"] == pytest.approx(49.97935944)
    assert profile["simplified_cage_dimensions"]["outside_d_mm"] == pytest.approx(57.83335544)
    assert profile["simplified_cage_dimensions"]["width_mm"] == pytest.approx(14.25)
    assert profile["source_files"]["BallDB.csv"]
    assert "DGBOptimizer.Optimizer" in " ".join(profile["warnings"])


def test_dgb_geometry_profile_always_selects_a_real_balldb_entry(tmp_path):
    # BaseOptimizer.DetermineRollerDiameter can return its raw target if the
    # first CSV row is closest. The port deliberately returns a real table row.
    (tmp_path / "BallDB.csv").write_text("diameter(mm)\n8.5\n10\n", encoding="utf-8")
    profile = dgb_geometry_profile(
        bore_d_mm=40, outside_d_mm=68, width_mm=15, tables_dir=tmp_path)
    assert profile["parameters"]["ball_d_mm"] == 8.5


def test_dgb_geometry_profile_refuses_robas_zero_clearance_fallback(tmp_path):
    (tmp_path / "BallDB.csv").write_text("diameter(mm)\n8.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="radial-clearance table is undefined"):
        dgb_geometry_profile(
            bore_d_mm=200, outside_d_mm=228, width_mm=15, tables_dir=tmp_path)


def test_dgb_geometry_profile_builds_a_valid_simplified_cage_brep(tmp_path):
    (tmp_path / "BallDB.csv").write_text(
        "diameter(mm)\\n8\\n8.33438\\n8.5\\n", encoding="utf-8")
    profile = dgb_geometry_profile(
        bore_d_mm=40, outside_d_mm=68, width_mm=15, tables_dir=tmp_path)
    data = deep_request()
    data["parameters"].update(profile["parameters"])
    data["cage"] = {
        "kind": "simplified_annular",
        **profile["simplified_cage_dimensions"],
        "pocket_clearance_mm": 0.25,
    }
    model = build_deep_groove(parse_request(data))
    assert len(model.components) == 4
    assert len(model.instances) == 14
    assert all(inspect_solid(component.shape).valid for component in model.components)


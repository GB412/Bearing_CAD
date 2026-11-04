"""Local RoBAS StampingCage candidate route: strict, same-origin, no EXE."""
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

from test_robas_sizing_api import _request, _start, _stop


def _payload(**overrides):
    data = {
        "bearing_type": "rolling.deep_groove_ball",
        "bearing_model": "6008",
        "ball_d_mm": 8.33438,
        "pitch_d_mm": 54,
        "ball_count": 11,
        "bearing_width_mm": 15,
        "inner_shoulder_d_mm": 48.999372,
        "outer_shoulder_d_mm": 59.013628,
        "rivet_hole_clearance_mm": .05,
    }
    data.update(overrides)
    return data


def test_stamping_source_preset_works_without_robas_csv_or_exe():
    with TemporaryDirectory() as folder:
        server, thread = _start(Path(folder) / "artifacts")
        try:
            status, health = _request(server, "GET", "/api/v2/cad/status")
            assert status == 200
            assert health["robas_sizing_available"] is False
            assert health["robas_stamping_available"] is True
            status, profile = _request(server, "POST", "/api/v2/cad/sizing/dgb-stamping",
                                       _payload())
            assert status == 200
            assert profile["candidate_only"] is True
            assert profile["schema_version"] == "bearing-cad.robas-stamping-adapter.v1"
            assert profile["cad_cage"]["width_mm"] == 10.567818
            assert profile["cad_cage"]["board_thickness_mm"] == .7
            assert profile["cad_cage"]["rivet_shaft_d_mm"] == 1.0
            assert profile["cad_cage"]["rivet_hole_clearance_mm"] == .05
            assert profile["source_dimensions"]["width_radial_mm"] == pytest.approx(3.750471)
        finally:
            _stop(server, thread)


def test_stamping_source_preset_rejects_extra_fields_and_invalid_series():
    with TemporaryDirectory() as folder:
        server, thread = _start(Path(folder) / "artifacts")
        try:
            for payload in (_payload(untrusted=True),
                            _payload(bearing_model="6408"),
                            _payload(rivet_hole_clearance_mm=0)):
                status, result = _request(server, "POST",
                                          "/api/v2/cad/sizing/dgb-stamping", payload)
                assert status == 422
                assert result["error"]["error_code"] == "PARAMETER_INVALID"
            status, result = _request(server, "POST",
                                      "/api/v2/cad/sizing/dgb-stamping",
                                      _payload(bearing_type="rolling.cylindrical_roller"))
            assert status == 422
            assert result["error"]["error_code"] == "NOT_SUPPORTED"
        finally:
            _stop(server, thread)


def test_stamping_source_preset_rejects_cross_origin_posts():
    with TemporaryDirectory() as folder:
        server, thread = _start(Path(folder) / "artifacts")
        try:
            status, result = _request(server, "POST",
                                      "/api/v2/cad/sizing/dgb-stamping", _payload(),
                                      origin="http://evil.example")
            assert status == 403
            assert result["error"]["error_code"] == "ORIGIN_FORBIDDEN"
        finally:
            _stop(server, thread)

"""Contract test for SVG/DXF generated from synthetic OCCT rings."""
import json
from dataclasses import dataclass
import cadquery as cq
import ezdxf
from bearing_cad.rolling_drawings import generate_review_drawings

@dataclass
class Part:
    component_id: str
    shape: object

@dataclass
class Assembly:
    components: list

@dataclass
class Request:
    parameters: dict
    cage: object = None
    request_hash: str = "test-geometry-123"

def test_review_export(tmp_path):
    request = Request(dict(bore_d_mm=40., outside_d_mm=100., width_mm=20.,
                           pitch_d_mm=70., ball_d_mm=10., ball_count=12))
    model = Assembly([
        Part("inner_ring", cq.Workplane("XY").circle(30).circle(20).extrude(10, both=True).val()),
        Part("outer_ring", cq.Workplane("XY").circle(50).circle(40).extrude(10, both=True).val()),
        Part("ball", cq.Workplane("XY").sphere(5).val()),
    ])
    report = generate_review_drawings(request, model, tmp_path)
    assert report["request_hash"] == request.request_hash
    assert report["status"] == "DRAFT_NOT_FOR_MANUFACTURE"
    assert len(report["sheets"]) == 3
    for sheet in report["sheets"]:
        assert sheet["section_contours"] > 0
        svg = (tmp_path / sheet["svg"]).read_text(encoding="utf-8")
        assert "40" in svg and "100" in svg and "NOT FOR MANUFACTURE" in svg
        audit = ezdxf.readfile(tmp_path / sheet["dxf"]).audit()
        assert not audit.has_errors and not audit.fixes
    assert json.loads((tmp_path / "drawing_report.json").read_text())["request_hash"] == request.request_hash

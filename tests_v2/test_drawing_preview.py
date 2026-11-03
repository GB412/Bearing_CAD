"""The preview is derived from exported DXF and must not mutate its bytes."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET

import ezdxf
import pytest

from bearing_cad.drawing_preview import render_svg_preview


def test_realistic_robas_paper_frame_chinese_and_source_integrity(tmp_path: Path):
    source = tmp_path / "legacy.dxf"
    target = tmp_path / "legacy.svg"
    doc = ezdxf.new("R2007")
    doc.styles.new("HZ", dxfattribs={"font": "SIMPLEX", "bigfont": "HZTXT"})
    msp = doc.modelspace()
    # A legacy 210x300 mm paper frame; outlier text outside the border must
    # not determine the SVG viewport.
    for a, b in (
        ((40, 60), (250, 60)), ((250, 60), (250, 360)),
        ((250, 360), (40, 360)), ((40, 360), (40, 60)),
    ):
        msp.add_line(a, b)
    msp.add_text(r"\M+5C9EE\M+5B9B5", dxfattribs={
        "style": "HZ", "height": 3, "insert": (100, 340)
    })
    msp.add_text(r"\M+5B8D6 GCr15-GB/T18254", dxfattribs={
        "style": "HZ", "height": 2, "insert": (100, 80)
    })
    msp.add_text("OUTLIER", dxfattribs={
        "style": "Standard", "height": 1, "insert": (6000, 5000)
    })
    doc.saveas(source)
    hash_before = sha256(source.read_bytes()).hexdigest()

    report = render_svg_preview(source, target)
    assert report["paper_frame_detected"]
    assert report["legacy_text_decoded"] == 2
    assert sha256(source.read_bytes()).hexdigest() == hash_before

    root = ET.fromstring(target.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    view = list(map(float, root.attrib["viewBox"].split()))
    assert view[2] > 0 and view[3] > 0
    # Paper aspect ratio approx 210:300; not stretched by the outlier.
    assert 0.65 < view[2] / view[3] < 0.80
    assert "<path" in target.read_text(encoding="utf-8")
    # The delivered DXF still contains literal MIF and original HZ bigfont.
    original = ezdxf.readfile(source)
    assert any(r"\M+5C9EE" in e.dxf.text
               for e in original.modelspace().query("TEXT"))
    assert original.styles.get("HZ").dxf.bigfont == "HZTXT"


def test_fallback_to_content_bounds_without_paper_border(tmp_path: Path):
    source = tmp_path / "no_frame.dxf"
    target = tmp_path / "preview.svg"
    doc = ezdxf.new()
    doc.modelspace().add_circle((0, 0), 12)
    doc.saveas(source)
    report = render_svg_preview(source, target)
    assert report["paper_frame_detected"] is False
    assert report["legacy_text_decoded"] == 0
    assert ET.fromstring(target.read_text(encoding="utf-8")).tag.endswith("svg")


def test_dxf_document_still_valid_after_preview(tmp_path: Path):
    source = tmp_path / "text.dxf"
    target = tmp_path / "text.svg"
    doc = ezdxf.new()
    doc.modelspace().add_text("6208/P5", dxfattribs={"height": 4})
    doc.saveas(source)
    render_svg_preview(source, target)
    original = ezdxf.readfile(source)
    assert original.audit().errors == []
    assert [e.dxf.text for e in original.modelspace().query("TEXT")] == ["6208/P5"]

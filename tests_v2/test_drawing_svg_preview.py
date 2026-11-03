import xml.etree.ElementTree as ET
from hashlib import sha256

import ezdxf
import pytest

from bearing_cad.drawing_runner import DrawingExportError, _render_svg_preview, _PreviewFrontend


@pytest.mark.parametrize("start,end", [
    ((100, 200), (600, 500)),
    ((-700, -300), (-200, 0)),
    ((300, -800), (600, -300)),
])
def test_svg_preview_uses_content_bounds_with_four_percent_margin(tmp_path, start, end):
    document = ezdxf.new("R2013")
    modelspace = document.modelspace()
    modelspace.add_line(start, end)
    source = tmp_path / "outer_ring.dxf"
    preview = tmp_path / "outer_ring.svg"
    document.saveas(source)
    digest = sha256(source.read_bytes()).hexdigest()

    _render_svg_preview(source, preview)

    root = ET.parse(preview).getroot()
    width = float(root.attrib["width"].removesuffix("mm"))
    height = float(root.attrib["height"].removesuffix("mm"))
    view_width, view_height = map(float, root.attrib["viewBox"].split()[2:])

    # Both landscape and portrait content use 20 mm on every side, independent of origin.
    assert width == end[0] - start[0] + 40
    assert height == end[1] - start[1] + 40
    assert abs(view_width / view_height - width / height) < 0.002
    assert sha256(source.read_bytes()).hexdigest() == digest


def test_empty_drawing_reports_no_preview_content(tmp_path):
    source = tmp_path / "empty.dxf"
    ezdxf.new("R2013").saveas(source)
    with pytest.raises(DrawingExportError, match="empty DXF"):
        _render_svg_preview(source, tmp_path / "empty.svg")


def test_distant_entities_are_preserved_in_preview_bounds(tmp_path):
    source = tmp_path / "distant.dxf"
    document = ezdxf.new("R2013")
    document.modelspace().add_line((0, 0), (400, 300))
    document.modelspace().add_line((2000, 2000), (2010, 2010))
    document.saveas(source)
    _render_svg_preview(source, tmp_path / "distant.svg")
    root = ET.parse(tmp_path / "distant.svg").getroot()
    assert float(root.attrib["width"].removesuffix("mm")) > 2010


def test_mif_encoded_and_unicode_chinese_have_identical_preview(tmp_path):
    # CADImport preserves legacy MIF (code page 5 = cp936) in TEXT.
    # Rendering the escape sequence literally creates a very wide false bbox.
    previews = []
    for name, text in [("encoded", r"\M+5C9EE\M+5B9B5\M+5C7F2"), ("unicode", "深沟球")]:
        document = ezdxf.new("R2013")
        document.styles.new("HZ", dxfattribs={"font": "SIMPLEX", "bigfont": "HZTXT"})
        document.modelspace().add_text(text, dxfattribs={"style": "HZ", "height": 3})
        source = tmp_path / (name + ".dxf")
        document.saveas(source)
        before = source.read_bytes()
        preview = tmp_path / (name + ".svg")
        _render_svg_preview(source, preview)
        assert source.read_bytes() == before
        previews.append(preview.read_text(encoding="utf-8"))
    assert previews[0] == previews[1]


def test_preview_decodes_only_display_copy_and_preserves_properties(monkeypatch):
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.svg import SVGBackend
    from ezdxf.fonts.font_face import FontFace

    document = ezdxf.new()
    entity = document.modelspace().add_text(r"\M+5C9EE\M+5B9B5")
    context = RenderContext(document)
    properties = context.resolve_all(entity)
    original_font = properties.font
    preview_font = FontFace(filename="local-cjk.ttf")
    frontend = _PreviewFrontend(context, SVGBackend())
    frontend.cjk_font = preview_font
    observed = []
    monkeypatch.setattr(Frontend, "draw_text_entity", lambda self, text, props:
                        observed.append((text.dxf.text, props.font)))
    frontend.draw_text_entity(entity, properties)
    assert observed == [("深沟", preview_font)]
    assert entity.dxf.text == r"\M+5C9EE\M+5B9B5"
    assert properties.font == original_font


def test_missing_cjk_font_is_reported_without_changing_dxf(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr("bearing_cad.drawing_runner._preview_cjk_font", lambda: None)
    document = ezdxf.new()
    document.modelspace().add_text("技术要求")
    source = tmp_path / "missing-font.dxf"
    document.saveas(source)
    before = source.read_bytes()
    _render_svg_preview(source, tmp_path / "missing-font.svg")
    assert "no supported installed CJK font" in caplog.text
    assert source.read_bytes() == before

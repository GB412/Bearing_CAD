"""Readable SVG *preview* of RoBAS DXF, without changing the delivered DXF.

Original CADImport DWG -> DXF is the authority. This isolated renderer fixes
legacy MIF-encoded Chinese TEXT and frames the existing engineering drawing.
It never rewrites TEXT, STYLE, drawing geometry or fonts in the exported DXF.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import os
from pathlib import Path

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.svg import SVGBackend
from ezdxf.fonts import fonts
from ezdxf.lldxf.encoding import decode_dxf_unicode, decode_mif_to_unicode
from ezdxf.math import BoundingBox2d


# The TTF/TTC is used only by ezdxf's browser renderer; no font files are
# distributed. SHX bigfont rendering cannot reproduce original AutoCAD text
# when the font is unavailable. Windows typically provides YaHei or SimSun.
_CJK_FONT_CANDIDATES = (
    "msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc",
    "NotoSansCJK-Regular.ttc", "NotoSerifCJK-Regular.ttc",
)


def _cjk_preview_font() -> str | None:
    manager = fonts.font_manager
    preferred = os.environ.get("BEARING_CAD_SVG_FONT", "").strip()
    names = ((preferred,) if preferred else ()) + _CJK_FONT_CANDIDATES
    for name in names:
        if manager.has_font(name):
            return name
    # Some Windows ezdxf installations have not yet indexed the local font
    # directory; scan it for the preview renderer, not for CADImport/AutoCAD.
    if os.name == "nt":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        folder = Path(windir) / "Fonts"
        if folder.is_dir():
            try:
                manager.scan_folder(folder)
                for name in names:
                    if manager.has_font(name):
                        return name
            except (OSError, ValueError):
                pass
    return None


def _frame_bounds(modelspace) -> BoundingBox2d | None:
    """Find the largest *closed, axis-aligned* DWG paper border.

    RoBAS templates contain an A4-like frame made from four LINE entities.
    Using the frame rather than a remote stray entity for the SVG viewport
    prevents off-center previews. Never alter or discard any DXF entities.
    If no reliable frame is found, use SVGBackend's standard content bounds.
    """
    horizontals: dict[tuple[float, float], set[float]] = defaultdict(set)
    verticals: set[tuple[float, float, float]] = set()

    def q(value: float) -> float:
        return round(float(value), 2)

    for entity in modelspace.query("LINE"):
        a = entity.dxf.start
        b = entity.dxf.end
        if abs(a.y - b.y) < 0.01 and abs(a.x - b.x) >= 100:
            x0, x1 = sorted((q(a.x), q(b.x)))
            horizontals[(x0, x1)].add(q((a.y + b.y) / 2))
        if abs(a.x - b.x) < 0.01 and abs(a.y - b.y) >= 100:
            y0, y1 = sorted((q(a.y), q(b.y)))
            verticals.add((q((a.x + b.x) / 2), y0, y1))

    best: tuple[float, float, float, float] | None = None
    largest_area = 0.0
    for (x0, x1), levels in horizontals.items():
        for y0, y1 in combinations(sorted(levels), 2):
            width, height = x1 - x0, y1 - y0
            if height < 100 or not 0.4 <= width / height <= 3:
                continue
            if ((x0, y0, y1) not in verticals or
                    (x1, y0, y1) not in verticals):
                continue
            area = width * height
            if area > largest_area:
                largest_area = area
                best = (x0, y0, x1, y1)
    if best is None:
        return None
    x0, y0, x1, y1 = best
    margin = max(3.0, min(8.0, min(x1 - x0, y1 - y0) * 0.025))
    return BoundingBox2d([(x0 - margin, y0 - margin),
                          (x1 + margin, y1 + margin)])


def render_svg_preview(dxf_path: Path, svg_path: Path) -> dict:
    """Render independent SVG preview; return diagnostic metadata.

    DXF entity coordinates, text and font references on disk are immutable.
    This is not a manufacturing approval or a pixel-equivalent AutoCAD export.
    """
    document = ezdxf.readfile(str(dxf_path))
    frame = _frame_bounds(document.modelspace())
    fallback_font = _cjk_preview_font()
    decoded_count = 0
    # RoBAS's legacy CADImport DXFs use \M+5xxxx (GBK) for Chinese.
    # ezdxf's SVGBackend otherwise renders literal M+5xxxx strings as glyphs.
    # Include INSERT block definitions (and their ATTRIBs) in the preview-only
    # decoding pass, without changing the actual exported DXF.
    for block in document.blocks:
        for entity in block:
            if entity.dxftype() not in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
                continue
            original = entity.dxf.get("text", "")
            if not isinstance(original, str) or not original:
                continue
            converted = decode_dxf_unicode(decode_mif_to_unicode(original))
            if converted != original:
                entity.dxf.text = converted
                decoded_count += 1
    # Override only SHX *bigfont* styles in the ephemeral copy. The original
    # HZ style and HZTXT references are preserved in the DXF for AutoCAD.
    if fallback_font:
        for style in document.styles:
            if style.dxf.get("bigfont", ""):
                style.dxf.font = fallback_font
                style.dxf.bigfont = ""

    backend = SVGBackend()
    config = Configuration(
        color_policy=ColorPolicy.COLOR,
        background_policy=BackgroundPolicy.MODELSPACE,
        lineweight_scaling=0.5,
    )
    Frontend(RenderContext(document), backend, config).draw_layout(
        document.modelspace(), finalize=True)
    svg = backend.get_string(layout.Page(0, 0), render_box=frame)
    svg_path.write_text(svg, encoding="utf-8")
    return {
        "legacy_text_decoded": decoded_count,
        "paper_frame_detected": frame is not None,
        "preview_font": fallback_font,
        "preview_font_warning": (
            "CJK_PREVIEW_FONT_UNAVAILABLE"
            if decoded_count and not fallback_font else None
        ),
    }

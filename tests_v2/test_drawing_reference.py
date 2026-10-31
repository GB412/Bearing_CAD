"""Fidelity checker must preserve genuine RoBAS non-text geometry."""
import shutil

import ezdxf
import pytest

from bearing_cad.drawing_reference import compare_reference, summarize_dxf


def make_sample(path, text="d", extra_circle=False):
    doc=ezdxf.new("R2010")
    model=doc.modelspace()
    model.add_line((0,0),(10,10), dxfattribs={"layer":"GEOMETRY"})
    model.add_text(text, dxfattribs={"layer":"TEXT"})
    if extra_circle:
        model.add_circle((5,5),3,dxfattribs={"layer":"GEOMETRY"})
    doc.saveas(path)


def test_text_changes_not_geometry_changes(tmp_path):
    reference=tmp_path/"reference.dxf"
    labels_only=tmp_path/"labels.dxf"
    make_sample(reference,"d")
    make_sample(labels_only,"40")
    r=compare_reference(reference,labels_only)
    assert r["status"]=="STRUCTURE_MATCHED_UNREVIEWED"
    assert not r["blocking_findings"]
    assert not r["manufacturing_approved"]


def test_nontext_shape_changes_are_blocked(tmp_path):
    reference=tmp_path/"reference.dxf"
    modified=tmp_path/"modified.dxf"
    make_sample(reference)
    make_sample(modified,extra_circle=True)
    r=compare_reference(reference,modified)
    assert r["status"]=="STRUCTURE_MISMATCH"
    assert "NON_TEXT_ENTITY_TYPE_COUNTS_CHANGED" in r["blocking_findings"]


def test_nontext_bounds_changes_are_blocked(tmp_path):
    reference=tmp_path/"reference.dxf"
    modified=tmp_path/"modified.dxf"
    make_sample(reference)
    doc=ezdxf.new("R2010")
    doc.modelspace().add_line((0,0),(20,10), dxfattribs={"layer":"GEOMETRY"})
    doc.modelspace().add_text("40", dxfattribs={"layer":"TEXT"})
    doc.saveas(modified)
    r=compare_reference(reference,modified)
    assert "NON_TEXT_BOUNDS_CHANGED" in r["blocking_findings"]


def test_unsupported_tolerance_rejected(tmp_path):
    reference=tmp_path/"reference.dxf"
    make_sample(reference)
    with pytest.raises(ValueError):
        compare_reference(reference, reference, tolerance_mm=1.5)

"""Compare CADImport-exported DXF with genuine RoBAS reference DXF.

Text replacement is expected to change labels; non-TEXT entity counts,
layer membership and extents should remain stable. No factory approval inferred.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ezdxf import bbox, readfile

NON_GEOMETRY_TEXT = {"TEXT", "MTEXT", "ATTRIB"}


def summarize_dxf(path: Path) -> dict:
    doc = readfile(str(path))
    audit = doc.audit()
    if audit.errors:
        raise ValueError(f"Fatal DXF audit errors in {path}: {len(audit.errors)}")
    non_text = [e for e in doc.modelspace() if e.dxftype() not in NON_GEOMETRY_TEXT]
    types = dict(sorted(Counter(e.dxftype() for e in non_text).items()))
    layers = dict(sorted(Counter(e.dxf.layer for e in non_text).items()))
    bounds = bbox.extents(non_text, fast=True)
    return {
        "entity_type_counts": types,
        "non_text_layer_counts": layers,
        "non_text_entity_count": len(non_text),
        "non_text_bounds": (
            [list(map(float, bounds.extmin)), list(map(float, bounds.extmax))]
            if bounds.has_data else None
        ),
        "audit_fixes": len(audit.fixes),
        "audit_fix_codes": sorted(set(int(issue.code) for issue in audit.fixes)),
        "fatal_audit_errors": len(audit.errors),
    }


def compare_reference(reference: Path, generated: Path, tolerance_mm: float = 0.005) -> dict:
    """Reject missing non-text geometry; preserve known RoBAS DXF audit caveats."""
    if tolerance_mm <= 0 or tolerance_mm > 0.1:
        raise ValueError("Invalid DXF comparison tolerance")
    ref = summarize_dxf(Path(reference))
    actual = summarize_dxf(Path(generated))
    findings = []
    for key in ("entity_type_counts", "non_text_layer_counts"):
        if ref[key] != actual[key]:
            findings.append(f"NON_TEXT_{key.upper()}_CHANGED")
    a, b = ref["non_text_bounds"], actual["non_text_bounds"]
    if (a is None) != (b is None):
        findings.append("NON_TEXT_BOUNDS_MISSING")
    elif a and b and any(abs(x - y) > tolerance_mm
                         for va, vb in zip(a, b) for x, y in zip(va, vb)):
        findings.append("NON_TEXT_BOUNDS_CHANGED")
    # Original RoBAS DXFs often have recoverable dictionary handle issues
    # (ezdxf Auditor code 202). Do not mistake them for new geometry errors.
    non_fatal = []
    if ref["audit_fixes"] or actual["audit_fixes"]:
        non_fatal.append("DXF_LEGACY_METADATA_REPAIRS_REQUIRE_CAD_VIEWER_REVIEW")
    if set(actual["audit_fix_codes"]) - set(ref["audit_fix_codes"]):
        non_fatal.append("NEW_AUDITOR_FIX_CATEGORY")
    return {
        "status": "STRUCTURE_MATCHED_UNREVIEWED" if not findings else "STRUCTURE_MISMATCH",
        "reference": ref,
        "generated": actual,
        "blocking_findings": findings,
        "review_warnings": non_fatal,
        "manufacturing_approved": False,
    }

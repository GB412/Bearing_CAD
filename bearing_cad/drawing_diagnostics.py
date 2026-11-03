"""Report which *actually matched* RoBAS DWG TEXT keys remain blank.

SQLite's global unresolved_count is NOT a count of incomplete DXF annotations.
CADImport's matched_keys tells us which source-template TEXT was consumed.
No changes to the drawing, source DB, or the original replacement mapping.
"""
from __future__ import annotations

from collections import Counter


def _confirmed_rows(report: dict) -> tuple[set[str], set[str]]:
    if report.get("schema_version") != "robas.drawing.variables.v1":
        raise ValueError("Unexpected RoBAS drawing-variable report")
    values = report.get("variables")
    if not isinstance(values, list):
        raise ValueError("RoBAS variable rows must be a list")
    all_keys = set()
    blank_keys = set()
    for row in values:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("Invalid RoBAS variable row")
        key = row["name"]
        all_keys.add(key)
        if row.get("value") is None or row["value"] == "":
            blank_keys.add(key)
    return all_keys, blank_keys


def sheet_variable_diagnostics(report: dict, matched_keys: dict) -> dict:
    """Classify only keys confirmed by the licensed CADImport inspect/export.

    Count names separately from the number of matched TEXT entities; repeated
    occurrences and database duplicate rows must not inflate missing names.
    """
    all_keys, blank_keys = _confirmed_rows(report)
    if not isinstance(matched_keys, dict) or len(matched_keys) > 2000:
        raise ValueError("CADImport must report bounded matched_keys")
    observed = Counter()
    for key, count in matched_keys.items():
        if (not isinstance(key, str) or key not in all_keys or
                type(count) is not int or count < 1):
            raise ValueError("Invalid CADImport matched_key report")
        observed[key] += count
    used = set(observed)
    missing = sorted(used & blank_keys)
    return {
        "matched_variable_names": sorted(used),
        "matched_variable_count": len(used),
        "matched_text_entities": sum(observed.values()),
        "unfilled_variable_names": missing,
        "unfilled_variable_count": len(missing),
        "unfilled_text_entities": sum(observed[name] for name in missing),
        "variable_completeness": (
            "MATCHED_KEYS_HAVE_BLANKS" if missing else "MATCHED_KEYS_POPULATED_UNREVIEWED"
        ),
    }


def bundle_variable_diagnostics(report: dict, sheets: list[dict]) -> dict:
    """Keep database-wide blanks and current-template blanks distinct.

    A name absent from matched_keys of all four/five sheets is NOT evidence of
    a missing dimension in the delivered DXF. These checks also do not assess
    the correctness of nonblank values, manufacturing tolerances or CAD fonts.
    """
    _, blank = _confirmed_rows(report)
    used = set()
    matched_blank = set()
    for sheet in sheets:
        diagnosis = sheet["variable_diagnostics"]
        used.update(diagnosis["matched_variable_names"])
        matched_blank.update(diagnosis["unfilled_variable_names"])
    return {
        "matched_template_variable_names": sorted(used),
        "matched_template_variable_count": len(used),
        "unfilled_template_variable_names": sorted(matched_blank),
        "unfilled_template_variable_count": len(matched_blank),
        "unfilled_database_unused_names": sorted(blank - used),
        "unfilled_database_unused_count": len(blank - used),
        "diagnostic_status": (
            "USED_TEMPLATE_TEXT_UNFILLED" if matched_blank else
            "MATCHED_TEMPLATE_TEXT_POPULATED_UNREVIEWED"
        ),
        "note": (
            "Blank original SQLite variables outside the selected DWG TEXT are not "
            "missing dimensions in this drawing; nonblank texts still require "
            "engineering review."
        ),
    }

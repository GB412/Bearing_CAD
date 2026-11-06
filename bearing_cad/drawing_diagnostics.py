"""Report which *actually matched* RoBAS DWG TEXT keys remain blank.

SQLite's global unresolved_count is NOT a count of incomplete DXF annotations.
CADImport's matched_keys tells us which source-template TEXT was consumed.
No changes to the drawing, source DB, or the original replacement mapping.
"""
from __future__ import annotations

from collections import Counter
from .drawing_variables import _COMMON, _BALL, _ROLLER


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
    by_name = {}
    for row in report["variables"]:
        by_name.setdefault(row["name"], []).append(row)
    geometry_fields = dict(_COMMON)
    if report.get("bearing_type") == "rolling.cylindrical_roller":
        geometry_fields.update(_ROLLER)
    elif report.get("bearing_type") in (
            "rolling.deep_groove_ball", "rolling.angular_contact_ball"):
        geometry_fields.update(_BALL)
        if report["bearing_type"] == "rolling.angular_contact_ball":
            geometry_fields["alfa1"] = "contact_angle_deg"
    trace = []
    for key in sorted(used):
        rows = by_name[key]
        values = {None if row.get("value") is None else str(row["value"])
                  for row in rows}
        sources = sorted({str(row.get("source", "unknown")) for row in rows})
        review_flags = []
        if len(values) > 1:
            review_flags.append("CONFLICTING_DUPLICATE_SQLITE_VARIABLE_ROWS")
        entry = {
            "name": key,
            "matched_text_entities": observed[key],
            "row_indices": sorted(row["row_index"] for row in rows
                                  if type(row.get("row_index")) is int),
            "source_tags": sources,
            "requested_value": next(iter(values)) if len(values) == 1 else None,
            "state": ("TEMPLATE_USED_MISSING" if key in blank_keys
                      else "POPULATED_UNREVIEWED"),
            "review_flags": review_flags,
        }
        if key in geometry_fields and sources == ["confirmed_geometry"]:
            entry["confirmed_design_field"] = geometry_fields[key]
        trace.append(entry)
    return {
        "matched_variable_names": sorted(used),
        "matched_variable_count": len(used),
        "matched_variable_provenance": trace,
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
    ambiguous_rows = set()
    for sheet in sheets:
        diagnosis = sheet["variable_diagnostics"]
        used.update(diagnosis["matched_variable_names"])
        matched_blank.update(diagnosis["unfilled_variable_names"])
        ambiguous_rows.update(
            item["name"] for item in diagnosis.get("matched_variable_provenance", [])
            if "CONFLICTING_DUPLICATE_SQLITE_VARIABLE_ROWS" in item["review_flags"]
        )
    return {
        "matched_template_variable_names": sorted(used),
        "matched_template_variable_count": len(used),
        "unfilled_template_variable_names": sorted(matched_blank),
        "unfilled_template_variable_count": len(matched_blank),
        "source_conflict_template_variable_names": sorted(ambiguous_rows),
        "source_conflict_template_variable_count": len(ambiguous_rows),
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

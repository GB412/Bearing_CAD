"""An unused SQLite blank is not a missing dimension on the current DWG."""
import pytest

from bearing_cad.drawing_diagnostics import (
    sheet_variable_diagnostics, bundle_variable_diagnostics,
)


def report():
    return {
        "schema_version": "robas.drawing.variables.v1",
        "variables": [
            {"name": "W01", "value": None, "source": "sqlite_default"},
            {"name": "W01", "value": "", "source": "sqlite_default"},
            {"name": "C_", "value": "", "source": "sqlite_default"},
            {"name": "Cr", "value": "12.31", "source": "robas_load"},
            {"name": "@Dd", "value": "", "source": "sqlite_default"},
            {"name": "not_used", "value": None, "source": "sqlite_default"},
        ],
    }


def test_per_sheet_diagnostics_use_actual_cadimport_matches():
    r = report()
    assembly = sheet_variable_diagnostics(r, {"Cr": 2, "W01": 3})
    cage = sheet_variable_diagnostics(r, {"C_": 5, "Cr": 1})
    assert assembly["matched_variable_names"] == ["Cr", "W01"]
    assert assembly["matched_variable_count"] == 2
    assert assembly["matched_text_entities"] == 5
    assert assembly["unfilled_variable_names"] == ["W01"]
    assert assembly["unfilled_variable_count"] == 1
    assert assembly["unfilled_text_entities"] == 3
    assert cage["unfilled_variable_names"] == ["C_"]
    overall = bundle_variable_diagnostics(r, [
        {"view": "assembly", "variable_diagnostics": assembly},
        {"view": "cage", "variable_diagnostics": cage},
    ])
    assert overall["unfilled_template_variable_names"] == ["C_", "W01"]
    assert overall["unfilled_template_variable_count"] == 2
    assert overall["unfilled_database_unused_names"] == ["@Dd", "not_used"]
    assert overall["unfilled_database_unused_count"] == 2
    assert overall["diagnostic_status"] == "USED_TEMPLATE_TEXT_UNFILLED"
    # No database rows are changed by the diagnostic.
    assert r == report()


def test_duplicate_db_rows_do_not_inflate_missing_names():
    r = report()
    r["variables"].append({"name": "C_", "value": "", "source": "sqlite_default"})
    sheet = sheet_variable_diagnostics(r, {"C_": 10})
    assert sheet["matched_variable_count"] == 1
    assert sheet["unfilled_variable_count"] == 1
    assert sheet["unfilled_text_entities"] == 10


def test_blank_unused_db_variables_do_not_block_sheet_report():
    r = report()
    sheet = sheet_variable_diagnostics(r, {"Cr": 3})
    assert sheet["unfilled_variable_count"] == 0
    total = bundle_variable_diagnostics(r, [{"variable_diagnostics": sheet}])
    assert total["unfilled_template_variable_count"] == 0
    assert total["unfilled_database_unused_count"] == 4
    assert total["diagnostic_status"] == "MATCHED_TEMPLATE_TEXT_POPULATED_UNREVIEWED"


@pytest.mark.parametrize("bad", [
    None, [], {"absent": 1}, {"Cr": 0}, {"Cr": -1}, {"Cr": True},
    {"Cr": "2"}, {"Cr": 1.5},
])
def test_invalid_bridge_metadata_is_rejected(bad):
    with pytest.raises(ValueError):
        sheet_variable_diagnostics(report(), bad)


def test_per_sheet_provenance_reports_source_row_and_actual_design_parameter():
    report = {
        "schema_version": "robas.drawing.variables.v1",
        "bearing_type": "rolling.deep_groove_ball",
        "variables": [
            {"name": "Dd", "value": "68", "source": "confirmed_geometry",
             "row_index": 0},
            {"name": "Cr", "value": "11.31", "source": "robas_SetCADTextValue_ratings",
             "row_index": 1},
            {"name": "W16", "value": None, "source": "sqlite_default",
             "row_index": 2},
            {"name": "X", "value": "source", "source": "sqlite_default",
             "row_index": 3},
            {"name": "X", "value": "checked", "source": "explicit_checked_value",
             "row_index": 4},
            {"name": "unused", "value": None, "source": "sqlite_default",
             "row_index": 5},
        ],
    }
    sheet = sheet_variable_diagnostics(
        report, {"Dd": 3, "Cr": 2, "W16": 2, "X": 1})
    by_name = {item["name"]: item
               for item in sheet["matched_variable_provenance"]}
    assert by_name["Dd"]["confirmed_design_field"] == "outside_d_mm"
    assert by_name["Dd"]["requested_value"] == "68"
    assert by_name["Dd"]["row_indices"] == [0]
    assert by_name["Dd"]["matched_text_entities"] == 3
    assert by_name["Cr"]["source_tags"] == ["robas_SetCADTextValue_ratings"]
    assert by_name["W16"]["state"] == "TEMPLATE_USED_MISSING"
    assert by_name["W16"]["requested_value"] is None
    assert by_name["X"]["requested_value"] is None
    assert by_name["X"]["row_indices"] == [3, 4]
    assert by_name["X"]["review_flags"] == [
        "CONFLICTING_DUPLICATE_SQLITE_VARIABLE_ROWS"
    ]
    total = bundle_variable_diagnostics(report, [
        {"view": "assembly", "variable_diagnostics": sheet},
        {"view": "loose_rib", "variable_diagnostics":
             sheet_variable_diagnostics(report, {"W16": 1})},
    ])
    assert total["unfilled_template_variable_names"] == ["W16"]
    assert total["source_conflict_template_variable_names"] == ["X"]
    assert total["unfilled_database_unused_names"] == ["unused"]
    assert total["unfilled_template_variable_count"] == 1
    assert sheet["matched_text_entities"] == 8

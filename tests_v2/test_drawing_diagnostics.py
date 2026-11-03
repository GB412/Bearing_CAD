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

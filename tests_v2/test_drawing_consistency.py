"""PR-2D-08: verify drawing title/model against original RoBAS data, not guesses."""
from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from bearing_cad.drawing_consistency import (
    audit_drawing_design, effective_drawing_model,
    explicit_legacy_override_audit,
)
from bearing_cad.drawing_variables import DrawingDataError

DGB = "rolling.deep_groove_ball"
ACB = "rolling.angular_contact_ball"
CRB = "rolling.cylindrical_roller"
SIZE_6008 = {"bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15}
SIZE_6208 = {"bore_d_mm": 40, "outside_d_mm": 80, "width_mm": 18}


@pytest.fixture
def original_catalog(tmp_path):
    folder = tmp_path / "Data"
    folder.mkdir()
    with sqlite3.connect(folder / "BearingType.db") as db:
        db.execute(
            'CREATE TABLE "深沟球轴承型号目录" '
            '("model" TEXT, "d" REAL, "Dd" REAL, "B" REAL)'
        )
        db.executemany(
            'INSERT INTO "深沟球轴承型号目录" VALUES (?, ?, ?, ?)',
            [("6008", 40, 68, 15), ("6208", 40, 80, 18),
             ("6308", 40, 90, 23)],
        )
    return tmp_path


def audit(resources, kind=DGB, model="6008/P5", dimensions=SIZE_6008,
          configuration=None, series="0", grade="P5"):
    return audit_drawing_design(
        resources=resources, bearing_type=kind, parameters=dimensions,
        model_label=model, configuration=configuration,
        accuracy_class=grade, diameter_series=series,
    )


def test_original_catalog_identifies_actual_6008_nominals(original_catalog):
    result = audit(original_catalog)
    assert result["status"] == "SOURCE_MODEL_DIMENSIONS_MATCH_REQUEST"
    evidence = result["catalog_evidence"]
    assert evidence["source"] == "RoBAS_Resources/Data/BearingType.db"
    assert evidence["table"] == "深沟球轴承型号目录"
    assert evidence["expected_dimensions_mm"] == {
        "bore_d_mm": 40, "outside_d_mm": 68, "width_mm": 15,
    }
    assert len(evidence["sha256"]) == len(sha256().hexdigest())
    assert result["verifies_3d_brep"] is False


@pytest.mark.parametrize("model, expected", [
    ("6208/P5", "RoBAS catalog model 6208 dimensions disagree"),
    ("6308/P5", "RoBAS catalog model 6308 dimensions disagree"),
])
def test_wrong_standard_model_cannot_silently_label_different_cad(
        original_catalog, model, expected):
    with pytest.raises(DrawingDataError, match=expected):
        audit(original_catalog, model=model, dimensions=SIZE_6008, series=None)


def test_matching_6208_must_use_its_own_geometry_and_series(original_catalog):
    accepted = audit(
        original_catalog, model="6208/P5",
        dimensions=SIZE_6208, series="2")
    assert accepted["status"] == "SOURCE_MODEL_DIMENSIONS_MATCH_REQUEST"
    with pytest.raises(DrawingDataError, match="diameter series"):
        audit(original_catalog, model="6208/P5",
              dimensions=SIZE_6208, series="0")


def test_different_grade_is_not_relabelled_as_requested_grade(original_catalog):
    with pytest.raises(DrawingDataError, match="contradicts selected"):
        audit(original_catalog, model="6008/P4")


def test_unknown_custom_model_is_reviewable_not_made_up(original_catalog):
    result = audit(original_catalog, model="CUSTOM-40X68", series=None)
    assert result["status"] == "MODEL_DIMENSIONS_NOT_VERIFIABLE_REQUIRES_REVIEW"
    assert "MODEL_NOT_IN_SOURCE_CATALOG_REQUIRES_REVIEW" in result["warnings"]


def test_unavailable_catalog_is_reported_not_fabricated(tmp_path):
    result = audit(tmp_path)
    assert result["status"] == "MODEL_DIMENSIONS_NOT_VERIFIABLE_REQUIRES_REVIEW"
    assert "ORIGINAL_MODEL_CATALOG_UNAVAILABLE_REQUIRES_REVIEW" in result["warnings"]


def test_original_catalog_hash_changes_when_the_same_model_row_is_updated(
        original_catalog):
    before = audit(original_catalog)
    with sqlite3.connect(original_catalog / "Data" / "BearingType.db") as db:
        db.execute(
            'INSERT INTO "深沟球轴承型号目录" VALUES (?, ?, ?, ?)',
            ("6408", 40, 110, 27))
    after = audit(original_catalog)
    assert (before["catalog_evidence"]["sha256"] !=
            after["catalog_evidence"]["sha256"])


def test_source_catalog_has_no_claim_of_fully_verified_angular_sizes(
        original_catalog):
    result = audit(original_catalog, kind=ACB, model="7208/P5", series="2")
    assert result["status"] == "MODEL_DIMENSIONS_NOT_VERIFIABLE_REQUIRES_REVIEW"
    assert "NO_CONFIRMED_ROBAS_MODEL_DIMENSION_CATALOG" in result["warnings"]


@pytest.mark.parametrize("model, configuration", [
    ("NUP208", "NUP"), ("NU 208", "NU"), ("NJ208", "NJ"),
    ("NF208", "NF"), ("N208", "N"),
])
def test_roller_model_prefix_matches_actual_selected_template(
        original_catalog, model, configuration):
    result = audit(
        original_catalog, kind=CRB, model=model, series=None,
        configuration=configuration, grade=None)
    assert result["status"] == "MODEL_CONFIGURATION_PREFIX_MATCH_UNVERIFIED_DIMENSIONS"
    assert result["model_configuration"] == configuration


def test_roller_model_configuration_conflict_is_blocked(original_catalog):
    with pytest.raises(DrawingDataError, match="contradicts model prefix"):
        audit(original_catalog, kind=CRB, model="NU208",
              configuration="NUP", series=None, grade=None)


def test_custom_roller_model_remains_reviewable(original_catalog):
    result = audit(original_catalog, kind=CRB, model="CUSTOM-ROLLER",
                   configuration="NUP", series=None, grade=None)
    assert result["status"] == "MODEL_CONFIGURATION_NOT_VERIFIABLE_REQUIRES_REVIEW"


def test_final_model_label_from_checked_values_is_audited(original_catalog):
    final_report = {
        "schema_version": "robas.drawing.variables.v1",
        "variables": [
            {"name": "model", "value": "6208/P5", "source": "explicit_checked_value"},
        ],
    }
    checked_label = effective_drawing_model(final_report)
    assert checked_label == "6208/P5"
    with pytest.raises(DrawingDataError, match="dimensions disagree"):
        audit(original_catalog, model=checked_label)
    final_report["variables"].append(
        {"name": "model", "value": "6008/P5", "source": "sqlite_default"}
    )
    with pytest.raises(DrawingDataError, match="Conflicting duplicated"):
        effective_drawing_model(final_report)


def test_final_model_not_present_requires_no_assumed_standard(original_catalog):
    report = {"schema_version": "robas.drawing.variables.v1",
              "variables": [{"name": "model", "value": None}]}
    assert effective_drawing_model(report) is None
    assert audit(original_catalog, model=None)["status"] == "NO_MODEL_LABEL_TO_VALIDATE"


def test_checked_legacy_overrides_are_reported_not_automatically_certified():
    result = explicit_legacy_override_audit(
        {"inner_groove_d_mm": 46.0, "outer_groove_d_mm": 62.01},
        {"inner_groove_d_mm": 45.9, "custom_flag": 1},
    )
    assert result["overridden_source_keys"] == ["inner_groove_d_mm"]
    assert result["source_value_disagreement_keys"] == ["inner_groove_d_mm"]
    assert result["review_status"] == (
        "CALLER_INPUT_NOT_AUTOMATICALLY_ENGINEERING_APPROVED"
    )


def test_duplicate_accuracy_suffix_is_rejected_in_final_title(original_catalog):
    # The API already appends /P5 to the drawing model option, so callers
    # must not provide the suffix twice.
    with pytest.raises(DrawingDataError, match="repeated accuracy suffix"):
        audit(original_catalog, model="6008/P5/P5")

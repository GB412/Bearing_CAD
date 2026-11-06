"""Minimal source-backed drawing-label checks; never infer a 3D shape from DWG.

The original RoBAS BearingType.db contains a *partial* deep-groove model
catalog. Other series/configurations have no equivalent confirmed catalog
here, so unknown/custom model names remain reviewable rather than rejected.
"""
from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
import re
import sqlite3

from .drawing_variables import DrawingDataError

_CATALOG_NAME = "BearingType.db"
_CATALOG_TABLE = "深沟球轴承型号目录"
_GRADE_SUFFIX = re.compile(r"/(P0|P6|P5|P4|P2)$", re.IGNORECASE)
_DGB_SERIES = re.compile(r"^6([0234])\d{2,3}$")
_CRB_PREFIX = re.compile(r"^(NUP|NU|NJ|NF|N)\s*(?=\d)", re.IGNORECASE)
_DIMENSION_KEYS = ("bore_d_mm", "outside_d_mm", "width_mm")


def effective_drawing_model(report: dict) -> str | None:
    """Read the *final* model TEXT, including explicitly checked overrides."""
    if report.get("schema_version") != "robas.drawing.variables.v1":
        raise DrawingDataError("Invalid RoBAS drawing variable report")
    labels = {
        str(row["value"]).strip()
        for row in report.get("variables", ())
        if row.get("name") == "model" and row.get("value") not in (None, "")
    }
    if len(labels) > 1:
        raise DrawingDataError("Conflicting duplicated drawing model labels")
    return next(iter(labels)) if labels else None


def _confirmed_dimensions(parameters: dict) -> dict[str, float]:
    result = {}
    for key in _DIMENSION_KEYS:
        value = parameters.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise DrawingDataError("Invalid confirmed design dimension: " + key)
        result[key] = float(value)
    return result


def _original_dgb_catalog(resources: Path, model: str) -> dict:
    catalog = Path(resources) / "Data" / _CATALOG_NAME
    if catalog.is_symlink() or not catalog.is_file():
        return {"status": "ORIGINAL_MODEL_CATALOG_UNAVAILABLE_REQUIRES_REVIEW"}
    if catalog.stat().st_size > 16_000_000:
        raise DrawingDataError("Unexpectedly large original RoBAS model catalog")
    digest = sha256(catalog.read_bytes()).hexdigest()
    try:
        with sqlite3.connect(catalog.resolve().as_uri() + "?mode=ro", uri=True) as db:
            records = db.execute(
                'SELECT "d", "Dd", "B" FROM "深沟球轴承型号目录" '
                'WHERE "model" = ?', (model,)).fetchall()
    except sqlite3.DatabaseError as error:
        raise DrawingDataError("Original RoBAS model catalog is corrupt") from error
    evidence = {
        "source": "RoBAS_Resources/Data/" + _CATALOG_NAME,
        "table": _CATALOG_TABLE,
        "sha256": digest,
        "model": model,
    }
    if not records:
        return {**evidence, "status": "MODEL_NOT_IN_SOURCE_CATALOG_REQUIRES_REVIEW"}
    if len(records) != 1:
        raise DrawingDataError("Ambiguous duplicate model in original RoBAS catalog")
    numbers = records[0]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in numbers):
        raise DrawingDataError("Invalid dimension row in original RoBAS catalog")
    return {
        **evidence, "status": "EXACT_SOURCE_MODEL_ROW_FOUND",
        "expected_dimensions_mm": dict(zip(_DIMENSION_KEYS, map(float, numbers))),
    }


def audit_drawing_design(*, resources: Path, bearing_type: str,
                         parameters: dict, model_label: str | None,
                         configuration: str | None,
                         accuracy_class: str | None,
                         diameter_series: str | None) -> dict:
    """Check explicit drawing context against the confirmed design request.

    This is a model-label/nominal-parameter test, NOT a B-Rep verification or
    a manufacturing/ISO approval.
    """
    actual = _confirmed_dimensions(parameters)
    result = {
        "status": "NO_MODEL_LABEL_TO_VALIDATE",
        "model_label": model_label,
        "confirmed_request_dimensions_mm": actual,
        "configuration": configuration,
        "source": "confirmed_design_request",
        "verifies_3d_brep": False,
        "warnings": [],
    }
    if model_label is None:
        return result
    if not isinstance(model_label, str) or not model_label.strip():
        raise DrawingDataError("Invalid drawing model label")

    model = model_label.strip()
    if bearing_type in ("rolling.deep_groove_ball", "rolling.angular_contact_ball"):
        suffix = _GRADE_SUFFIX.search(model)
        if suffix is not None:
            grade = suffix.group(1).upper()
            if accuracy_class is not None and grade != accuracy_class:
                raise DrawingDataError(
                    f"Drawing model grade {grade} contradicts selected {accuracy_class}")
            model = model[:suffix.start()]
            if _GRADE_SUFFIX.search(model):
                raise DrawingDataError(
                    "Drawing model label has a repeated accuracy suffix; "
                    "provide the base model and select accuracy separately")
        result["catalog_model"] = model

    if bearing_type == "rolling.deep_groove_ball":
        catalog = _original_dgb_catalog(resources, model)
        result["catalog_evidence"] = catalog
        if catalog["status"] != "EXACT_SOURCE_MODEL_ROW_FOUND":
            result["status"] = "MODEL_DIMENSIONS_NOT_VERIFIABLE_REQUIRES_REVIEW"
            result["warnings"].append(catalog["status"])
            return result
        expected = catalog["expected_dimensions_mm"]
        mismatches = {
            key: {"source_mm": expected[key], "confirmed_request_mm": actual[key]}
            for key in _DIMENSION_KEYS
            if not math.isclose(actual[key], expected[key], rel_tol=0, abs_tol=1e-6)
        }
        if mismatches:
            raise DrawingDataError(
                f"RoBAS catalog model {model} dimensions disagree with confirmed "
                f"CAD d/D/B: catalog {expected}, request {actual}; choose the "
                "correct original model or an explicitly nonstandard label")
        series_match = _DGB_SERIES.fullmatch(model)
        if series_match and diameter_series is not None and (
                series_match.group(1) != diameter_series):
            raise DrawingDataError(
                f"RoBAS model {model} diameter series {series_match.group(1)} "
                f"contradicts selected drawing series {diameter_series}")
        result["status"] = "SOURCE_MODEL_DIMENSIONS_MATCH_REQUEST"
        return result

    if bearing_type == "rolling.cylindrical_roller":
        candidate = _CRB_PREFIX.match(model)
        if candidate:
            model_configuration = candidate.group(1).upper()
            if configuration is not None and model_configuration != configuration:
                raise DrawingDataError(
                    f"RoBAS roller drawing configuration {configuration} "
                    f"contradicts model prefix {model_configuration}")
            result["status"] = "MODEL_CONFIGURATION_PREFIX_MATCH_UNVERIFIED_DIMENSIONS"
            result["model_configuration"] = model_configuration
        else:
            result["status"] = "MODEL_CONFIGURATION_NOT_VERIFIABLE_REQUIRES_REVIEW"
            result["warnings"].append("UNKNOWN_ROLLER_MODEL_PREFIX")
        result["warnings"].append("NO_CONFIRMED_ROBAS_ROLLER_MODEL_DIMENSION_CATALOG")
        return result

    result["status"] = "MODEL_DIMENSIONS_NOT_VERIFIABLE_REQUIRES_REVIEW"
    result["warnings"].append("NO_CONFIRMED_ROBAS_MODEL_DIMENSION_CATALOG")
    return result


def explicit_legacy_override_audit(automatic: dict, supplied: dict | None) -> dict:
    """Explain manual legacy inputs without treating them as reviewed facts."""
    supplied = supplied or {}
    overlaps = set(automatic) & set(supplied)
    return {
        "caller_supplied_keys": sorted(supplied),
        "overridden_source_keys": sorted(overlaps),
        "source_value_disagreement_keys": sorted(
            key for key in overlaps if supplied[key] != automatic[key]
        ),
        "review_status": "CALLER_INPUT_NOT_AUTOMATICALLY_ENGINEERING_APPROVED",
    }

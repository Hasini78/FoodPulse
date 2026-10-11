"""Validate cleaned FoodPulse tables and write a JSON-ready report.

Critical errors fail the pipeline. Warnings are recorded and do not stop it.

Critical checks:

- Required columns exist.
- Primary keys are present and unique.
- Required fields are present after cleaning.
- Non-nullable foreign keys resolve. Nullable ``reviews.order_id`` may be
  missing, but a present value must exist on ``orders.id``.
- ``reviews.rating`` is an integer from 1 to 5.
- Prices, quantities, order totals, and discounts are not negative.
- Event timestamps fall between 1990-01-01 and 2100-01-01. Dates of birth
  fall between 1900-01-01 and the reference date.

Warnings:

- Documented optional columns are missing.
- A date is after the feature reference date.
- Order totals were flagged by the Tukey outlier rule.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from etl.transform.dataset_specs import DATASET_ORDER, DATASET_SPECS, DatasetSpec, ForeignKey
from etl.transform.parsing import parse_timestamps

logger = logging.getLogger(__name__)

MIN_EVENT_DATE = date(1990, 1, 1)
MAX_EVENT_DATE = date(2100, 1, 1)
MIN_BIRTH_DATE = date(1900, 1, 1)
VALID_RATINGS = {1, 2, 3, 4, 5}
NON_NEGATIVE_COLUMNS = {
    "orders": ("total_amount", "discount_used"),
    "food_items": ("price",),
    "order_items": ("unit_price", "subtotal"),
}


class CriticalValidationError(RuntimeError):
    """Raised when one or more datasets have critical validation errors."""

    def __init__(self, report: dict[str, Any]) -> None:
        lines = ["Validation failed with critical errors:"]
        for dataset in report.get("datasets", []):
            for error in dataset.get("critical_errors", []):
                lines.append(f"- {dataset['dataset']}: {error['message']}")
        super().__init__("\n".join(lines))
        self.report = report


def validate_all(
    frames: dict[str, pd.DataFrame],
    *,
    reference_date: date,
) -> dict[str, Any]:
    """Validate every known dataset and return the combined report."""
    dataset_reports = [
        validate_dataset(frames.get(name, pd.DataFrame()), name, frames, reference_date=reference_date)
        for name in DATASET_ORDER
        if name in frames
    ]
    return _overall_report(dataset_reports, reference_date)


def validate_dataset(
    df: pd.DataFrame,
    dataset: str,
    frames: dict[str, pd.DataFrame],
    *,
    reference_date: date,
) -> dict[str, Any]:
    """Validate one dataset against its column contract and related tables."""
    spec = DATASET_SPECS[dataset]
    passed: list[str] = []
    warnings: list[dict[str, Any]] = []
    critical: list[dict[str, Any]] = []

    missing_columns = [column for column in spec.columns if column not in df.columns]
    if missing_columns:
        critical.append(
            _issue(
                "required_columns",
                f"Missing required columns: {', '.join(missing_columns)}",
                len(missing_columns),
            )
        )
    else:
        passed.append("required_columns")

    if spec.primary_key in df.columns:
        _check_primary_key(df, spec, passed, critical)
    _check_required_values(df, spec, passed, critical)
    _check_foreign_keys(df, spec, frames, passed, critical)
    if dataset == "reviews":
        _check_ratings(df, passed, critical)
    _check_non_negative(df, dataset, passed, critical)
    if dataset == "order_items":
        _check_quantity(df, passed, critical)
    _check_dates(df, spec, reference_date, passed, warnings, critical)
    _check_optional_missing(df, spec, passed, warnings)
    if dataset == "orders":
        _check_outlier_warning(df, passed, warnings)

    status = "failed" if critical else "warning" if warnings else "passed"
    report = {
        "dataset": dataset,
        "rows_checked": int(len(df)),
        "passed_checks": passed,
        "warnings": warnings,
        "critical_errors": critical,
        "status": status,
    }
    logger.info("Validated %s: status=%s rows=%s", dataset, status, len(df))
    return report


def write_report(report: dict[str, Any], path: Path) -> None:
    """Write the validation report as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote validation report to %s", path)


def assert_no_critical_errors(report: dict[str, Any]) -> None:
    """Raise ``CriticalValidationError`` when the report status is failed."""
    if report.get("status") == "failed":
        raise CriticalValidationError(report)


def _check_primary_key(
    df: pd.DataFrame,
    spec: DatasetSpec,
    passed: list[str],
    critical: list[dict[str, Any]],
) -> None:
    key = spec.primary_key
    missing = int(df[key].isna().sum())
    if missing:
        critical.append(_issue("primary_key_present", f"{missing} rows are missing {key}", missing))
    else:
        passed.append("primary_key_present")
    duplicates = int(df[key].dropna().duplicated().sum())
    if duplicates:
        critical.append(_issue("primary_key_unique", f"{duplicates} duplicate {key} values", duplicates))
    else:
        passed.append("primary_key_unique")


def _check_required_values(
    df: pd.DataFrame,
    spec: DatasetSpec,
    passed: list[str],
    critical: list[dict[str, Any]],
) -> None:
    problems = 0
    details: list[str] = []
    for column in spec.non_nullable:
        if column not in df.columns or column == spec.primary_key:
            continue
        missing = int(df[column].isna().sum())
        if missing:
            problems += missing
            details.append(f"{column} ({missing})")
    if problems:
        critical.append(
            _issue(
                "required_values",
                "Missing or unparseable required values: " + ", ".join(details),
                problems,
            )
        )
    else:
        passed.append("required_values")


def _check_foreign_keys(
    df: pd.DataFrame,
    spec: DatasetSpec,
    frames: dict[str, pd.DataFrame],
    passed: list[str],
    critical: list[dict[str, Any]],
) -> None:
    if not spec.foreign_keys:
        passed.append("referential_integrity")
        return
    failures = 0
    details: list[str] = []
    for foreign_key in spec.foreign_keys:
        count, detail = _foreign_key_failures(df, foreign_key, frames)
        failures += count
        if detail:
            details.append(detail)
    if failures:
        critical.append(
            _issue("referential_integrity", "Referential integrity failures: " + "; ".join(details), failures)
        )
    else:
        passed.append("referential_integrity")


def _foreign_key_failures(
    df: pd.DataFrame,
    foreign_key: ForeignKey,
    frames: dict[str, pd.DataFrame],
) -> tuple[int, str]:
    if foreign_key.column not in df.columns:
        return 0, ""
    parent = frames.get(foreign_key.references)
    if parent is None or "id" not in parent.columns:
        return len(df), f"{foreign_key.column} has no parent dataset {foreign_key.references}"
    parent_ids = set(parent["id"].dropna().tolist())
    values = df[foreign_key.column]
    present = values.dropna()
    dangling = int((~present.isin(parent_ids)).sum())
    missing_required = 0 if foreign_key.nullable else int(values.isna().sum())
    total = dangling + missing_required
    if total == 0:
        return 0, ""
    return total, (
        f"{foreign_key.column}->{foreign_key.references}.id "
        f"dangling={dangling} missing={missing_required}"
    )


def _check_ratings(df: pd.DataFrame, passed: list[str], critical: list[dict[str, Any]]) -> None:
    if "rating" not in df.columns:
        return
    ratings = pd.to_numeric(df["rating"], errors="coerce")
    invalid = ratings.isna() | ~ratings.isin(VALID_RATINGS)
    # Integer check: 5.0 is valid, 4.5 is not. isin already rejects 4.5.
    count = int(invalid.sum())
    if count:
        critical.append(_issue("rating_range", f"{count} ratings are outside the integers 1 through 5", count))
    else:
        passed.append("rating_range")


def _check_non_negative(
    df: pd.DataFrame,
    dataset: str,
    passed: list[str],
    critical: list[dict[str, Any]],
) -> None:
    columns = NON_NEGATIVE_COLUMNS.get(dataset, ())
    if not columns:
        return
    problems = 0
    details: list[str] = []
    for column in columns:
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        count = int((numeric < 0).sum())
        if count:
            problems += count
            details.append(f"{column} ({count})")
    if problems:
        critical.append(_issue("non_negative_amounts", "Negative amounts: " + ", ".join(details), problems))
    else:
        passed.append("non_negative_amounts")


def _check_quantity(df: pd.DataFrame, passed: list[str], critical: list[dict[str, Any]]) -> None:
    if "quantity" not in df.columns:
        return
    quantity = pd.to_numeric(df["quantity"], errors="coerce")
    count = int((quantity.notna() & (quantity <= 0)).sum())
    if count:
        critical.append(_issue("positive_quantity", f"{count} order item quantities are not positive", count))
    else:
        passed.append("positive_quantity")


def _check_dates(
    df: pd.DataFrame,
    spec: DatasetSpec,
    reference_date: date,
    passed: list[str],
    warnings: list[dict[str, Any]],
    critical: list[dict[str, Any]],
) -> None:
    absurd = 0
    future = 0
    details: list[str] = []
    future_details: list[str] = []
    reference_end = (
        pd.Timestamp(reference_date).tz_localize("UTC")
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    )
    min_event = pd.Timestamp(MIN_EVENT_DATE, tz="UTC")
    max_event = pd.Timestamp(MAX_EVENT_DATE, tz="UTC")
    min_birth = pd.Timestamp(MIN_BIRTH_DATE, tz="UTC")
    for column in (*spec.datetime_columns, *spec.date_columns):
        if column not in df.columns:
            continue
        values = parse_timestamps(df[column])
        lower = min_birth if column in spec.date_columns else min_event
        bad = values.notna() & ((values < lower) | (values > max_event))
        late = values.notna() & (values > reference_end) & ~bad
        bad_count = int(bad.sum())
        late_count = int(late.sum())
        absurd += bad_count
        future += late_count
        if bad_count:
            details.append(f"{column} ({bad_count})")
        if late_count:
            future_details.append(f"{column} ({late_count})")
    if absurd:
        critical.append(
            _issue(
                "sensible_dates",
                "Dates outside the accepted range: " + ", ".join(details),
                absurd,
            )
        )
    else:
        passed.append("sensible_dates")
    if future:
        warnings.append(
            _issue(
                "dates_after_reference",
                "Dates after the reference date " + reference_date.isoformat() + ": " + ", ".join(future_details),
                future,
            )
        )


def _check_optional_missing(
    df: pd.DataFrame,
    spec: DatasetSpec,
    passed: list[str],
    warnings: list[dict[str, Any]],
) -> None:
    details: list[str] = []
    total = 0
    for column in spec.optional_nullable:
        if column not in df.columns:
            continue
        count = int(df[column].isna().sum())
        if count:
            total += count
            details.append(f"{column} ({count})")
    if total:
        warnings.append(
            _issue("optional_missing", "Optional values are missing: " + ", ".join(details), total)
        )
    else:
        passed.append("optional_values_present")


def _check_outlier_warning(
    df: pd.DataFrame,
    passed: list[str],
    warnings: list[dict[str, Any]],
) -> None:
    if "is_total_outlier" not in df.columns:
        return
    count = int(df["is_total_outlier"].fillna(False).sum())
    if count:
        warnings.append(
            _issue(
                "order_total_outliers",
                (
                    f"{count} order totals are outside Tukey 1.5-IQR fences. "
                    "total_amount is unchanged; total_amount_capped holds the clipped value. "
                    "The lower fence is never below 0."
                ),
                count,
            )
        )
    else:
        passed.append("order_total_outliers")


def _overall_report(dataset_reports: list[dict[str, Any]], reference_date: date) -> dict[str, Any]:
    if any(item["status"] == "failed" for item in dataset_reports):
        status = "failed"
    elif any(item["status"] == "warning" for item in dataset_reports):
        status = "warning"
    else:
        status = "passed"
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reference_date": reference_date.isoformat(),
        "status": status,
        "datasets": dataset_reports,
    }


def _issue(check: str, message: str, count: int) -> dict[str, Any]:
    return {"check": check, "message": message, "count": count}

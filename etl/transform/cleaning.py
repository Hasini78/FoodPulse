"""Reusable Pandas cleaning for FoodPulse sample tables.

Functions return new DataFrames and do not modify their inputs.

Missing-value rules (never invent identifiers):

- Primary keys and foreign keys are left missing when the source value is
  missing. Downstream validation treats a missing required key as critical.
- Empty strings in text columns become missing values. Optional text such as
  ``gender``, ``phone``, ``description``, and ``postal_code`` is not imputed.
- ``orders.discount_used`` is the only numeric fill. The ORM default is 0,
  so a missing discount is recorded as 0 (no discount).
- Unparseable numbers and timestamps become missing. The original token is
  not replaced with a guessed value.

Duplicate keys:

- Exact duplicate primary keys keep the first row and drop later copies.
- Rows with a missing primary key are kept; they are not collapsed together.
- Distinct ids are never removed because names, emails, or amounts match.

Order-total outliers:

- Method: Tukey fences on non-null ``total_amount``.
  ``IQR = Q3 - Q1``, ``lower = max(0, Q1 - 1.5 * IQR)``,
  ``upper = Q3 + 1.5 * IQR``.
- The lower fence is held at 0 so capping cannot invent a negative total.
- ``total_amount`` is unchanged. ``total_amount_capped`` holds the value
  clipped to ``[lower, upper]``. ``is_total_outlier`` marks values outside
  the fences. Fence values are repeated on each row so the method is
  recoverable from the output.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any

import pandas as pd

from etl.transform.dataset_specs import DATASET_SPECS, DatasetSpec
from etl.transform.parsing import parse_calendar_dates, parse_timestamps

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_TRUE_TOKENS = {"true", "t", "1", "yes", "y"}
_FALSE_TOKENS = {"false", "f", "0", "no", "n"}

OUTLIER_METHOD = "tukey_iqr_1.5_lower_fence_at_least_zero"


def clean_dataset(df: pd.DataFrame, dataset: str) -> pd.DataFrame:
    """Clean one sample table and return a new DataFrame."""
    spec = _require_spec(dataset)
    cleaned = df.copy(deep=True)
    cleaned = dedupe_by_primary_key(cleaned, spec.primary_key)
    cleaned = apply_missing_value_rules(cleaned, spec)
    cleaned = convert_types(cleaned, spec)
    if dataset == "reviews" and "review_text" in cleaned.columns:
        cleaned["review_text"] = cleaned["review_text"].map(normalize_review_text)
    if dataset == "orders":
        cleaned = flag_order_total_outliers(cleaned)
    if dataset == "orders" and "status" in cleaned.columns:
        cleaned["status"] = cleaned["status"].map(_normalize_status)
    logger.info("Cleaned %s: %s rows", dataset, len(cleaned))
    return cleaned


def dedupe_by_primary_key(df: pd.DataFrame, key: str = "id") -> pd.DataFrame:
    """Drop repeated primary keys, keeping the first row.

    Rows whose key is missing are preserved. Rows with different keys are
    preserved even when other columns match.
    """
    cleaned = df.copy(deep=True)
    if key not in cleaned.columns:
        return cleaned
    duplicate = cleaned[key].notna() & cleaned.duplicated(subset=[key], keep="first")
    removed = int(duplicate.sum())
    if removed:
        logger.info("Removed %s duplicate %s rows", removed, key)
    return cleaned.loc[~duplicate].reset_index(drop=True)


def apply_missing_value_rules(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    """Apply the documented per-column missing-value rules."""
    cleaned = df.copy(deep=True)
    for column in spec.text_columns:
        if column not in cleaned.columns:
            continue
        cleaned[column] = cleaned[column].map(_blank_to_missing)
    for column in spec.fill_zero:
        if column not in cleaned.columns:
            continue
        numeric = pd.to_numeric(cleaned[column], errors="coerce")
        cleaned[column] = numeric.fillna(0)
    return cleaned


def convert_types(df: pd.DataFrame, spec: DatasetSpec) -> pd.DataFrame:
    """Convert integer, float, boolean, date, and timestamp columns."""
    cleaned = df.copy(deep=True)
    for column in spec.integer_columns:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce").astype("Int64")
    for column in spec.float_columns:
        if column in cleaned.columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    for column in spec.boolean_columns:
        if column in cleaned.columns:
            cleaned[column] = _to_boolean(cleaned[column])
    for column in spec.datetime_columns:
        if column in cleaned.columns:
            cleaned[column] = parse_timestamps(cleaned[column])
    for column in spec.date_columns:
        if column in cleaned.columns:
            # Midnight timestamps keep the calendar date and write cleanly to Parquet.
            cleaned[column] = parse_calendar_dates(cleaned[column])
    for column in spec.text_columns:
        if column not in cleaned.columns:
            continue
        cleaned[column] = cleaned[column].map(_strip_text)
    return cleaned


def normalize_review_text(value: Any) -> str | None:
    """Strip HTML, trim, and lowercase review text.

    Negations, contrast words, and punctuation are preserved. ``"not good"``,
    ``"slow!"``, and ``"amazing but expensive"`` stay readable after casing
    and whitespace cleanup.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip().lower()
    return text or None


def flag_order_total_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Flag and cap ``total_amount`` outliers without replacing the original.

    See the module docstring for the Tukey fence definition.
    """
    cleaned = df.copy(deep=True)
    if "total_amount" not in cleaned.columns:
        return cleaned
    amounts = pd.to_numeric(cleaned["total_amount"], errors="coerce")
    observed = amounts.dropna()
    if observed.empty:
        lower, upper = 0.0, 0.0
    else:
        q1 = float(observed.quantile(0.25))
        q3 = float(observed.quantile(0.75))
        iqr = q3 - q1
        lower = max(0.0, q1 - 1.5 * iqr)
        upper = q3 + 1.5 * iqr
    outlier = amounts.notna() & ((amounts < lower) | (amounts > upper))
    cleaned["is_total_outlier"] = outlier.astype("boolean")
    cleaned["total_amount_capped"] = amounts.clip(lower=lower, upper=upper)
    cleaned["outlier_lower_fence"] = lower
    cleaned["outlier_upper_fence"] = upper
    cleaned["outlier_method"] = OUTLIER_METHOD
    logger.info(
        "Order total fences lower=%.2f upper=%.2f outliers=%s",
        lower,
        upper,
        int(outlier.sum()),
    )
    return cleaned


def _require_spec(dataset: str) -> DatasetSpec:
    try:
        return DATASET_SPECS[dataset]
    except KeyError as exc:
        known = ", ".join(DATASET_SPECS)
        raise KeyError(f"Unknown dataset '{dataset}'. Expected one of: {known}") from exc


def _blank_to_missing(value: Any) -> Any:
    if value is None:
        return pd.NA
    try:
        if pd.isna(value):
            return pd.NA
    except TypeError:
        pass
    if isinstance(value, str) and value.strip() == "":
        return pd.NA
    return value


def _strip_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return str(value).strip()


def _normalize_status(value: Any) -> str | None:
    text = _strip_text(value)
    if text is None:
        return None
    return text.lower()


def _to_boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype("boolean")

    def convert(value: Any) -> Any:
        if value is None:
            return pd.NA
        try:
            if pd.isna(value):
                return pd.NA
        except TypeError:
            pass
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        token = str(value).strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        return pd.NA

    return series.map(convert).astype("boolean")

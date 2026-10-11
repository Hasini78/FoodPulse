"""Classify inactivity without treating the score as a churn probability.

Categories come only from the inactivity rule. The score adds documented
points for recency and supporting behavior. There is no verified churn label,
so this module does not report accuracy, precision, recall, or ROC-AUC.
"""

from __future__ import annotations

import math

import pandas as pd

from mining.churn.features import BEHAVIOR_COLUMNS

ACTIVE = "active"
AT_RISK = "at_risk"
CHURNED = "churned_under_definition"
INSUFFICIENT = "insufficient_history"
CATEGORY_ORDER = (ACTIVE, AT_RISK, CHURNED, INSUFFICIENT)

RECENCY_CAP = 60.0
LOW_FREQUENCY_POINTS = 15.0
WIDENING_GAP_POINTS = 15.0
DECLINE_POINTS = 10.0
LOW_RATING_POINTS = 10.0
NEGATIVE_SENTIMENT_POINTS = 10.0
SCORE_MAX = 100.0
LOW_RATING_MAX = 2.5
NEGATIVE_SENTIMENT_MAX = -0.05
GAP_RATIO = 1.5

OUTPUT_COLUMNS = (
    *BEHAVIOR_COLUMNS,
    "risk_score",
    "risk_category",
    "reason_codes",
)

DEFINITION = (
    "A customer is churned_under_definition when the number of calendar days from "
    "their last completed order to the reference date is at least the inactivity window. "
    "Cancelled and pending orders do not reset that clock. "
    "churned_under_definition means inactive under this rule, not permanently lost. "
    "at_risk means inactivity is at least the at-risk threshold and still "
    "below the inactivity window. "
    "A customer whose first completed order is newer than the inactivity window is "
    "insufficient_history and is not flagged."
)


def validate_thresholds(inactivity_days: int, at_risk_days: int, low_frequency_max: int) -> None:
    """Reject thresholds that cannot define the windows."""
    _positive_int("inactivity_days", inactivity_days)
    _positive_int("at_risk_days", at_risk_days)
    _positive_int("low_frequency_max", low_frequency_max)
    if at_risk_days >= inactivity_days:
        raise ValueError("at_risk_days must be lower than inactivity_days")


def classify(
    behavior: pd.DataFrame,
    inactivity_days: int,
    at_risk_days: int,
    low_frequency_max: int,
) -> pd.DataFrame:
    """Add a category, reason codes, and a capped point score."""
    validate_thresholds(inactivity_days, at_risk_days, low_frequency_max)
    rows: list[dict[str, object]] = []
    for record in behavior.itertuples(index=False):
        reasons: list[str] = []
        observation = int(record.observation_days)
        inactivity = int(record.inactivity_days)
        if observation < inactivity_days:
            rows.append(_row(record, None, INSUFFICIENT, ["insufficient_history"]))
            continue
        if inactivity >= inactivity_days:
            category = CHURNED
            reasons.append("inactivity_window_met")
        elif inactivity >= at_risk_days:
            category = AT_RISK
            reasons.append("recency_at_risk_band")
        else:
            category = ACTIVE
        points = min(RECENCY_CAP, RECENCY_CAP * inactivity / inactivity_days)
        if int(record.order_frequency) <= low_frequency_max:
            points += LOW_FREQUENCY_POINTS
            reasons.append("low_order_frequency")
        if _gap_is_wide(record):
            points += WIDENING_GAP_POINTS
            reasons.append("current_gap_exceeds_typical")
        if observation >= 2 * at_risk_days and _frequency_declined(record):
            points += DECLINE_POINTS
            reasons.append("recent_frequency_decline")
        if _below(record.avg_rating, LOW_RATING_MAX):
            points += LOW_RATING_POINTS
            reasons.append("low_rating")
        if _below(record.avg_sentiment_score, NEGATIVE_SENTIMENT_MAX):
            points += NEGATIVE_SENTIMENT_POINTS
            reasons.append("negative_sentiment")
        rows.append(_row(record, min(SCORE_MAX, points), category, reasons))
    frame = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
    if frame.empty:
        return frame
    return frame.sort_values(["customer_id"]).reset_index(drop=True)


def summarize(classified: pd.DataFrame) -> pd.DataFrame:
    """Count customers and median behavior by category."""
    columns = [
        "risk_category",
        "customer_count",
        "share",
        "median_inactivity_days",
        "median_order_frequency",
        "median_total_spend",
        "median_avg_order_value",
        "median_avg_rating",
        "median_avg_sentiment_score",
    ]
    if classified.empty:
        return pd.DataFrame(columns=columns)
    total = len(classified)
    rows: list[dict[str, object]] = []
    for category in CATEGORY_ORDER:
        group = classified.loc[classified["risk_category"] == category]
        if group.empty:
            continue
        rows.append(
            {
                "risk_category": category,
                "customer_count": int(len(group)),
                "share": len(group) / total,
                "median_inactivity_days": _median(group["inactivity_days"]),
                "median_order_frequency": _median(group["order_frequency"]),
                "median_total_spend": _median(group["total_spend"]),
                "median_avg_order_value": _median(group["avg_order_value"]),
                "median_avg_rating": _median(group["avg_rating"]),
                "median_avg_sentiment_score": _median(group["avg_sentiment_score"]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def score_definition() -> dict[str, object]:
    """Return the point rules that produce the score."""
    return {
        "not_a_probability": (
            "risk_score is a sum of fixed points capped at 100. "
            "It is not a calibrated probability of leaving."
        ),
        "category_rule": DEFINITION,
        "points": {
            "recency": f"min({RECENCY_CAP:.0f}, {RECENCY_CAP:.0f} * inactivity_days / inactivity window)",
            "low_order_frequency": f"{LOW_FREQUENCY_POINTS:.0f} when completed-order count is at or below low_frequency_max",
            "current_gap_exceeds_typical": (
                f"{WIDENING_GAP_POINTS:.0f} when at least one closed gap exists and the current inactivity "
                f"is more than {GAP_RATIO} times the mean closed gap"
            ),
            "recent_frequency_decline": (
                f"{DECLINE_POINTS:.0f} when observation covers two at-risk windows and the recent window "
                "has fewer than half the completed orders of the prior window"
            ),
            "low_rating": f"{LOW_RATING_POINTS:.0f} when avg_rating is present and at or below {LOW_RATING_MAX}",
            "negative_sentiment": (
                f"{NEGATIVE_SENTIMENT_POINTS:.0f} when avg_sentiment_score is present and at or below {NEGATIVE_SENTIMENT_MAX}"
            ),
        },
        "missing_optional_features": "Missing rating or sentiment adds no points and is not treated as neutral.",
        "cap": SCORE_MAX,
        "insufficient_history_score": None,
    }


def _gap_is_wide(record: object) -> bool:
    mean_gap = getattr(record, "mean_purchase_gap_days")
    if mean_gap is None or (isinstance(mean_gap, float) and math.isnan(mean_gap)) or pd.isna(mean_gap):
        return False
    return float(getattr(record, "inactivity_days")) > GAP_RATIO * float(mean_gap)


def _frequency_declined(record: object) -> bool:
    prior = int(getattr(record, "prior_order_count"))
    recent = int(getattr(record, "recent_order_count"))
    return prior > 0 and recent * 2 < prior


def _below(value: object, limit: float) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return False
    return float(value) <= limit


def _row(record: object, score: float | None, category: str, reasons: list[str]) -> dict[str, object]:
    payload = {column: getattr(record, column) for column in BEHAVIOR_COLUMNS}
    payload["risk_score"] = score
    payload["risk_category"] = category
    payload["reason_codes"] = ",".join(sorted(set(reasons)))
    return payload


def _median(series: pd.Series) -> float | None:
    if series.dropna().empty:
        return None
    return float(series.median())


def _positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be an integer greater than or equal to 1")

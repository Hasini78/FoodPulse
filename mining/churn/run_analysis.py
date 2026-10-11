"""Score customer inactivity risk from processed FoodPulse tables.

From the repository root:

    python -m mining.churn.run_analysis --reference-date 2026-10-11 --inactivity-days 90 --at-risk-days 45

The command reads processed Parquet files and writes new churn outputs.
It does not modify the source files or connect to a database.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from etl.transform.feature_engineering import parse_reference_date
from mining.churn.analyze import DEFINITION, classify, score_definition, summarize, validate_thresholds
from mining.churn.features import build_behavior

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
ARTIFACTS = PROJECT_ROOT / "mining" / "churn" / "artifacts"

DEFAULT_INACTIVITY_DAYS = 90
DEFAULT_AT_RISK_DAYS = 45
DEFAULT_LOW_FREQUENCY_MAX = 4


def run_analysis(
    customers_path: Path,
    orders_path: Path,
    reviews_path: Path,
    sentiment_path: Path,
    output_dir: Path,
    artifacts_dir: Path,
    reference_date: str,
    inactivity_days: int,
    at_risk_days: int,
    low_frequency_max: int,
) -> dict[str, object]:
    """Build behavior rows, classify inactivity, and write the churn artifacts."""
    validate_thresholds(inactivity_days, at_risk_days, low_frequency_max)
    for path in (customers_path, orders_path, reviews_path, sentiment_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
    parsed_date = parse_reference_date(reference_date)
    customers = pd.read_parquet(customers_path)
    orders = pd.read_parquet(orders_path)
    reviews = pd.read_parquet(reviews_path)
    sentiment = pd.read_parquet(sentiment_path)
    behavior, stats = build_behavior(customers, orders, reviews, sentiment, parsed_date, at_risk_days)
    classified = classify(behavior, inactivity_days, at_risk_days, low_frequency_max)
    summary = summarize(classified)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    risk_path = output_dir / "customer_churn_risk.parquet"
    summary_path = output_dir / "customer_churn_summary.parquet"
    metrics_path = output_dir / "customer_churn_metrics.json"
    chart_path = artifacts_dir / "customer_churn_categories.png"
    classified.to_parquet(risk_path, index=False)
    summary.to_parquet(summary_path, index=False)
    if classified.empty:
        logger.info("No eligible customers, so no category chart was written")
        chart_written = False
    else:
        _plot(summary, chart_path)
        chart_written = True
    distribution = {
        str(row.risk_category): int(row.customer_count)
        for row in summary.itertuples(index=False)
    }
    payload: dict[str, object] = {
        "inputs": {
            "customer_features": str(customers_path),
            "orders": str(orders_path),
            "reviews": str(reviews_path),
            "review_sentiment": str(sentiment_path),
        },
        "reference_date": parsed_date.isoformat(),
        "definition": DEFINITION,
        "thresholds": {
            "inactivity_days": inactivity_days,
            "at_risk_days": at_risk_days,
            "low_frequency_max": low_frequency_max,
            "recent_window_days": at_risk_days,
        },
        "counts": stats,
        "category_distribution": distribution,
        "insufficient_history_not_flagged": int(distribution.get("insufficient_history", 0)),
        "feature_definitions": {
            "inactivity_days": "Calendar days from the last completed order to the reference date.",
            "observation_days": "Calendar days from the first completed order to the reference date.",
            "order_frequency": "Count of completed orders on or before the reference date.",
            "total_spend": "Sum of completed order totals. Line items and reviews are not joined.",
            "avg_order_value": "Mean completed order total.",
            "avg_discount": "Mean discount_used on those orders. A missing discount is treated as 0, matching the transform.",
            "discount_usage_rate": "Share of those orders with discount_used greater than 0.",
            "avg_rating": "Mean review rating on or before the reference date. Missing when the customer has no such review.",
            "avg_sentiment_score": "Mean VADER overall_score for those reviews. Missing when no score is linked.",
            "mean_purchase_gap_days": "Mean days between consecutive completed orders. Missing when the customer has one order.",
            "purchase_gap_std_days": "Sample standard deviation of those gaps. Missing when fewer than three orders exist.",
            "recent_order_count": "Completed orders in the at-risk window ending on the reference date.",
            "prior_order_count": "Completed orders in the at-risk window immediately before that.",
        },
        "score": score_definition(),
        "limitations": [
            "No verified churn label exists. The category is an inactivity rule, not proof that the customer is permanently lost.",
            "risk_score is not a probability and was not evaluated with accuracy, precision, recall, or ROC-AUC.",
            "Customers with no completed order on or before the reference date are excluded rather than labeled.",
            "Customers whose first completed order falls inside the inactivity window are marked insufficient_history and are not flagged.",
            "Cancelled and pending orders are ignored.",
            "A missing rating or sentiment score does not add risk points.",
            "The same dish, restaurant, or campaign is not identified as the cause of inactivity.",
        ],
        "artifacts": {
            "risk": str(risk_path),
            "summary": str(summary_path),
            "metrics": str(metrics_path),
            "category_chart": str(chart_path) if chart_written else None,
        },
    }
    metrics_path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")
    logger.info("Wrote inactivity categories for %s customers to %s", len(classified), risk_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Flag customers with no recent completed order. "
            "The score is a transparent point total, not a churn probability."
        )
    )
    parser.add_argument("--customers", type=Path, default=PROCESSED / "customer_features.parquet")
    parser.add_argument("--orders", type=Path, default=PROCESSED / "orders.parquet")
    parser.add_argument("--reviews", type=Path, default=PROCESSED / "reviews.parquet")
    parser.add_argument("--sentiment", type=Path, default=PROCESSED / "review_sentiment.parquet")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS)
    parser.add_argument(
        "--reference-date",
        default="2026-10-11",
        help="UTC calendar date. Completed orders and reviews after this date are ignored.",
    )
    parser.add_argument(
        "--inactivity-days",
        type=int,
        default=DEFAULT_INACTIVITY_DAYS,
        help=f"Days without a completed order before churned_under_definition. Default {DEFAULT_INACTIVITY_DAYS}.",
    )
    parser.add_argument(
        "--at-risk-days",
        type=int,
        default=DEFAULT_AT_RISK_DAYS,
        help=f"Days without a completed order before at_risk. Must be lower than the inactivity window. Default {DEFAULT_AT_RISK_DAYS}.",
    )
    parser.add_argument(
        "--low-frequency-max",
        type=int,
        default=DEFAULT_LOW_FREQUENCY_MAX,
        help=f"Completed-order count at or below this value adds low-frequency points. Default {DEFAULT_LOW_FREQUENCY_MAX}.",
    )
    args = parser.parse_args(argv)
    try:
        run_analysis(
            args.customers,
            args.orders,
            args.reviews,
            args.sentiment,
            args.output_dir,
            args.artifacts_dir,
            args.reference_date,
            args.inactivity_days,
            args.at_risk_days,
            args.low_frequency_max,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _plot(summary: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.bar(summary["risk_category"], summary["customer_count"])
    axis.set_xlabel("Category")
    axis.set_ylabel("Customers")
    axis.set_title("Customers by inactivity category")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    logger.info("Wrote category chart to %s", path)


def _json_ready(value: object) -> object:
    """Convert values so the metrics file is valid JSON."""
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, str):
        return value
    if pd.isna(value):
        return None
    return value


if __name__ == "__main__":
    sys.exit(main())

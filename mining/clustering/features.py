"""Customer features for segmentation.

Model columns, and why each one is included:

- ``recency_days``: days since the last completed order. Larger values mean a longer gap.
- ``order_frequency``: count of completed orders. Cancelled and pending orders are excluded.
- ``total_spend``: sum of completed ``total_amount`` values. Line items are not joined, so totals are not duplicated.
- ``avg_order_value``: mean completed order total.
- ``avg_discount``: mean ``discount_used`` on completed orders on or before the feature reference date. ``discount_usage_rate`` is only the share of orders with a discount, so the amount is derived from ``orders``.
- ``avg_rating``: mean star rating already aggregated per customer.
- ``avg_sentiment_score``: mean VADER ``overall_score``. Reviews are grouped by ``customer_id`` before any other join.

Identifiers, names, emails, and phone numbers are not model features. Missing ratings or sentiment scores are median-filled only inside the model matrix. The fill is recorded and is not written back to the source Parquet files.
"""

from __future__ import annotations

import logging

import pandas as pd
from sklearn.preprocessing import StandardScaler

from etl.transform.feature_engineering import end_of_reference_day, parse_reference_date

logger = logging.getLogger(__name__)

MODEL_FEATURES = (
    "recency_days",
    "order_frequency",
    "total_spend",
    "avg_order_value",
    "avg_discount",
    "avg_rating",
    "avg_sentiment_score",
)

FEATURE_REASONS = {
    "recency_days": "Days since the last completed order.",
    "order_frequency": "Number of completed orders, excluding cancelled and pending.",
    "total_spend": "Sum of completed order totals, without joining line items.",
    "avg_order_value": "Mean completed order total.",
    "avg_discount": "Mean discount amount on completed orders. Derived because the feature table stores a usage rate, not an amount.",
    "avg_rating": "Mean review rating aggregated per customer.",
    "avg_sentiment_score": "Mean VADER compound score aggregated from reviews to customers.",
}

REQUIRED_CUSTOMER_COLUMNS = (
    "customer_id",
    "recency_days",
    "order_frequency",
    "total_spend",
    "avg_order_value",
    "avg_rating",
    "feature_reference_date",
)


def prepare_model_frame(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    reviews: pd.DataFrame,
    sentiment: pd.DataFrame,
) -> tuple[pd.DataFrame, StandardScaler, dict[str, object]]:
    """Return one row per customer, a fitted scaler, and preparation notes."""
    _require_columns(customers, REQUIRED_CUSTOMER_COLUMNS, "customer features")
    _require_columns(orders, ("id", "customer_id", "discount_used", "status", "order_date"), "orders")
    _require_columns(reviews, ("id", "customer_id"), "reviews")
    _require_columns(sentiment, ("review_id", "overall_score"), "review sentiment")

    base = customers.drop_duplicates(subset=["customer_id"], keep="first").copy()
    duplicate_customers = int(len(customers) - len(base))
    reference_values = base["feature_reference_date"].dropna().astype(str).unique()
    if len(reference_values) != 1:
        raise ValueError("customer features must contain one feature_reference_date")
    reference_date = parse_reference_date(str(reference_values[0]))
    discounts = average_discount(orders, reference_date)
    sentiments = average_sentiment(reviews, sentiment)
    frame = base.merge(discounts, how="left", on="customer_id").merge(sentiments, how="left", on="customer_id")
    if frame["customer_id"].duplicated().any():
        raise RuntimeError("Customer features were duplicated by the discount or sentiment join")

    notes: dict[str, object] = {
        "customer_count": int(len(frame)),
        "duplicate_customers_removed": duplicate_customers,
        "feature_reference_date": reference_date.isoformat(),
        "features": list(MODEL_FEATURES),
        "feature_reasons": FEATURE_REASONS,
        "imputed_counts": {},
        "clip_bounds": {},
    }
    for column in MODEL_FEATURES:
        missing = int(frame[column].isna().sum())
        if missing:
            median = float(frame[column].median())
            if pd.isna(median):
                raise ValueError(f"{column} is missing for every customer, so it cannot be used")
            frame[column] = frame[column].fillna(median)
            notes["imputed_counts"][column] = {"count": missing, "method": "median", "value": median}
            logger.info("Median-filled %s missing %s values with %.4f", missing, column, median)
        lower = float(frame[column].quantile(0.01))
        upper = float(frame[column].quantile(0.99))
        frame[column] = frame[column].clip(lower=lower, upper=upper)
        notes["clip_bounds"][column] = {"lower": lower, "upper": upper}

    scaler = StandardScaler()
    scaled = scaler.fit(frame.loc[:, list(MODEL_FEATURES)])
    logger.info("Fitted StandardScaler on %s customers and %s features", len(frame), len(MODEL_FEATURES))
    notes["scaler"] = "StandardScaler"
    return frame.reset_index(drop=True), scaled, notes


def scaled_matrix(frame: pd.DataFrame, scaler: StandardScaler) -> pd.DataFrame:
    """Transform model columns with an already fitted scaler."""
    values = scaler.transform(frame.loc[:, list(MODEL_FEATURES)])
    return pd.DataFrame(values, columns=list(MODEL_FEATURES), index=frame.index)


def average_discount(orders: pd.DataFrame, reference_date) -> pd.DataFrame:
    """Mean completed-order discount per customer. Duplicate order ids are kept once."""
    unique_orders = orders.drop_duplicates(subset=["id"], keep="first")
    cutoff = end_of_reference_day(reference_date)
    status = unique_orders["status"].astype("string").str.lower()
    order_date = pd.to_datetime(unique_orders["order_date"], utc=True, format="mixed")
    completed = unique_orders.loc[(status == "completed") & order_date.notna() & (order_date <= cutoff)]
    grouped = completed.groupby("customer_id", as_index=False)["discount_used"].mean()
    return grouped.rename(columns={"discount_used": "avg_discount"})


def average_sentiment(reviews: pd.DataFrame, sentiment: pd.DataFrame) -> pd.DataFrame:
    """Mean VADER score per customer. Each review is counted once."""
    unique_reviews = reviews.drop_duplicates(subset=["id"], keep="first")
    unique_scores = sentiment.drop_duplicates(subset=["review_id"], keep="first")
    linked = unique_scores.merge(unique_reviews.loc[:, ["id", "customer_id"]], left_on="review_id", right_on="id", how="inner")
    grouped = linked.groupby("customer_id", as_index=False)["overall_score"].mean()
    return grouped.rename(columns={"overall_score": "avg_sentiment_score"})


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], dataset: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{dataset} is missing required columns: {', '.join(missing)}")

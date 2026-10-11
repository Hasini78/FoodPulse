"""Customer and restaurant features for later mining modules.

Monetary and frequency metrics use ``orders.status == "completed"`` only.
Cancelled and pending orders are excluded so they do not inflate spend.
Events after the reference date are excluded so a historical reference date
cannot see future orders or reviews.

Recency is the number of calendar days from the last completed order to the
reference date. It is null when the customer has no completed order on or
before that date. Zero completed orders also leave average order value and
discount usage rate null rather than implying a rate of zero.

Order totals are aggregated from ``orders`` before any review join, so line
items cannot duplicate spend.

``complaint_count`` is a heuristic, not a sentiment model: a complaint is a
review with ``rating <= 2`` on or before the reference date.

``sentiment_label`` and ``sentiment_score`` are always null. The sentiment
module owns those columns later.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from etl.transform.parsing import parse_timestamps

logger = logging.getLogger(__name__)

COMPLETED_ORDER_STATUS = "completed"
COMPLAINT_RATING_MAX = 2
ROLLING_RATING_WINDOW_DAYS = 90

CUSTOMER_FEATURE_COLUMNS = (
    "customer_id",
    "recency_days",
    "order_frequency",
    "total_spend",
    "avg_order_value",
    "avg_rating",
    "review_frequency",
    "discount_usage_rate",
    "feature_reference_date",
)

RESTAURANT_FEATURE_COLUMNS = (
    "restaurant_id",
    "avg_rating",
    "rolling_avg_rating",
    "review_volume",
    "order_volume",
    "complaint_count",
    "sentiment_label",
    "sentiment_score",
    "feature_reference_date",
)


def build_customer_features(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    reference_date: date,
) -> pd.DataFrame:
    """Return one feature row per customer id."""
    cutoff = end_of_reference_day(reference_date)
    eligible_orders = _completed_orders(orders, cutoff)
    eligible_reviews = _events_on_or_before(reviews, "created_at", cutoff)

    order_agg = _customer_order_agg(eligible_orders, reference_date)
    review_agg = _customer_review_agg(eligible_reviews)

    base = customers.loc[:, ["id"]].drop_duplicates().rename(columns={"id": "customer_id"})
    features = base.merge(order_agg, how="left", on="customer_id").merge(
        review_agg, how="left", on="customer_id"
    )
    features["order_frequency"] = features["order_frequency"].fillna(0).astype("int64")
    features["total_spend"] = features["total_spend"].fillna(0.0)
    features["review_frequency"] = features["review_frequency"].fillna(0).astype("int64")
    features["feature_reference_date"] = reference_date.isoformat()
    features = features.loc[:, list(CUSTOMER_FEATURE_COLUMNS)]
    logger.info("Built customer features for %s customers", len(features))
    return features.reset_index(drop=True)


def build_restaurant_features(
    restaurants: pd.DataFrame,
    orders: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    reference_date: date,
    rolling_window_days: int = ROLLING_RATING_WINDOW_DAYS,
) -> pd.DataFrame:
    """Return one feature row per restaurant id."""
    cutoff = end_of_reference_day(reference_date)
    window_start = cutoff - timedelta(days=rolling_window_days)
    eligible_orders = _completed_orders(orders, cutoff)
    eligible_reviews = _events_on_or_before(reviews, "created_at", cutoff)
    window_reviews = eligible_reviews.loc[eligible_reviews["created_at"] > window_start]

    order_agg = (
        eligible_orders.groupby("restaurant_id").size().reset_index(name="order_volume")
    )
    review_agg = eligible_reviews.groupby("restaurant_id", as_index=False).agg(
        avg_rating=("rating", "mean"),
        review_volume=("rating", "size"),
    )
    rolling_agg = window_reviews.groupby("restaurant_id", as_index=False).agg(
        rolling_avg_rating=("rating", "mean")
    )
    complaints = (
        eligible_reviews.loc[eligible_reviews["rating"] <= COMPLAINT_RATING_MAX]
        .groupby("restaurant_id")
        .size()
        .reset_index(name="complaint_count")
    )

    base = restaurants.loc[:, ["id"]].drop_duplicates().rename(columns={"id": "restaurant_id"})
    features = (
        base.merge(order_agg, how="left", on="restaurant_id")
        .merge(review_agg, how="left", on="restaurant_id")
        .merge(rolling_agg, how="left", on="restaurant_id")
        .merge(complaints, how="left", on="restaurant_id")
    )
    features["order_volume"] = features["order_volume"].fillna(0).astype("int64")
    features["review_volume"] = features["review_volume"].fillna(0).astype("int64")
    features["complaint_count"] = features["complaint_count"].fillna(0).astype("int64")
    features["sentiment_label"] = pd.Series([pd.NA] * len(features), dtype="string")
    features["sentiment_score"] = pd.Series([pd.NA] * len(features), dtype="Float64")
    features["feature_reference_date"] = reference_date.isoformat()
    features = features.loc[:, list(RESTAURANT_FEATURE_COLUMNS)]
    logger.info("Built restaurant features for %s restaurants", len(features))
    return features.reset_index(drop=True)


def end_of_reference_day(reference_date: date) -> pd.Timestamp:
    """Return the last timestamp of ``reference_date`` in UTC."""
    moment = datetime.combine(reference_date, time.max, tzinfo=timezone.utc)
    return pd.Timestamp(moment)


def parse_reference_date(value: str | date | datetime | None) -> date:
    """Parse a reference date. ``None`` uses the current UTC date."""
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return parsed


def _completed_orders(orders: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    if orders.empty:
        return orders.copy()
    status = orders["status"].astype("string").str.lower()
    order_date = parse_timestamps(orders["order_date"])
    mask = (status == COMPLETED_ORDER_STATUS) & order_date.notna() & (order_date <= cutoff)
    return orders.loc[mask].copy()


def _events_on_or_before(df: pd.DataFrame, column: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df.copy()
    stamps = parse_timestamps(df[column])
    return df.loc[stamps.notna() & (stamps <= cutoff)].copy()


def _customer_order_agg(orders: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(
            columns=[
                "customer_id",
                "order_frequency",
                "total_spend",
                "avg_order_value",
                "recency_days",
                "discount_usage_rate",
            ]
        )
    grouped = orders.groupby("customer_id", as_index=False).agg(
        order_frequency=("id", "count"),
        total_spend=("total_amount", "sum"),
        avg_order_value=("total_amount", "mean"),
        last_order_date=("order_date", "max"),
        discounted_orders=("discount_used", lambda values: int((pd.to_numeric(values) > 0).sum())),
    )
    grouped["discount_usage_rate"] = grouped["discounted_orders"] / grouped["order_frequency"]
    last_dates = parse_timestamps(grouped["last_order_date"]).dt.date
    grouped["recency_days"] = last_dates.map(lambda day: (reference_date - day).days)
    return grouped.drop(columns=["last_order_date", "discounted_orders"])


def _customer_review_agg(reviews: pd.DataFrame) -> pd.DataFrame:
    if reviews.empty:
        return pd.DataFrame(columns=["customer_id", "avg_rating", "review_frequency"])
    return reviews.groupby("customer_id", as_index=False).agg(
        avg_rating=("rating", "mean"),
        review_frequency=("rating", "size"),
    )

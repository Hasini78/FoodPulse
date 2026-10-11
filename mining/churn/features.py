"""Behavior table for inactivity risk.

Spend, frequency, and recency are aggregated from completed orders only.
Order totals are never joined to line items or reviews, so those tables
cannot duplicate spend. Customer ids identify rows. Names, emails, and
phone numbers are not read.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from etl.transform.feature_engineering import end_of_reference_day
from etl.transform.parsing import parse_timestamps

logger = logging.getLogger(__name__)

BEHAVIOR_COLUMNS = (
    "customer_id",
    "inactivity_days",
    "observation_days",
    "order_frequency",
    "total_spend",
    "avg_order_value",
    "avg_discount",
    "discount_usage_rate",
    "avg_rating",
    "review_frequency",
    "avg_sentiment_score",
    "mean_purchase_gap_days",
    "purchase_gap_std_days",
    "recent_order_count",
    "prior_order_count",
)


def build_behavior(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    reviews: pd.DataFrame,
    sentiment: pd.DataFrame,
    reference_date: date,
    recent_window_days: int,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Return one behavior row per customer with a completed order on or before the reference date."""
    _require(customers, ("customer_id",), "customer features")
    _require(orders, ("id", "customer_id", "total_amount", "discount_used", "status", "order_date"), "orders")
    _require(reviews, ("id", "customer_id", "rating", "created_at"), "reviews")
    _require(sentiment, ("review_id", "overall_score"), "review sentiment")
    if recent_window_days < 1:
        raise ValueError("recent_window_days must be an integer greater than or equal to 1")

    base = customers.drop_duplicates(subset=["customer_id"], keep="first").loc[:, ["customer_id"]]
    duplicate_customers = int(len(customers) - len(base))
    prepared, order_stats = _prepare_orders(orders, reference_date, set(base["customer_id"]))
    behavior = _order_behavior(prepared, reference_date, recent_window_days)
    ratings = _rating_summary(reviews, reference_date)
    sentiments = _sentiment_summary(reviews, sentiment, reference_date)
    frame = behavior.merge(ratings, how="left", on="customer_id").merge(sentiments, how="left", on="customer_id")
    if frame["customer_id"].duplicated().any():
        raise RuntimeError("Behavior rows were duplicated by the rating or sentiment join")
    frame["review_frequency"] = frame["review_frequency"].fillna(0).astype("int64")
    frame = frame.loc[:, list(BEHAVIOR_COLUMNS)].sort_values("customer_id").reset_index(drop=True)
    eligible_ids = set(frame["customer_id"])
    without_orders = int((~base["customer_id"].isin(eligible_ids)).sum())
    stats = {
        "source_customer_rows": int(len(customers)),
        "duplicate_customer_rows_removed": duplicate_customers,
        "customers_without_completed_orders": without_orders,
        "eligible_customers": int(len(frame)),
        **order_stats,
    }
    logger.info("Built inactivity features for %s customers", len(frame))
    return frame, stats


def _prepare_orders(
    orders: pd.DataFrame,
    reference_date: date,
    customer_ids: set[object],
) -> tuple[pd.DataFrame, dict[str, int]]:
    cutoff = end_of_reference_day(reference_date)
    working = orders.copy()
    working["order_id"] = working["id"]
    working["order_timestamp"] = parse_timestamps(working["order_date"])
    working["total_amount"] = pd.to_numeric(working["total_amount"], errors="coerce")
    working["discount_used"] = pd.to_numeric(working["discount_used"], errors="coerce").fillna(0.0)
    working["status_norm"] = working["status"].astype("string").str.strip().str.lower()
    invalid = working["order_id"].isna() | working["customer_id"].isna() | working["total_amount"].isna() | working["order_timestamp"].isna()
    known = working.loc[~invalid].copy()
    duplicate_ids = int(known["order_id"].duplicated().sum())
    known = known.drop_duplicates(subset=["order_id"], keep="first")
    dated = known.loc[known["order_timestamp"] <= cutoff].copy()
    unknown_customer = ~dated["customer_id"].isin(customer_ids)
    in_scope = dated.loc[~unknown_customer].copy()
    completed = in_scope.loc[in_scope["status_norm"] == "completed"].copy()
    completed["order_day"] = completed["order_timestamp"].dt.date
    stats = {
        "invalid_order_rows": int(invalid.sum()),
        "duplicate_order_ids_removed": duplicate_ids,
        "orders_after_reference_ignored": int((known["order_timestamp"] > cutoff).sum()),
        "non_completed_orders_ignored": int((in_scope["status_norm"] != "completed").sum()),
        "orders_for_unknown_customers": int(unknown_customer.sum()),
        "completed_orders_used": int(len(completed)),
    }
    return completed, stats


def _order_behavior(orders: pd.DataFrame, reference_date: date, recent_window_days: int) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(columns=[column for column in BEHAVIOR_COLUMNS if column not in {"avg_rating", "review_frequency", "avg_sentiment_score"}])
    recent_start = reference_date - timedelta(days=recent_window_days)
    prior_start = reference_date - timedelta(days=2 * recent_window_days)
    rows: list[dict[str, object]] = []
    for customer_id, group in orders.groupby("customer_id", sort=True):
        ordered = group.sort_values(["order_timestamp", "order_id"])
        days = list(ordered["order_day"])
        gaps = [(days[index] - days[index - 1]).days for index in range(1, len(days))]
        first_day = days[0]
        last_day = days[-1]
        positive_discount = ordered["discount_used"] > 0
        rows.append(
            {
                "customer_id": customer_id,
                "inactivity_days": (reference_date - last_day).days,
                "observation_days": (reference_date - first_day).days,
                "order_frequency": int(len(ordered)),
                "total_spend": float(ordered["total_amount"].sum()),
                "avg_order_value": float(ordered["total_amount"].mean()),
                "avg_discount": float(ordered["discount_used"].mean()),
                "discount_usage_rate": float(positive_discount.mean()),
                "mean_purchase_gap_days": float(sum(gaps) / len(gaps)) if gaps else pd.NA,
                "purchase_gap_std_days": float(pd.Series(gaps, dtype="float64").std(ddof=1)) if len(gaps) >= 2 else pd.NA,
                "recent_order_count": int(((ordered["order_day"] >= recent_start) & (ordered["order_day"] <= reference_date)).sum()),
                "prior_order_count": int(((ordered["order_day"] >= prior_start) & (ordered["order_day"] < recent_start)).sum()),
            }
        )
    return pd.DataFrame(rows)


def _rating_summary(reviews: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    cutoff = end_of_reference_day(reference_date)
    unique = reviews.drop_duplicates(subset=["id"], keep="first").copy()
    stamps = parse_timestamps(unique["created_at"])
    ratings = pd.to_numeric(unique["rating"], errors="coerce")
    usable = unique.loc[stamps.notna() & (stamps <= cutoff) & ratings.notna(), ["id", "customer_id"]].copy()
    usable["rating"] = ratings.loc[usable.index]
    if usable.empty:
        return pd.DataFrame(columns=["customer_id", "avg_rating", "review_frequency"])
    return usable.groupby("customer_id", as_index=False).agg(
        avg_rating=("rating", "mean"),
        review_frequency=("rating", "size"),
    )


def _sentiment_summary(reviews: pd.DataFrame, sentiment: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    cutoff = end_of_reference_day(reference_date)
    unique_reviews = reviews.drop_duplicates(subset=["id"], keep="first").copy()
    stamps = parse_timestamps(unique_reviews["created_at"])
    unique_reviews = unique_reviews.loc[stamps.notna() & (stamps <= cutoff), ["id", "customer_id"]]
    unique_scores = sentiment.drop_duplicates(subset=["review_id"], keep="first")
    linked = unique_scores.merge(unique_reviews, left_on="review_id", right_on="id", how="inner")
    if linked.empty:
        return pd.DataFrame(columns=["customer_id", "avg_sentiment_score"])
    grouped = linked.groupby("customer_id", as_index=False)["overall_score"].mean()
    return grouped.rename(columns={"overall_score": "avg_sentiment_score"})


def _require(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")

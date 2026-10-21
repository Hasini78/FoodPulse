"""FACT_REVIEWS. Review text is not loaded."""

from __future__ import annotations

import pandas as pd

from warehouse.snowflake.keys import as_utc_timestamp, date_key, number, surrogate, token

COLUMNS = (
    "review_sk",
    "review_id",
    "date_sk",
    "customer_sk",
    "restaurant_sk",
    "order_sk",
    "rating",
    "review_ts",
)


def build_reviews(
    reviews: pd.DataFrame,
    customers: pd.DataFrame,
    restaurants: pd.DataFrame,
    orders: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """Return one row per review with customer, restaurant, and date keys."""
    if reviews.empty:
        return pd.DataFrame(columns=COLUMNS), 0
    customer_sk = {row["customer_id"]: row["customer_sk"] for row in customers.to_dict("records")}
    restaurant_sk = {row["restaurant_id"]: row["restaurant_sk"] for row in restaurants.to_dict("records")}
    order_sk = {row["order_id"]: row["order_sk"] for row in orders.to_dict("records")}
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    skipped = 0
    ordered = reviews.copy()
    ordered["_sk"] = ordered["id"].map(surrogate) if "id" in ordered.columns else None
    ordered = ordered.sort_values(["_sk"], kind="mergesort")
    for record in ordered.to_dict("records"):
        key = surrogate(record.get("id"))
        natural = token(record.get("id"))
        stamp = as_utc_timestamp(record.get("created_at"))
        day = date_key(stamp)
        customer = customer_sk.get(token(record.get("customer_id")) or "")
        restaurant = restaurant_sk.get(token(record.get("restaurant_id")) or "")
        if key is None or natural is None or natural in seen or day is None or customer is None or restaurant is None:
            skipped += 1
            continue
        seen.add(natural)
        parsed_rating = number(record.get("rating"))
        rows.append(
            {
                "review_sk": key,
                "review_id": natural,
                "date_sk": day,
                "customer_sk": customer,
                "restaurant_sk": restaurant,
                "order_sk": order_sk.get(token(record.get("order_id")) or ""),
                "rating": None if parsed_rating is None else int(parsed_rating),
                "review_ts": stamp,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS), skipped

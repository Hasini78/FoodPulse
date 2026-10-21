"""FACT_ORDERS at order grain. Line items are not exploded onto this table."""

from __future__ import annotations

import pandas as pd

from warehouse.snowflake.keys import as_utc_timestamp, date_key, flag, number, surrogate, text, token

COLUMNS = (
    "order_sk",
    "order_id",
    "date_sk",
    "customer_sk",
    "restaurant_sk",
    "status",
    "total_amount",
    "discount_used",
    "total_amount_capped",
    "is_total_outlier",
    "order_ts",
)


def build_orders(orders: pd.DataFrame, customers: pd.DataFrame, restaurants: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Return one row per order that has date, customer, and restaurant keys."""
    if orders.empty:
        return pd.DataFrame(columns=COLUMNS), 0
    customer_sk = {row["customer_id"]: row["customer_sk"] for row in customers.to_dict("records")}
    restaurant_sk = {row["restaurant_id"]: row["restaurant_sk"] for row in restaurants.to_dict("records")}
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    skipped = 0
    ordered = orders.copy()
    ordered["_sk"] = ordered["id"].map(surrogate) if "id" in ordered.columns else None
    ordered = ordered.sort_values(["_sk"], kind="mergesort")
    for record in ordered.to_dict("records"):
        key = surrogate(record.get("id"))
        natural = token(record.get("id"))
        stamp = as_utc_timestamp(record.get("order_date"))
        day = date_key(stamp)
        customer = customer_sk.get(token(record.get("customer_id")) or "")
        restaurant = restaurant_sk.get(token(record.get("restaurant_id")) or "")
        if key is None or natural is None or natural in seen or day is None or customer is None or restaurant is None:
            skipped += 1
            continue
        seen.add(natural)
        rows.append(
            {
                "order_sk": key,
                "order_id": natural,
                "date_sk": day,
                "customer_sk": customer,
                "restaurant_sk": restaurant,
                "status": text(record.get("status")),
                "total_amount": number(record.get("total_amount")),
                "discount_used": number(record.get("discount_used")),
                "total_amount_capped": number(record.get("total_amount_capped")),
                "is_total_outlier": flag(record.get("is_total_outlier")),
                "order_ts": stamp,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS), skipped

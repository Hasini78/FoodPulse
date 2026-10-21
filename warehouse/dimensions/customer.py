"""DIM_CUSTOMER without PII columns from customers.parquet."""

from __future__ import annotations

import pandas as pd

from warehouse.snowflake.keys import as_utc_timestamp, surrogate, text, token

COLUMNS = ("customer_sk", "customer_id", "city", "gender", "created_at")
EXCLUDED_COLUMNS = ("email", "phone", "first_name", "last_name", "date_of_birth")


def build_customer(customers: pd.DataFrame) -> pd.DataFrame:
    """Return one row per customer_id. Duplicate ids keep the first sorted row."""
    if customers.empty:
        return pd.DataFrame(columns=COLUMNS)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    ordered = customers.copy()
    ordered["_sk"] = ordered["id"].map(surrogate) if "id" in ordered.columns else None
    ordered = ordered.sort_values(["_sk"], kind="mergesort")
    for record in ordered.to_dict("records"):
        key = surrogate(record.get("id"))
        natural = token(record.get("id"))
        if key is None or natural is None or natural in seen:
            continue
        seen.add(natural)
        rows.append(
            {
                "customer_sk": key,
                "customer_id": natural,
                "city": text(record.get("city")),
                "gender": text(record.get("gender")),
                "created_at": as_utc_timestamp(record.get("created_at")),
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)

"""DIM_FOOD_ITEM. Menu items point at DIM_RESTAURANT; they are not a fact grain."""

from __future__ import annotations

import pandas as pd

from warehouse.snowflake.keys import as_utc_timestamp, flag, number, surrogate, text, token

COLUMNS = (
    "food_item_sk",
    "food_item_id",
    "restaurant_sk",
    "restaurant_id",
    "name",
    "category",
    "price",
    "is_available",
    "created_at",
)


def build_food_item(foods: pd.DataFrame, restaurants: pd.DataFrame) -> pd.DataFrame:
    """Return food items whose restaurant_id exists on DIM_RESTAURANT."""
    if foods.empty:
        return pd.DataFrame(columns=COLUMNS)
    restaurant_sk = {
        row["restaurant_id"]: row["restaurant_sk"]
        for row in restaurants.to_dict("records")
        if row.get("restaurant_id") is not None
    }
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    ordered = foods.copy()
    ordered["_sk"] = ordered["id"].map(surrogate) if "id" in ordered.columns else None
    ordered = ordered.sort_values(["_sk"], kind="mergesort")
    for record in ordered.to_dict("records"):
        key = surrogate(record.get("id"))
        natural = token(record.get("id"))
        restaurant_id = token(record.get("restaurant_id"))
        place = restaurant_sk.get(restaurant_id) if restaurant_id else None
        if key is None or natural is None or place is None or natural in seen:
            continue
        seen.add(natural)
        rows.append(
            {
                "food_item_sk": key,
                "food_item_id": natural,
                "restaurant_sk": place,
                "restaurant_id": restaurant_id,
                "name": text(record.get("name")),
                "category": text(record.get("category")),
                "price": number(record.get("price")),
                "is_available": flag(record.get("is_available")),
                "created_at": as_utc_timestamp(record.get("created_at")),
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)

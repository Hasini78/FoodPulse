"""Read-only relational checks over processed Parquet.

This module never writes Parquet, never connects to PostgreSQL, and never
invents rows. Completed-order counts lowercase ``status`` without stripping,
matching the analytics dashboard.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_FILES = (
    "locations.parquet",
    "restaurants.parquet",
    "food_items.parquet",
    "customers.parquet",
    "orders.parquet",
    "order_items.parquet",
    "reviews.parquet",
    "food_recommendations.parquet",
    "restaurant_recommendations.parquet",
)


def id_set(frame: pd.DataFrame, column: str = "id") -> set[int]:
    values: set[int] = set()
    if column not in frame.columns:
        return values
    for value in frame[column]:
        token = _int_token(value)
        if token is not None:
            values.add(token)
    return values


def completed_mask(orders: pd.DataFrame) -> pd.Series:
    status = orders["status"].map(lambda value: "" if _missing(value) else str(value).lower())
    return status == "completed"


def parquet_consistency_report(processed_dir: Path) -> dict[str, object]:
    """Return counts and gap lists. Does not repair files."""
    frames = _read_required(processed_dir)
    locations = frames["locations"]
    restaurants = frames["restaurants"]
    foods = frames["food_items"]
    customers = frames["customers"]
    orders = frames["orders"]
    items = frames["order_items"]
    reviews = frames["reviews"]
    food_recs = frames["food_recommendations"]
    restaurant_recs = frames["restaurant_recommendations"]

    location_ids = id_set(locations)
    restaurant_ids = id_set(restaurants)
    food_ids = id_set(foods)
    customer_ids = id_set(customers)
    order_ids = id_set(orders)
    completed = orders.loc[completed_mask(orders)]
    completed_ids = id_set(completed)

    food_restaurant = _map_int(foods, "id", "restaurant_id")
    order_restaurant = _map_int(orders, "id", "restaurant_id")
    offering_sizes = foods.groupby(["name", "restaurant_id"]).size() if not foods.empty else pd.Series(dtype="int64")

    rec_food_unknown = _unknown_ids(food_recs, "food_item_id", food_ids)
    rec_food_customers = id_set(food_recs, "customer_id")
    rec_restaurant_customers = id_set(restaurant_recs, "customer_id")

    mismatch = 0
    for record in items.to_dict("records"):
        food_id = _int_token(record.get("food_item_id"))
        order_id = _int_token(record.get("order_id"))
        if food_id is None or order_id is None:
            mismatch += 1
            continue
        if food_restaurant.get(food_id) != order_restaurant.get(order_id):
            mismatch += 1

    return {
        "source": "processed_parquet",
        "completed_rule": "status.str.lower() == 'completed' without strip",
        "counts": {
            "locations": int(len(locations)),
            "restaurants": int(len(restaurants)),
            "food_items": int(len(foods)),
            "customers": int(len(customers)),
            "orders": int(len(orders)),
            "completed_orders": int(len(completed)),
            "order_items": int(len(items)),
            "completed_order_items": int(items["order_id"].map(_int_token).isin(completed_ids).sum()) if not items.empty else 0,
            "reviews": int(len(reviews)),
            "food_recommendations": int(len(food_recs)),
            "restaurant_recommendations": int(len(restaurant_recs)),
            "unique_food_names": int(foods["name"].nunique()) if "name" in foods.columns else 0,
            "offering_groups": int(len(offering_sizes)),
            "offering_groups_with_duplicate_ids": int((offering_sizes > 1).sum()) if len(offering_sizes) else 0,
        },
        "duplicate_primary_keys": {
            "locations": int(locations["id"].duplicated().sum()) if "id" in locations.columns else 0,
            "restaurants": int(restaurants["id"].duplicated().sum()),
            "food_items": int(foods["id"].duplicated().sum()),
            "customers": int(customers["id"].duplicated().sum()),
            "orders": int(orders["id"].duplicated().sum()),
            "order_items": int(items["id"].duplicated().sum()) if "id" in items.columns else int(len(items)),
            "reviews": int(reviews["id"].duplicated().sum()),
        },
        "foreign_key_gaps": {
            "restaurants_missing_location": _missing_count(restaurants, "location_id", location_ids),
            "food_items_missing_restaurant": _missing_count(foods, "restaurant_id", restaurant_ids),
            "orders_missing_customer": _missing_count(orders, "customer_id", customer_ids),
            "orders_missing_restaurant": _missing_count(orders, "restaurant_id", restaurant_ids),
            "order_items_missing_order": _missing_count(items, "order_id", order_ids),
            "order_items_missing_food": _missing_count(items, "food_item_id", food_ids),
            "order_items_restaurant_mismatch": mismatch,
            "reviews_missing_customer": _missing_count(reviews, "customer_id", customer_ids),
            "reviews_missing_restaurant": _missing_count(reviews, "restaurant_id", restaurant_ids),
            "reviews_missing_order": _missing_count(reviews.dropna(subset=["order_id"]) if "order_id" in reviews.columns else reviews, "order_id", order_ids),
        },
        "recommendation_coverage": {
            "food_rec_customers": len(rec_food_customers),
            "restaurant_rec_customers": len(rec_restaurant_customers),
            "customers_without_food_recs": len(customer_ids - rec_food_customers),
            "customers_without_restaurant_recs": len(customer_ids - rec_restaurant_customers),
            "food_recs_unknown_customer": len(rec_food_customers - customer_ids),
            "food_recs_unknown_food": rec_food_unknown,
            "food_recs_unknown_restaurant": _unknown_ids(food_recs, "restaurant_id", restaurant_ids),
            "restaurant_recs_unknown_restaurant": _unknown_ids(restaurant_recs, "restaurant_id", restaurant_ids),
            "customers_without_orders": len(customer_ids - id_set(orders, "customer_id")),
            "customers_without_completed_orders": len(customer_ids - id_set(completed, "customer_id")),
        },
        "postgres_loader_expected": {
            "food_items": int(len(foods)),
            "order_items": int(len(items)),
            "note": "PostgreSQL currently holds operational parents. food_items and order_items still require an approved --execute load.",
        },
    }


def _read_required(processed_dir: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    missing = []
    for name in REQUIRED_FILES:
        path = processed_dir / name
        key = name.removesuffix(".parquet")
        if not path.is_file():
            missing.append(name)
            frames[key] = pd.DataFrame()
            continue
        frames[key] = pd.read_parquet(path)
    if missing:
        raise FileNotFoundError("Required Parquet files were not found: " + ", ".join(missing))
    return frames


def _missing_count(frame: pd.DataFrame, column: str, parent_ids: set[int]) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(sum(_int_token(value) not in parent_ids for value in frame[column]))


def _unknown_ids(frame: pd.DataFrame, column: str, parent_ids: set[int]) -> int:
    return _missing_count(frame, column, parent_ids)


def _map_int(frame: pd.DataFrame, key: str, value: str) -> dict[int, int]:
    mapping: dict[int, int] = {}
    if frame.empty or key not in frame.columns or value not in frame.columns:
        return mapping
    for record in frame.to_dict("records"):
        left = _int_token(record.get(key))
        right = _int_token(record.get(value))
        if left is not None and right is not None:
            mapping[left] = right
    return mapping


def _int_token(value: object) -> int | None:
    if _missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer():
        return None
    return int(number)


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
